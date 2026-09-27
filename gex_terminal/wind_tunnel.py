"""Deterministic, bounded counterfactual repricing of bundled synthetic replays.

The consumer owns replay accumulation. Every evaluation then prices detached
copies of that checkpoint using the existing engine, without ingesting future
events or inventing a future price path. IV shifts are absolute volatility
points (1 means +0.01); time advances are minutes; spot shifts are points.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np

from gex_terminal import __version__
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.contracts import days_until_expiry, expiry_date, parse_market_datetime
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import validate_normalized_message
from gex_terminal.replay_catalog import ReplaySession, bundled_replay_sessions


VERSION = 1
REQUEST_SCHEMA = "gex-terminal.wind-tunnel.request.v1"
MODELS = ("raw_trade_volume", "open_interest", "directionalized_trade_volume")
MODEL_LABELS = {
    "raw_trade_volume": "Volume proxy",
    "open_interest": "Open-interest proxy",
    "directionalized_trade_volume": "Aggressor-directionalized proxy",
}
EXAMPLE_NAMES = ("discovered-break", "no-break", "expiry-exclusion")
BOUNDS = {
    "spot_shift": (-5000.0, 5000.0),
    "iv_shift": (-100.0, 100.0),
    "time_advance": (0.0, 43200.0),
    "fallback_dte": (0.000001, 30.0),
    "risk_free_rate": (-0.1, 1.0),
    "minimum_directional_coverage": (0.0, 1.0),
}
DEFAULTS = {
    "session": "wind-tunnel-lab", "checkpoint": None,
    "model": "raw_trade_volume", "spot_shift": 0.0, "iv_shift": 0.0,
    "time_advance": 0.0, "exclude_nearest_expiry": False,
    "fallback_dte": 0.25, "risk_free_rate": 0.045,
    "minimum_directional_coverage": 0.5,
}
LIMITATIONS = {
    "source_kind": "synthetic_fixture", "predictive_validity": "unmeasured",
    "participant_classification": "unobserved", "opening_closing_classification": "unobserved",
    "live_provider_certified": False, "models_may_not_be_summed": True,
    "future_events_used": False, "future_price_path_predicted": False,
    "interpretation": "Conditional model calculations, not market forecasts or outcome probabilities.",
    "iv_policy": "Sticky strike: supplied row IV plus an absolute uniform shift; no smile dynamics inferred.",
    "time_policy": "Frozen quantities; advance model time without reading later replay events.",
    "expiry_policy": "Exact expiry instants take precedence; otherwise remaining model DTE decreases from the checkpoint fallback.",
    "directional_assumption": "Aggressor buy implies passive counterparty short gamma; sell implies long gamma. Unknown direction is excluded from signed exposure, not coverage.",
    "zero_gamma_semantics": "Legacy strike-profile crossing or neutral-strike fallback, not a portfolio underlying-price root.",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def calculation_identity() -> dict:
    """Bind numeric behavior and replay projection to exact local implementation."""
    names = ("wind_tunnel.py", "engine.py", "consumer.py", "contracts.py", "market_data_adapter.py", "replay_catalog.py")
    return {
        "contract_version": VERSION, "application_version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}", "numpy": np.__version__,
        "implementation": {name: hashlib.sha256(files("gex_terminal").joinpath(name).read_bytes()).hexdigest() for name in names},
    }


def _report(kind: str, **content: Any) -> dict:
    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{kind}.v1", "version": VERSION,
        "calculation": identity, "calculation_fingerprint": _sha(identity),
        "limitations": copy.deepcopy(LIMITATIONS), **content,
    }
    if "request" in content:
        result["request_sha256"] = _sha(content["request"])
        result["model_identity_sha256"] = _sha({
            "calculation_fingerprint": result["calculation_fingerprint"],
            **{key: content["request"][key] for key in ("model", "fallback_dte", "risk_free_rate", "minimum_directional_coverage")},
        })
    # Convert numpy scalars without rounding scientific outputs.
    result = json.loads(json.dumps(result, allow_nan=False, default=lambda item: item.item()))
    result["result_sha256"] = _sha(result)
    return result


def _sessions() -> tuple[ReplaySession, ...]:
    example = ReplaySession(
        name="wind-tunnel-lab",
        path=str(files("gex_terminal").joinpath("data/wind_tunnel/es_multi_expiry.jsonl")),
        label="ES Wind Tunnel Lab",
        description="Synthetic ES chain with two exact expiries, separated OI/trade quantities and known aggressor direction.",
        symbol="ES", contract_multiplier=50,
    )
    return (example, *bundled_replay_sessions())


def _session(name: Any) -> ReplaySession:
    if not isinstance(name, str):
        raise ValueError("session must name a bundled replay")
    for session in _sessions():
        if session.name == name:
            return session
    raise ValueError("Unknown bundled Wind Tunnel session")


def _messages(session: ReplaySession) -> tuple[list[dict], bytes]:
    raw = Path(session.path).read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("Bundled replay exceeds the 2 MB input limit")
    records = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    if not records or len(records) > 10000:
        raise ValueError("Bundled replay must have between 1 and 10000 events")
    return records, raw


def _timeline(records: list[dict]) -> list[dict]:
    result = []
    previous = None
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("Every replay event must be an object")
        validate_normalized_message(record)
        time = parse_market_datetime(record.get("event_time") or record.get("timestamp"))
        if time is None:
            raise ValueError("Wind Tunnel requires timezone-bearing event time on every replay event")
        if previous is not None and time < previous:
            raise ValueError("Wind Tunnel checkpoints require nondecreasing replay event time")
        previous = time
        result.append({"index": index, "as_of": _time(time), "event_type": record["type"],
                       "phase": record.get("session_phase"), "spot": record.get("price")})
    return result


def _time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def catalog() -> dict:
    entries = []
    for session in _sessions():
        records, raw = _messages(session)
        try:
            timeline = _timeline(records)
            status, reason = "available", None
        except ValueError as error:
            timeline, status, reason = [], "unavailable", str(error)
        v2 = [r for r in records if r.get("type") == "options_volume_tick" and r.get("schema_version", 1) == 2]
        present = {r.get("position_source", "trade_volume") for r in v2}
        directional = any(r.get("aggressor_side") in {"buy", "sell"} for r in v2)
        entries.append({
            "name": session.name, "label": session.label, "description": session.description,
            "symbol": session.symbol, "contract_multiplier": session.contract_multiplier,
            "source_ref": session.source_ref, "source_sha256": hashlib.sha256(raw).hexdigest(),
            "status": status, "reason": reason, "event_count": len(records),
            "first_as_of": timeline[0]["as_of"] if timeline else None,
            "last_as_of": timeline[-1]["as_of"] if timeline else None,
            "models": {model: {"label": MODEL_LABELS[model], "available_in_source": (
                ("open_interest" in present) if model == "open_interest" else
                directional if model == "directionalized_trade_volume" else
                ("trade_volume" in present or not v2)
            )} for model in MODELS},
        })
    return _report("catalog", sessions=entries, models=MODEL_LABELS,
                   bounds={key: list(value) for key, value in BOUNDS.items()},
                   defaults=DEFAULTS, examples=list(EXAMPLE_NAMES), max_axis_points=41)


def checkpoints(session: str) -> dict:
    selected = _session(session)
    records, raw = _messages(selected)
    timeline = _timeline(records)
    return _report("checkpoints", session=selected.name, symbol=selected.symbol,
                   source_sha256=hashlib.sha256(raw).hexdigest(), checkpoints=timeline)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite JSON number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    low, high = BOUNDS[name]
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return number


def _axis(value: Any, name: str) -> list[float]:
    if not isinstance(value, list) or not 1 <= len(value) <= 41:
        raise ValueError("Grid axes must contain between 1 and 41 numbers")
    values = [_number(item, name) for item in value]
    if any(left >= right for left, right in zip(values, values[1:])):
        raise ValueError("Grid axes must be strictly increasing with no duplicate values")
    return values


def normalize_request(request: Mapping[str, Any], operation: str = "calculate") -> dict:
    """Reject unknown, nonfinite, unbounded or ambiguous public input."""
    if not isinstance(request, Mapping) or operation not in {"calculate", "surface", "search"}:
        raise ValueError("Expected a Wind Tunnel request object and supported operation")
    extra = {"calculate": set(), "surface": {"spot_shifts", "time_advances"},
             "search": {"x_axis", "y_axis", "x_values", "y_values", "claim", "comparison_model"}}[operation]
    unknown = set(request) - (set(DEFAULTS) | extra | {"schema", "operation"})
    if unknown:
        raise ValueError("Unknown Wind Tunnel fields: " + ", ".join(sorted(map(str, unknown))))
    if request.get("schema", REQUEST_SCHEMA) != REQUEST_SCHEMA or request.get("operation", operation) != operation:
        raise ValueError("Unsupported Wind Tunnel request schema or operation")
    result = {**DEFAULTS, **dict(request), "schema": REQUEST_SCHEMA, "operation": operation}
    _session(result["session"])
    if result["model"] not in MODELS:
        raise ValueError("Unknown quantity model")
    if result["checkpoint"] is not None and (type(result["checkpoint"]) is not int or result["checkpoint"] < 0):
        raise ValueError("checkpoint must be null or a nonnegative integer event index")
    if type(result["exclude_nearest_expiry"]) is not bool:
        raise ValueError("exclude_nearest_expiry must be boolean")
    for name in BOUNDS:
        result[name] = _number(result[name], name)
    if operation == "surface":
        result["spot_shifts"] = _axis(result.get("spot_shifts", [float(x) for x in range(-100, 101, 10)]), "spot_shift")
        result["time_advances"] = _axis(result.get("time_advances", [float(t) for t in range(0, 181, 15)]), "time_advance")
    elif operation == "search":
        result.setdefault("x_axis", "spot_shift")
        result.setdefault("y_axis", "iv_shift")
        axes = {"spot_shift", "iv_shift", "time_advance"}
        if (not isinstance(result["x_axis"], str) or not isinstance(result["y_axis"], str)
                or result["x_axis"] not in axes or result["y_axis"] not in axes or result["x_axis"] == result["y_axis"]):
            raise ValueError("Search requires two distinct shock axes")
        defaults = {"spot_shift": [-100, -50, 0, 50, 100], "iv_shift": [-4, -2, 0, 2, 4], "time_advance": [0, 15, 30, 60, 120]}
        for coordinate in ("x", "y"):
            name = result[f"{coordinate}_axis"]
            result[f"{coordinate}_values"] = _axis(result.get(f"{coordinate}_values", defaults[name]), name)
        result.setdefault("claim", "wall_change")
        result.setdefault("comparison_model", "open_interest")
        if not isinstance(result["claim"], str) or result["claim"] not in {"wall_change", "net_sign", "model_disagreement"}:
            raise ValueError("Unknown fragility claim")
        if result["comparison_model"] not in MODELS:
            raise ValueError("Unknown comparison model")
        if result["claim"] == "model_disagreement" and result["comparison_model"] == result["model"]:
            raise ValueError("Model disagreement requires two different quantity models")
    return result


@dataclass(frozen=True)
class _Checkpoint:
    source: dict
    spot: float
    as_of: datetime
    rows: tuple[dict, ...]
    mode: str
    multiplier: int


async def _checkpoint(request: dict) -> _Checkpoint:
    session = _session(request["session"])
    records, raw = _messages(session)
    timeline = _timeline(records)
    index = len(records) - 1 if request["checkpoint"] is None else request["checkpoint"]
    if index >= len(records):
        raise ValueError("checkpoint is outside the bundled replay")
    request["checkpoint"] = index
    as_of = parse_market_datetime(timeline[index]["as_of"])
    consumer = StatefulGexConsumer(IntradayGexEngine(session.contract_multiplier),
                                  target_underlying=session.symbol, risk_free_rate=request["risk_free_rate"], data_mode="replay")
    accepted = 0
    for number, message in enumerate(records[:index + 1]):
        accepted += bool(await consumer.update_market_state(json.dumps(message)))
        if number % 128 == 127:
            await asyncio.sleep(0)
    if consumer._v1_option_count and consumer._v2_option_count:
        raise ValueError("Mixed legacy/v2 replay state is not a supported Wind Tunnel checkpoint")
    rows = []
    if consumer._v1_option_count:
        mode = "legacy_v1"
        for strike, state in sorted(consumer.chain_state.items()):
            # Use the consumer's last-IV strike projection exactly. Legacy
            # expiries/individual contracts cannot be recovered from that map.
            for option in ("C", "P"):
                rows.append({"contract_id": f"legacy:{strike:g}:{option}", "provider": "legacy",
                             "symbol": session.symbol, "strike": strike, "option_type": option,
                             "accumulated_volume": state[option], "position_source": "trade_volume",
                             "iv": state["iv"], "pricing_model": "black_scholes", "expiry": "legacy aggregate",
                             "contract_multiplier": None, "iv_source": "legacy_unspecified"})
    else:
        mode = "contract_v2"
        rows = copy.deepcopy(list(consumer.contract_state.values()))
    if len(rows) > 5000:
        raise ValueError("Wind Tunnel supports at most 5000 checkpoint contract rows")
    source = {
        "session": session.name, "label": session.label, "symbol": session.symbol,
        "source_ref": session.source_ref, "source_sha256": hashlib.sha256(raw).hexdigest(),
        "checkpoint_sha256": _sha(records[:index + 1]), "checkpoint": index,
        "as_of": _time(as_of), "events_available": index + 1, "events_accepted": accepted,
        "later_events_excluded": len(records) - index - 1,
        "off_symbol_or_duplicate_events": index + 1 - accepted,
        "synthetic": True, "rights_status": session.rights_status, "redistributable": session.redistributable,
        "contract_multiplier": session.contract_multiplier, "calculation_mode": mode,
    }
    return _Checkpoint(source, consumer.current_spot, as_of, tuple(rows), mode, session.contract_multiplier)


def _baseline(request: dict) -> dict:
    return {**request, "spot_shift": 0.0, "iv_shift": 0.0, "time_advance": 0.0, "exclude_nearest_expiry": False}


def _state(checkpoint: _Checkpoint, request: dict, *, details: bool = True) -> dict:
    model = request["model"]
    spot = checkpoint.spot + request["spot_shift"]
    advance = request["time_advance"]
    as_of = checkpoint.as_of + timedelta(minutes=advance)
    source_name = "open_interest" if model == "open_interest" else "trade_volume"
    original = [row for row in checkpoint.rows if row.get("position_source") == source_name]
    result = {
        "status": "no_data", "reason": None, "model": model, "model_label": MODEL_LABELS[model],
        "spot": spot, "as_of": _time(as_of), "matrix": None, "summary": None,
        "counts": {"source_rows": len(original), "selected_rows": 0, "expired_rows": 0,
                   "excluded_nearest_rows": 0, "fallback_expiry_rows": 0},
        "contracts": [], "excluded_contracts": [],
    }
    if checkpoint.spot <= 0 or not original:
        result["reason"] = "No underlying and quantity-source state is available at this checkpoint."
        return result
    if checkpoint.mode == "legacy_v1" and model == "directionalized_trade_volume":
        result["reason"] = "Legacy replay has no aggressor-direction evidence."
        result["status"] = "insufficient_directional_coverage"
        return result
    if spot <= 0:
        result.update(status="invalid_scenario", reason="Scenario underlying price must remain positive.")
        return result
    for field in ("spot_shift", "iv_shift", "time_advance"):
        if not BOUNDS[field][0] <= request[field] <= BOUNDS[field][1]:
            result.update(status="invalid_scenario", reason=f"Combined {field} exceeds the declared numerical bounds.")
            return result
    prepared = []
    for raw in original:
        row = copy.deepcopy(raw)
        exact = days_until_expiry(row.get("expiry_timestamp"), checkpoint.as_of)
        base_dte = exact if exact is not None else float(row.get("days_to_expiry") or request["fallback_dte"])
        row["checkpoint_dte"] = base_dte
        row["remaining_dte"] = base_dte - advance / 1440.0
        row["expiry_authority"] = "exact_timestamp" if exact is not None else "contract_dte" if row.get("days_to_expiry") else "configured_fallback"
        row["base_iv"] = float(row.get("iv", 0.15))
        row["scenario_iv"] = row["base_iv"] + request["iv_shift"] / 100.0
        prepared.append(row)
    # Freeze the removed expiry cohort at the checkpoint; it does not jump to
    # the next expiry after advancing time.
    candidates = [row for row in prepared if row["checkpoint_dte"] > 0 and not (
        row["expiry_authority"] != "exact_timestamp"
        and (dated := expiry_date(row.get("expiry"))) and dated < checkpoint.as_of.date()
    )]
    nearest = min((row["checkpoint_dte"] for row in candidates), default=None)
    active = []
    for row in prepared:
        dated = expiry_date(row.get("expiry"))
        if row["remaining_dte"] <= 0 or (row["expiry_authority"] != "exact_timestamp" and dated is not None and dated < as_of.date()):
            reason = "expired"
            result["counts"]["expired_rows"] += 1
        elif request["exclude_nearest_expiry"] and row["checkpoint_dte"] == nearest:
            reason = "nearest_expiry_excluded"
            result["counts"]["excluded_nearest_rows"] += 1
        else:
            active.append(row)
            continue
        if details:
            result["excluded_contracts"].append({"contract_id": row["contract_id"], "position_source": source_name,
                                                  "expiry": row.get("expiry"), "reason": reason})
    result["counts"]["selected_rows"] = len(active)
    result["counts"]["fallback_expiry_rows"] = sum(row["expiry_authority"] != "exact_timestamp" for row in active)
    if not active or not sum(row.get("accumulated_volume", 0) for row in active):
        result["reason"] = "No positive quantities remain after expiry and exclusion rules."
        return result
    if any(not 0 < row["scenario_iv"] <= 5.0 for row in active):
        result.update(status="invalid_scenario", reason="Every retained contract IV must remain above 0 and at most 500%; no clamping applied.")
        return result
    strikes = np.array([row["strike"] for row in active], dtype=float)
    dtes = np.array([row["remaining_dte"] for row in active], dtype=float)
    ivs = np.array([row["scenario_iv"] for row in active], dtype=float)
    models = np.array([row.get("pricing_model", "black_scholes") for row in active], dtype=object)
    multipliers = np.array([row.get("contract_multiplier") or checkpoint.multiplier for row in active], dtype=float)
    quantities = np.array([row["accumulated_volume"] for row in active], dtype=float)
    engine = IntradayGexEngine(checkpoint.multiplier)
    arguments = dict(spot_price=spot, strikes=strikes, days_to_expiry=dtes,
                     risk_free_rate=request["risk_free_rate"], implied_vols=ivs,
                     pricing_model=models, contract_multipliers=multipliers)
    if model == "directionalized_trade_volume":
        buys = np.array([row.get("directional_volume", {}).get("buy", 0) for row in active], dtype=float)
        sells = np.array([row.get("directional_volume", {}).get("sell", 0) for row in active], dtype=float)
        unknown = np.array([row.get("directional_volume", {}).get("unknown", row["accumulated_volume"]) for row in active], dtype=float)
        matrix = engine.compute_directionalized_gex_matrix(**arguments, buy_aggressor_vol=buys,
                                                          sell_aggressor_vol=sells, unknown_aggressor_vol=unknown)
        signed_quantities = sells - buys
        result["directional_coverage"] = matrix["directional_coverage"]
        if matrix["known_direction_volume"] <= 0 or matrix["directional_coverage"] < request["minimum_directional_coverage"]:
            result.update(status="insufficient_directional_coverage", reason="Known aggressor quantity is below the declared coverage requirement.")
            return result
    else:
        calls = np.array([row["option_type"] == "C" for row in active])
        matrix = engine.compute_intraday_gex_matrix(**arguments,
                                                   accumulated_call_vol=np.where(calls, quantities, 0),
                                                   accumulated_put_vol=np.where(calls, 0, quantities))
        signed_quantities = np.where(calls, quantities, -quantities)
    total = float(matrix["total_net_gex"])
    meaningful_wall = any(float(value) != 0 for value in matrix["net_gex"])
    summary = {
        "total_net_gex": total, "gamma_wall": float(matrix["gamma_wall_strike"]) if meaningful_wall else None,
        "zero_gamma": float(matrix["zero_gamma_strike"]), "strike_profile_flip": matrix["strike_profile_flip"],
        "net_sign": 1 if total > 0 else -1 if total < 0 else 0,
        "directional_coverage": matrix.get("directional_coverage"),
        "quantity": float(np.sum(quantities)), "contract_count": len(active),
        "pricing_models": matrix["pricing_models"], "units": matrix["units"],
    }
    result.update(status="available", reason=None, matrix=matrix, summary=summary)
    if details:
        gammas = engine.calculate_gamma(spot, strikes, dtes / 365.0, request["risk_free_rate"], ivs, pricing_model=models)
        for row, gamma, multiplier, signed in zip(active, gammas, multipliers, signed_quantities):
            result["contracts"].append({
                "contract_id": row["contract_id"], "provider": row.get("provider"), "strike": float(row["strike"]),
                "option_type": row["option_type"], "quantity": float(row["accumulated_volume"]),
                "position_source": source_name, "model": model, "pricing_model": row.get("pricing_model"),
                "expiry": row.get("expiry"), "expiry_timestamp": row.get("expiry_timestamp"),
                "expiry_authority": row["expiry_authority"], "remaining_dte": row["remaining_dte"],
                "base_iv": row["base_iv"], "scenario_iv": row["scenario_iv"], "iv_source": row.get("iv_source"),
                "multiplier": float(multiplier), "multiplier_source": "contract" if row.get("contract_multiplier") else "configured_fallback",
                "gamma": float(gamma), "signed_quantity": float(signed),
                "net_gex": float(signed * gamma * spot * spot * 0.01 * multiplier),
                "directional_volume": copy.deepcopy(row.get("directional_volume")),
                "direction_sources": sorted(row.get("direction_sources", [])),
            })
    return result


def _comparison(baseline: dict, scenario: dict) -> dict:
    if baseline["status"] != "available" or scenario["status"] != "available":
        return {"status": "not_evaluable", "net_gex_delta": None, "gamma_wall_delta": None, "net_sign_changed": None}
    left, right = baseline["summary"], scenario["summary"]
    return {"status": "available", "net_gex_delta": right["total_net_gex"] - left["total_net_gex"],
            "gamma_wall_delta": right["gamma_wall"] - left["gamma_wall"] if left["gamma_wall"] is not None and right["gamma_wall"] is not None else None,
            "net_sign_changed": left["net_sign"] != right["net_sign"]}


async def calculate(request: Mapping[str, Any]) -> dict:
    normalized = normalize_request(request)
    checkpoint = await _checkpoint(normalized)
    baseline, scenario = _state(checkpoint, _baseline(normalized)), _state(checkpoint, normalized)
    return _report("calculation", request=normalized, source=checkpoint.source,
                   baseline=baseline, scenario=scenario, comparison=_comparison(baseline, scenario))


async def surface(request: Mapping[str, Any]) -> dict:
    normalized = normalize_request(request, "surface")
    checkpoint = await _checkpoint(normalized)
    baseline_request = _baseline(normalized)
    points = []
    for time_index, minutes in enumerate(normalized["time_advances"]):
        for spot_index, shift in enumerate(normalized["spot_shifts"]):
            left = _state(checkpoint, {**baseline_request, "spot_shift": shift, "time_advance": minutes}, details=False)
            right = _state(checkpoint, {**normalized, "spot_shift": normalized["spot_shift"] + shift,
                                         "time_advance": normalized["time_advance"] + minutes}, details=False)
            a, b = left["summary"], right["summary"]
            points.append({"spot_index": spot_index, "time_index": time_index,
                           "baseline_status": left["status"], "scenario_status": right["status"],
                           "baseline_reason": left["reason"], "scenario_reason": right["reason"],
                           "baseline_total_net_gex": a["total_net_gex"] if a else None,
                           "scenario_total_net_gex": b["total_net_gex"] if b else None,
                           "baseline_gamma_wall": a["gamma_wall"] if a else None,
                           "scenario_gamma_wall": b["gamma_wall"] if b else None,
                           "delta_total_net_gex": b["total_net_gex"] - a["total_net_gex"] if a and b else None})
        # Keep bounded requests cancellable without changing numeric ordering.
        await asyncio.sleep(0)
    return _report("surface", request=normalized, source=checkpoint.source,
                   baseline=_state(checkpoint, baseline_request), scenario=_state(checkpoint, normalized),
                   axes={"spot_shifts": normalized["spot_shifts"],
                         "baseline_underlying_prices": [checkpoint.spot + value for value in normalized["spot_shifts"]],
                         "scenario_underlying_prices": [checkpoint.spot + normalized["spot_shift"] + value for value in normalized["spot_shifts"]],
                         "time_advances": normalized["time_advances"],
                         "scenario_time_advances": [normalized["time_advance"] + value for value in normalized["time_advances"]]},
                   points=points, interpretation="Two conditional surfaces with explicit underlying/time coordinates; no price trajectory is simulated.")


def _claim(baseline: dict, scenario: dict, comparison: dict | None, claim: str) -> tuple[str, str | None]:
    other = comparison if claim == "model_disagreement" else baseline
    if scenario["status"] != "available" or other is None or other["status"] != "available":
        return "not_evaluable", scenario["reason"] or (other or {}).get("reason") or "Comparison is unavailable"
    left, right = other["summary"], scenario["summary"]
    if claim in {"wall_change", "model_disagreement"} and (left["gamma_wall"] is None or right["gamma_wall"] is None):
        return "not_evaluable", "A zero exposure profile has no dominant gamma wall"
    changed = (left["gamma_wall"] != right["gamma_wall"] if claim == "wall_change" else
               left["net_sign"] != right["net_sign"] if claim == "net_sign" else
               left["gamma_wall"] != right["gamma_wall"] or left["net_sign"] != right["net_sign"])
    return "changed" if changed else "unchanged", None


async def search(request: Mapping[str, Any]) -> dict:
    normalized = normalize_request(request, "search")
    checkpoint = await _checkpoint(normalized)
    baseline = _state(checkpoint, _baseline(normalized))
    scales = {axis: max((abs(value) for value in normalized[f"{axis}_values"]), default=0) or 1.0 for axis in ("x", "y")}
    cells = []
    for y_index, y in enumerate(normalized["y_values"]):
        for x_index, x in enumerate(normalized["x_values"]):
            candidate = {**normalized, normalized["x_axis"]: x, normalized["y_axis"]: y}
            state = _state(checkpoint, candidate, details=False)
            comparison = _state(checkpoint, {**candidate, "model": normalized["comparison_model"]}, details=False) if normalized["claim"] == "model_disagreement" else None
            status, reason = _claim(baseline, state, comparison, normalized["claim"])
            cells.append({"x_index": x_index, "y_index": y_index, "x": x, "y": y,
                          "status": status, "reason": reason, "scenario_status": state["status"],
                          "summary": state["summary"], "comparison_summary": comparison["summary"] if comparison else None,
                          "distance": math.hypot(x / scales["x"], y / scales["y"])})
        await asyncio.sleep(0)
    broken = [cell for cell in cells if cell["status"] == "changed"]
    smallest = None
    if broken:
        smallest = copy.deepcopy(min(broken, key=lambda cell: (cell["distance"], cell["x"], cell["y"])))
        scenario_request = {key: normalized[key] for key in DEFAULTS}
        scenario_request.update({normalized["x_axis"]: smallest["x"], normalized["y_axis"]: smallest["y"]})
        smallest["request"] = normalize_request(scenario_request)
        smallest["scenario"] = _state(checkpoint, scenario_request)
    counts = {status: sum(cell["status"] == status for cell in cells) for status in ("changed", "unchanged", "not_evaluable")}
    return _report("search", request=normalized, source=checkpoint.source, baseline=baseline,
                   cells=cells, counts=counts, smallest_change=smallest,
                   outcome="break_found" if broken else "no_break_found" if counts["unchanged"] else "not_evaluable",
                   distance={"formula": "sqrt((x/x_scale)^2 + (y/y_scale)^2)", "x_scale": scales["x"], "y_scale": scales["y"],
                             "scales": "maximum absolute tested coordinate on each axis; zero-only axis uses 1",
                             "fixed_shocks": {key: normalized[key] for key in ("spot_shift", "iv_shift", "time_advance", "exclude_nearest_expiry") if key not in (normalized["x_axis"], normalized["y_axis"])},
                             "tie_break": "distance, then x, then y ascending", "global_minimum_claimed": False},
                   interpretation="Smallest normalized-distance changed point among the tested grid only. Untested points and not-evaluable cells carry no conclusion.")


def examples(name: str) -> dict:
    """Return executable example requests, never canned calculation outputs."""
    definitions = {
        "discovered-break": {"title": "Find a changed wall", "description": "Search ES spot/IV changes on the frozen multi-expiry chain.",
                             "operation": "search", "request": {"session": "wind-tunnel-lab", "x_values": [-100, -50, -25, 0, 25, 50, 100], "y_values": [-4, -2, 0, 2, 4]}},
        "no-break": {"title": "No break in a narrow grid", "description": "A narrow tested neighborhood may keep the same dominant wall; this is not a safety guarantee.",
                     "operation": "search", "request": {"session": "wind-tunnel-lab", "x_values": [-0.1, 0, 0.1], "y_values": [-0.01, 0, 0.01]}},
        "expiry-exclusion": {"title": "Remove the front expiry", "description": "Exclude ES contracts expiring at 14:00 UTC and reprice the remaining 20:00 UTC contracts; the source checkpoint stays intact.",
                             "operation": "calculate", "request": {"session": "wind-tunnel-lab", "exclude_nearest_expiry": True}},
    }
    if not isinstance(name, str) or name not in definitions:
        raise ValueError("Unknown Wind Tunnel example")
    selected = copy.deepcopy(definitions[name])
    selected["request"] = normalize_request(selected["request"], selected["operation"])
    return {"name": name, **selected}

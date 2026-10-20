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
from gex_terminal.pricing_assumptions import (build_pricing_assumptions, has_qualified_pricing,
                                             is_priced_contract, pricing_coverage)
from gex_terminal.replay_catalog import ReplaySession, bundled_replay_sessions
from gex_terminal.wind_tunnel_checkpoint import checkpoint_transport, validate_checkpoint


VERSION = 1
REQUEST_SCHEMA = "gex-terminal.wind-tunnel.request.v1"
MODELS = ("raw_trade_volume", "open_interest", "directionalized_trade_volume")
CHECKPOINT_MODEL = "terminal_selected"
CHECKPOINT_MODEL_LABEL = "Terminal selected proxy"
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
    "pricing_policy": "Explicit American futures CRR rows model early exercise using a finite lattice. Black-76 and Black-Scholes retain European exercise; American rows using them remain approximations. Missing exercise style remains unqualified.",
    "risk_free_rate_policy": "Configured continuously compounded flat rate, not an observed market curve; exact expiry uses ACT/365.",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def calculation_identity() -> dict:
    """Bind numeric behavior and replay projection to exact local implementation."""
    names = ("wind_tunnel.py", "wind_tunnel_checkpoint.py", "engine.py", "consumer.py", "contracts.py", "pricing_assumptions.py", "american_futures.py", "implied_volatility.py", "market_data_adapter.py", "replay_catalog.py")
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
    if content.get("source", {}).get("source_kind") == "terminal_checkpoint":
        result["limitations"]["source_kind"] = "offline_terminal_checkpoint"
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
    if not isinstance(request, Mapping) or operation not in {"calculate", "surface", "search", "models"}:
        raise ValueError("Expected a Wind Tunnel request object and supported operation")
    extra = {"calculate": set(), "surface": {"spot_shifts", "time_advances"},
             "search": {"x_axis", "y_axis", "x_values", "y_values", "claim", "comparison_model"},
             "models": {"grid"}}[operation]
    unknown = set(request) - (set(DEFAULTS) | extra | {"schema", "operation", "terminal_checkpoint"})
    if unknown:
        raise ValueError("Unknown Wind Tunnel fields: " + ", ".join(sorted(map(str, unknown))))
    if request.get("schema", REQUEST_SCHEMA) != REQUEST_SCHEMA or request.get("operation", operation) != operation:
        raise ValueError("Unsupported Wind Tunnel request schema or operation")
    result = {**DEFAULTS, **dict(request), "schema": REQUEST_SCHEMA, "operation": operation}
    checkpoint_source = request.get("terminal_checkpoint")
    if checkpoint_source is not None:
        artifact = validate_checkpoint(checkpoint_source)
        if request.get("session", "terminal-checkpoint") != "terminal-checkpoint":
            raise ValueError("Terminal checkpoint artifact requires session terminal-checkpoint")
        result.update(terminal_checkpoint=checkpoint_transport(artifact), session="terminal-checkpoint")
        for field in ("fallback_dte", "risk_free_rate"):
            if field not in request:
                result[field] = artifact["parameters"][field]
        if "model" not in request:
            result["model"] = CHECKPOINT_MODEL
        if request.get("checkpoint") not in (None, 0) or isinstance(request.get("checkpoint"), bool):
            raise ValueError("Terminal checkpoint has only index 0")
        result["checkpoint"] = 0
        valid_models = (*MODELS, CHECKPOINT_MODEL)
    else:
        if "terminal_checkpoint" in request or result["session"] == "terminal-checkpoint":
            raise ValueError("Terminal checkpoint session requires an embedded artifact")
        _session(result["session"])
        valid_models = MODELS
    if result["model"] not in valid_models:
        raise ValueError("Unknown quantity model")
    if result["checkpoint"] is not None and (type(result["checkpoint"]) is not int or result["checkpoint"] < 0):
        raise ValueError("checkpoint must be null or a nonnegative integer event index")
    if type(result["exclude_nearest_expiry"]) is not bool:
        raise ValueError("exclude_nearest_expiry must be boolean")
    for name in BOUNDS:
        result[name] = _number(result[name], name)
    if operation == "models":
        if type(result.setdefault("grid", False)) is not bool:
            raise ValueError("grid must be boolean")
        # This operation always compares the app default with the directional
        # proxy. A current single-model selector cannot silently change the pair.
        result["model"] = CHECKPOINT_MODEL if checkpoint_source is not None else "raw_trade_volume"
    elif operation == "surface":
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
        if result["comparison_model"] not in valid_models:
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
    if "terminal_checkpoint" in request:
        artifact = validate_checkpoint(request["terminal_checkpoint"])
        source = copy.deepcopy(artifact["source"])
        parameters = artifact["parameters"]
        source.update(session="terminal-checkpoint", source_kind="terminal_checkpoint", checkpoint=0,
                      source_sha256=artifact["sha256"], checkpoint_sha256=artifact["sha256"],
                      contract_multiplier=parameters["contract_multiplier"], source_ref=None,
                      rights_status="user_responsibility", redistributable=False,
                      later_events_excluded=0, checkpoint_transport_version=artifact["version"])
        return _Checkpoint(source, parameters["spot"], parse_market_datetime(source["as_of"]),
                           tuple(copy.deepcopy(artifact["rows"])), source["calculation_mode"], parameters["contract_multiplier"])
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
    original = [row for row in checkpoint.rows if row.get("terminal_selected")] if model == CHECKPOINT_MODEL else [row for row in checkpoint.rows if row.get("position_source") == source_name]
    result = {
        "status": "no_data", "reason": None, "model": model, "model_label": CHECKPOINT_MODEL_LABEL if model == CHECKPOINT_MODEL else MODEL_LABELS[model],
        "spot": spot, "as_of": _time(as_of), "matrix": None, "summary": None,
        "counts": {"source_rows": len(original), "selected_rows": 0, "expired_rows": 0,
                   "excluded_nearest_rows": 0, "fallback_expiry_rows": 0},
        "contracts": [], "excluded_contracts": [],
        "pricing_assumptions": build_pricing_assumptions(original or checkpoint.rows, request["risk_free_rate"]),
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
        row["base_iv"] = float(row.get("iv", 0.15)) if is_priced_contract(row) else None
        row["scenario_iv"] = row["base_iv"] + request["iv_shift"] / 100.0 if row["base_iv"] is not None else None
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
            result["excluded_contracts"].append({"contract_id": row["contract_id"], "position_source": row["position_source"],
                                                  "expiry": row.get("expiry"), "reason": reason})
    result["counts"]["selected_rows"] = len(active)
    if active:
        result["pricing_assumptions"] = build_pricing_assumptions(active, request["risk_free_rate"])
    result["counts"]["fallback_expiry_rows"] = sum(row["expiry_authority"] != "exact_timestamp" for row in active)
    if has_qualified_pricing(original):
        coverage = pricing_coverage(active)
        result["pricing_coverage"] = coverage
        result["counts"].update(priced_rows=coverage["priced_contract_count"],
                                unpriced_rows=coverage["unpriced_contract_count"])
    if not active or not sum(row.get("accumulated_volume", 0) for row in active):
        result["reason"] = "No positive quantities remain after expiry and exclusion rules."
        return result
    unpriced = [row for row in active if not is_priced_contract(row)]
    if details:
        result["excluded_contracts"].extend({
            "contract_id": row["contract_id"], "position_source": row["position_source"],
            "expiry": row.get("expiry"), "quantity": row["accumulated_volume"],
            "reason": "iv_unavailable", "iv_provenance": copy.deepcopy(row.get("iv_provenance")),
        } for row in unpriced)
    active = [row for row in active if is_priced_contract(row)]
    if not active or not sum(row.get("accumulated_volume", 0) for row in active):
        result["reason"] = "No retained option contracts have an available IV; raw quantities are retained."
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
    option_types = np.array([row["option_type"] for row in active], dtype=object)
    engine = IntradayGexEngine(checkpoint.multiplier)
    arguments = dict(spot_price=spot, strikes=strikes, days_to_expiry=dtes,
                     risk_free_rate=request["risk_free_rate"], implied_vols=ivs,
                     pricing_model=models, contract_multipliers=multipliers, option_types=option_types)
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
    matrix["pricing_assumptions"] = copy.deepcopy(result["pricing_assumptions"])
    matrix["risk_free_rate"] = request["risk_free_rate"]
    if "pricing_coverage" in result:
        matrix["pricing_coverage"] = copy.deepcopy(result["pricing_coverage"])
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
        gammas = engine.calculate_gamma(spot, strikes, dtes / 365.0, request["risk_free_rate"], ivs, pricing_model=models, option_types=option_types)
        for row, gamma, multiplier, signed in zip(active, gammas, multipliers, signed_quantities):
            result["contracts"].append({
                "contract_id": row["contract_id"], "provider": row.get("provider"), "strike": float(row["strike"]),
                "option_type": row["option_type"], "quantity": float(row["accumulated_volume"]),
                "exercise_style": row.get("exercise_style") or "unknown",
                "exercise_style_source": row.get("exercise_style_source") or "missing",
                "provider_cfi": row.get("provider_cfi"),
                "position_source": row["position_source"], "model": model, "pricing_model": row.get("pricing_model"),
                "expiry": row.get("expiry"), "expiry_timestamp": row.get("expiry_timestamp"),
                "expiry_authority": row["expiry_authority"], "remaining_dte": row["remaining_dte"],
                "base_iv": row["base_iv"], "scenario_iv": row["scenario_iv"], "iv_source": row.get("iv_source"),
                "iv_inversion_risk_free_rate": row.get("iv_inversion_risk_free_rate"),
                "multiplier": float(multiplier), "multiplier_source": "contract" if row.get("contract_multiplier") else "configured_fallback",
                "gamma": float(gamma), "signed_quantity": float(signed),
                "net_gex": float(signed * gamma * spot * spot * 0.01 * multiplier),
                "directional_volume": copy.deepcopy(row.get("directional_volume")),
                "direction_sources": sorted(row.get("direction_sources", [])),
            })
            if row.get("iv_provenance") is not None:
                result["contracts"][-1]["iv_provenance"] = copy.deepcopy(row["iv_provenance"])
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


def _model_agreement(states: list[dict]) -> dict:
    comparable = all(state["status"] == "available" for state in states)
    summaries = [state["summary"] for state in states]
    walls = [summary["gamma_wall"] if summary else None for summary in summaries]
    return {
        "status": "available" if comparable else "not_evaluable",
        "net_sign_matches": summaries[0]["net_sign"] == summaries[1]["net_sign"] if comparable else None,
        "gamma_wall_matches": walls[0] == walls[1] if comparable and all(wall is not None for wall in walls) else None,
        "models": [{"model": state["model"], "status": state["status"],
                    "net_sign": state["summary"]["net_sign"] if state["summary"] else None,
                    "gamma_wall": state["summary"]["gamma_wall"] if state["summary"] else None}
                   for state in states],
    }


def _model_grid_summary(model: str, label: str, cases: list[dict], baseline: dict) -> dict:
    available = [case for case in cases if case["status"] == "available"]
    complete = len(available) == len(cases)
    walls = sorted({case["gamma_wall_strike"] for case in available if case["gamma_wall_strike"] is not None})
    signs = {case["net_sign"] for case in available}
    totals = [case["total_net_gex"] for case in available]
    return {
        "model": model, "label": label, "case_count": len(cases),
        "evaluable_count": len(available), "not_evaluable_count": len(cases) - len(available),
        "status_counts": {status: sum(case["status"] == status for case in cases) for status in sorted({case["status"] for case in cases})},
        "net_sign_counts": {label: sum(case["net_sign"] == sign for case in available)
                            for label, sign in (("positive", 1), ("negative", -1), ("zero", 0))},
        "net_gex_range": {"min": min(totals), "max": max(totals)} if totals else None,
        "gamma_wall_strikes": walls,
        "gamma_wall_counts": [{"strike": wall, "count": sum(case["gamma_wall_strike"] == wall for case in available)} for wall in walls],
        # A partial grid cannot establish that a conclusion survives the grid.
        "net_sign_stable": len(signs) == 1 if complete else None,
        "gamma_wall_stable": len(walls) == 1 if complete and all(case["gamma_wall_strike"] is not None for case in available) else None,
        "baseline_net_sign_matches": all(case["net_sign"] == baseline["summary"]["net_sign"] for case in available)
            if complete and baseline["status"] == "available" else None,
    }


async def models(request: Mapping[str, Any]) -> dict:
    """Compare two quantity models on one immutable, offline checkpoint.

    The optional fixed grid deliberately ignores the current shock controls:
    every coordinate is absolute to the original checkpoint with all expiries.
    """
    normalized = normalize_request(request, "models")
    checkpoint = await _checkpoint(normalized)
    selected = (normalized["model"], "directionalized_trade_volume")
    results = []
    for model in selected:
        candidate = {**normalized, "model": model}
        baseline = _state(checkpoint, _baseline(candidate))
        scenario = _state(checkpoint, candidate)
        results.append({"model": model, "label": baseline["model_label"],
                        "baseline": baseline, "scenario": scenario,
                        "comparison": _comparison(baseline, scenario)})
        await asyncio.sleep(0)
    grid = None
    if normalized["grid"]:
        width = 100.0 if checkpoint.source["symbol"] == "NQ" else 25.0
        axes = {"spot_shifts": [-width, 0.0, width], "iv_shifts": [-1.0, 0.0, 1.0],
                "time_advances": [0.0, 30.0, 60.0]}
        cases, summaries = [], []
        for result in results:
            model_cases = []
            fixed = {**_baseline(normalized), "model": result["model"]}
            for shift in axes["spot_shifts"]:
                for iv in axes["iv_shifts"]:
                    for minutes in axes["time_advances"]:
                        state = _state(checkpoint, {**fixed, "spot_shift": shift, "iv_shift": iv,
                                                    "time_advance": minutes}, details=False)
                        summary, matrix = state["summary"], state["matrix"]
                        model_cases.append({
                            "model": result["model"], "spot_shift": shift, "iv_shift": iv, "time_advance": minutes,
                            "status": state["status"], "reason": state["reason"],
                            "total_net_gex": summary["total_net_gex"] if summary else None,
                            "net_sign": summary["net_sign"] if summary else None,
                            "gamma_wall_strike": summary["gamma_wall"] if summary else None,
                            "call_wall_strike": matrix.get("call_wall_strike") if matrix else None,
                            "put_wall_strike": matrix.get("put_wall_strike") if matrix else None,
                            "pricing_coverage": state.get("pricing_coverage"),
                            "directional_coverage": state.get("directional_coverage"), "counts": state["counts"],
                        })
                        # Yield at every cell for the server's cancellation and
                        # timeout boundary, including large saved checkpoints.
                        await asyncio.sleep(0)
            cases.extend(model_cases)
            summaries.append(_model_grid_summary(result["model"], result["label"], model_cases, result["baseline"]))
        grid = {"axes": axes, "case_count": len(cases), "cases": cases, "summaries": summaries,
                "interpretation": "Fixed Cartesian grid, absolute to the original zero-shock checkpoint; nearest-expiry exclusion is off. Unavailable cases do not establish stability. No future events or outcome probabilities are used."}
    return _report("models", request=normalized, source=checkpoint.source, models=results,
                   agreement={"baseline": _model_agreement([result["baseline"] for result in results]),
                              "scenario": _model_agreement([result["scenario"] for result in results]),
                              "interpretation": "Agreement compares conditional model outputs only. Models may use different quantity cohorts and may not be summed; neither reveals actual dealer positions or predictive validity."},
                   grid=grid)


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
            # A large checkpoint may make one grid row expensive. Yield after
            # every calculated cell so cancellation/timeouts remain responsive.
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
        if "terminal_checkpoint" in normalized:
            scenario_request["terminal_checkpoint"] = normalized["terminal_checkpoint"]
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


class TerminalCheckpointCore:
    """A server-local immutable source alongside the unchanged bundled catalog."""

    EXAMPLE_NAMES = EXAMPLE_NAMES
    calculation_identity = staticmethod(calculation_identity)
    examples = staticmethod(examples)

    def __init__(self, artifact: dict):
        self._artifact = validate_checkpoint(artifact)

    def _request(self, request: Mapping[str, Any]) -> dict:
        if not isinstance(request, Mapping):
            raise ValueError("Expected a Wind Tunnel request object")
        selected = request.get("session", "terminal-checkpoint")
        if selected == "terminal-checkpoint":
            supplied = request.get("terminal_checkpoint", self._artifact)
            return {**request, "session": selected, "terminal_checkpoint": supplied}
        return dict(request)

    def catalog(self) -> dict:
        result = catalog()
        source, parameters = self._artifact["source"], self._artifact["parameters"]
        defaults = {**DEFAULTS, "session": "terminal-checkpoint", "checkpoint": 0,
                    "model": CHECKPOINT_MODEL, "fallback_dte": parameters["fallback_dte"],
                    "risk_free_rate": parameters["risk_free_rate"]}
        labels = {**MODEL_LABELS, CHECKPOINT_MODEL: CHECKPOINT_MODEL_LABEL}
        entry = {"name": "terminal-checkpoint", "label": source["label"], "symbol": source["symbol"],
                 "description": "Frozen offline Terminal state; quantities and source time remain fixed.",
                 "contract_multiplier": parameters["contract_multiplier"], "source_ref": None,
                 "source_sha256": self._artifact["sha256"], "source_kind": "terminal_checkpoint",
                 "status": "available", "reason": None, "event_count": 1,
                 "first_as_of": source["as_of"], "last_as_of": source["as_of"], "as_of": source["as_of"],
                 "expiry_filter": source["expiry_filter"], "quality": source["quality"],
                 "data_mode": source["data_mode"], "synthetic": source["synthetic"],
                 "defaults": defaults, "terminal_checkpoint": checkpoint_transport(self._artifact),
                 "models": {model: {"label": label, "available_in_source": (
                     any(row["terminal_selected"] for row in self._artifact["rows"]) if model == CHECKPOINT_MODEL else
                     any(row["position_source"] == "open_interest" for row in self._artifact["rows"]) if model == "open_interest" else
                     any(row["directional_volume"]["buy"] + row["directional_volume"]["sell"] > 0 for row in self._artifact["rows"]) if model == "directionalized_trade_volume" else
                     any(row["position_source"] == "trade_volume" for row in self._artifact["rows"]))}
                            for model, label in labels.items()}}
        # Rebuild the report rather than retaining an invalid digest after mutation.
        return _report("catalog", sessions=[copy.deepcopy(entry), *result["sessions"]], models=labels,
                       bounds=result["bounds"], defaults=defaults, bundled_defaults=DEFAULTS,
                       examples=result["examples"], max_axis_points=41)

    def checkpoints(self, session: str) -> dict:
        if session != "terminal-checkpoint":
            return checkpoints(session)
        source, parameters = self._artifact["source"], self._artifact["parameters"]
        return _report("checkpoints", session=session, symbol=source["symbol"], source_sha256=self._artifact["sha256"],
                       checkpoints=[{"index": 0, "as_of": source["as_of"], "event_type": "terminal_checkpoint",
                                     "phase": None, "spot": parameters["spot"]}])

    async def calculate(self, request: Mapping[str, Any]) -> dict:
        return await calculate(self._request(request))

    async def models(self, request: Mapping[str, Any]) -> dict:
        return await models(self._request(request))

    async def surface(self, request: Mapping[str, Any]) -> dict:
        return await surface(self._request(request))

    async def search(self, request: Mapping[str, Any]) -> dict:
        return await search(self._request(request))

"""Point-in-time comparison of OI, raw-volume, and directionalized GEX proxies."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.contracts import parse_market_datetime
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import dumps_normalized_message, validate_normalized_message
from gex_terminal.snapshot import build_snapshot


POSITION_COMPARISON_SCHEMA = "gex-terminal.position-model-comparison.v1"


async def build_position_model_comparison(
    payload: Mapping[str, Any], *, config: GexConfig
) -> dict[str, Any]:
    """Compare position proxies while enforcing an explicit information cutoff."""
    as_of_text = str(payload.get("as_of") or "")
    as_of = parse_market_datetime(as_of_text)
    if as_of is None:
        raise ValueError("position comparison requires timezone-bearing as_of")
    messages = payload.get("messages")
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        raise ValueError("position comparison requires a messages array")

    underlying = []
    by_source: dict[str, list[Mapping[str, Any]]] = {
        "open_interest": [], "trade_volume": []
    }
    rejected_future = 0
    rejected_missing_time = 0
    for raw in messages:
        if not isinstance(raw, Mapping):
            continue
        message = dict(raw)
        validate_normalized_message(message)
        event_time = parse_market_datetime(message.get("event_time") or message.get("timestamp"))
        if event_time is None:
            rejected_missing_time += 1
            continue
        if event_time > as_of:
            rejected_future += 1
            continue
        if message.get("type") == "underlying_tick":
            underlying.append(message)
            continue
        source = str(message.get("position_source") or "trade_volume")
        if source in by_source:
            by_source[source].append(message)

    snapshots = {}
    for source, option_messages in by_source.items():
        snapshots[source] = await _snapshot_for_messages(
            [*underlying, *option_messages], config=config, as_of=as_of_text
        )
    raw_trade = _model_summary(snapshots.get("trade_volume"))
    oi = _model_summary(snapshots.get("open_interest"))
    directional = _directional_summary(snapshots.get("trade_volume"))
    comparable = all(summary.get("status") == "available" for summary in (oi, raw_trade))
    return {
        "schema": POSITION_COMPARISON_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_text,
        "vintage_control": {
            "future_messages_rejected": rejected_future,
            "missing_event_time_rejected": rejected_missing_time,
            "future_information_used": False,
        },
        "models": {
            "open_interest": oi,
            "raw_trade_volume": raw_trade,
            "directionalized_trade_volume": directional,
        },
        "differences": {
            "oi_minus_raw_total_net_gex": (
                oi["total_net_gex"] - raw_trade["total_net_gex"] if comparable else None
            ),
            "oi_raw_gamma_wall_distance": (
                abs(oi["gamma_wall"] - raw_trade["gamma_wall"]) if comparable else None
            ),
            "raw_directional_total_net_gex_delta": (
                directional["total_net_gex"] - raw_trade["total_net_gex"]
                if directional.get("status") == "available" and raw_trade.get("status") == "available"
                else None
            ),
        },
        "result": {
            "status": "available" if comparable else "insufficient_position_sources",
            "predictive_validity": "unmeasured",
            "models_may_not_be_summed": True,
        },
        "evidence_ceiling": (
            "point-in-time proxy comparison only; OI publication lag must be supplied "
            "in event_time and no source establishes dealer inventory"
        ),
    }


async def load_position_model_comparison(
    path: str | Path, *, config: GexConfig
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("position comparison input must be a JSON object")
    return await build_position_model_comparison(payload, config=config)


def write_position_model_comparison(
    report: Mapping[str, Any], output_path: str | Path
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("Position-model comparison output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


async def _snapshot_for_messages(
    messages: Sequence[Mapping[str, Any]], *, config: GexConfig, as_of: str
) -> dict[str, Any] | None:
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode="replay",
        expiry_filter=config.expiry_filter,
    )
    for message in sorted(
        messages, key=lambda row: str(row.get("event_time") or row.get("timestamp") or "")
    ):
        await consumer.update_market_state(dumps_normalized_message(dict(message)))
    if not consumer.current_spot or not consumer.contract_state:
        return None
    matrix = await consumer.process_latest_snapshot(
        days_to_expiry=config.days_to_expiry,
        expiry_filter=config.expiry_filter,
    )
    if "error" in matrix:
        return None
    return build_snapshot(
        symbol=config.symbol,
        spot=consumer.current_spot,
        session_open=consumer.session_open,
        days_to_expiry=config.days_to_expiry,
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        data=matrix,
        chain_state=consumer.chain_state,
        expiry_breakdown=await consumer.process_expiry_breakdown(
            days_to_expiry=config.days_to_expiry
        ),
        timestamp=as_of,
    )


def _model_summary(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"status": "unavailable"}
    metrics = snapshot["metrics"]
    return {
        "status": "available",
        "total_net_gex": metrics["total_net_gex"],
        "gamma_wall": metrics["gamma_wall"],
        "zero_gamma": metrics["zero_gamma"],
        "position_sources": snapshot["model"]["position_sources"],
        "contract_count": snapshot["model"]["selected_contract_count"],
    }


def _directional_summary(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    if not snapshot or not isinstance(snapshot.get("directionalized"), Mapping):
        return {"status": "unavailable"}
    model = snapshot["directionalized"]
    if model.get("status") != "available":
        return {
            "status": model.get("status", "unavailable"),
            "directional_coverage": model.get("directional_coverage", 0.0),
        }
    return {
        "status": "available",
        "total_net_gex": model["total_net_gex"],
        "gamma_wall": model["gamma_wall_strike"],
        "zero_gamma": model["zero_gamma_strike"],
        "directional_coverage": model["directional_coverage"],
        "participant_classification": "unobserved",
    }

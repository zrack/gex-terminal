"""Deterministic provider fault/state simulation without network access."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.databento_offline import replay_databento_records
from gex_terminal.engine import IntradayGexEngine


PROVIDER_FAULT_SCHEMA = "gex-terminal.provider-fault-certification.v1"


async def build_provider_fault_report(config: GexConfig) -> dict[str, Any]:
    base = _records()
    scenarios = {
        "sequence_gap": [base[0], base[1], base[2], {**base[2], "sequence": 4}],
        "duplicate_frame": [base[0], base[1], base[2], dict(base[2])],
        "reordered_prerequisites": [base[2], base[1], base[0]],
        "malformed_frame": [base[0], base[1], {**base[2], "price": "not-a-price"}],
        "unknown_frame": [base[0], base[1], {"record_type": "schema_added_later"}, base[2]],
        "partial_definition": [base[1], base[2]],
    }
    cases = []
    for name, records in scenarios.items():
        report = await replay_databento_records(
            records,
            config=config,
            source=f"fault-simulation:{name}",
        )
        cases.append({
            "name": name,
            "passed": _expectation(name, report, records),
            "input_frames": len(records),
            "coverage": report["coverage"],
            "feed_quality": report["feed_quality"],
            "errors": report["errors"],
            "software_path_certified": report["result"]["software_path_certified"],
        })
    lifecycle = _lifecycle_case(config)
    cases.append(lifecycle)
    return {
        "schema": PROVIDER_FAULT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": "databento",
        "network_used": False,
        "cases": cases,
        "result": {
            "passed": all(case["passed"] for case in cases),
            "passed_cases": sum(case["passed"] for case in cases),
            "total_cases": len(cases),
            "live_transport_certified": False,
            "predictive_validity": "unmeasured",
        },
        "evidence_ceiling": (
            "scripted adapter/consumer state behavior only; no authentication, entitlement, "
            "provider reconnect implementation, network latency, or payload-drift claim"
        ),
    }


def write_provider_fault_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("provider fault output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _expectation(name: str, report: Mapping[str, Any], records: list[Mapping[str, Any]]) -> bool:
    if name == "sequence_gap":
        sequences = [int(record["sequence"]) for record in records if record.get("record_type") == "trades"]
        gaps = sum(current > previous + 1 for previous, current in zip(sequences, sequences[1:]))
        return gaps == 1 and report["coverage"]["option_trades"] == 2
    if name == "duplicate_frame":
        return report["feed_quality"]["duplicate_message_count"] == 1
    if name == "reordered_prerequisites":
        return report["coverage"]["option_trades"] == 0
    if name == "malformed_frame":
        return (
            report["coverage"]["fallback_iv_ticks"] == 1
            and not report["result"]["software_path_certified"]
        )
    if name == "unknown_frame":
        return report["coverage"]["control_or_dropped_records"] >= 1
    if name == "partial_definition":
        return report["coverage"]["option_trades"] == 0
    return False


def _lifecycle_case(config: GexConfig) -> dict[str, Any]:
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        data_mode="live",
    )
    states = [consumer.connection_state]
    consumer.mark_connected()
    states.append(consumer.connection_state)
    consumer.mark_subscribed(3)
    consumer.mark_disconnected()
    states.append(consumer.connection_state)
    consumer.mark_reconnected()
    states.append(consumer.connection_state)
    consumer.mark_subscription_error()
    quality = consumer.feed_quality_snapshot()
    return {
        "name": "disconnect_reconnect_subscription_failure",
        "passed": (
            states == ["DISCONNECTED", "CONNECTED", "DISCONNECTED", "CONNECTED"]
            and quality["reconnect_count"] == 1
            and quality["subscription_status"] == "error"
        ),
        "states": states,
        "feed_quality": quality,
        "live_transport_certified": False,
    }


def _records() -> list[dict[str, Any]]:
    return [
        {
            "record_type": "definition",
            "instrument_id": 101,
            "raw_symbol": "ESU6 C6000",
            "asset": "ES",
            "underlying_id": 202,
            "strike_price": 6000,
            "expiration": "2026-09-18T20:00:00Z",
            "instrument_class": "C",
            "contract_multiplier": 50,
        },
        {
            "record_type": "mbp-1",
            "instrument_id": 202,
            "bid_px_00": 5999.75,
            "ask_px_00": 6000.25,
            "ts_event": "2026-08-19T16:00:00Z",
        },
        {
            "record_type": "trades",
            "instrument_id": 101,
            "price": 80.0,
            "size": 3,
            "side": "B",
            "sequence": 1,
            "ts_event": "2026-08-19T16:00:01Z",
        },
    ]

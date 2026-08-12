"""Offline Databento record replay and adversarial software-path certification."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.snapshot import build_snapshot
from gex_terminal.package_data import portable_package_data_reference


OFFLINE_REPLAY_SCHEMA = "gex-terminal.databento-offline-replay.v1"
OFFLINE_CERTIFICATION_SCHEMA = "gex-terminal.databento-offline-certification.v1"


def load_databento_records(path: str | Path) -> list[Any]:
    """Load local JSON/JSONL or SDK-readable DBN records without network access."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Databento replay file not found: {source}")
    lower_name = source.name.lower()
    if lower_name.endswith((".dbn", ".dbn.zst", ".dbz")):
        try:
            import databento as db
        except ModuleNotFoundError as exc:
            raise ValueError(
                'DBN replay requires the optional SDK: pip install -e ".[databento]"'
            ) from exc
        return list(db.DBNStore.from_file(source))

    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if source.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
            return list(payload["records"])
        if isinstance(payload, Mapping):
            return [dict(payload)]
        raise ValueError("Databento JSON replay must be an object or array")
    records = []
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on Databento replay line {line_number}") from exc
    return records


async def replay_databento_records(
    records: Iterable[Any],
    *,
    config: GexConfig,
    source: str = "memory",
    maximum_underlying_age_seconds: float = 2.0,
) -> dict[str, Any]:
    """Route local provider records through the same handler used by live mode."""
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode="replay",
        stale_after_seconds=config.stale_after_seconds,
        expiry_filter=config.expiry_filter,
    )
    adapter = DatabentoAdapter(
        consumer,
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        max_underlying_age_seconds=maximum_underlying_age_seconds,
        live_client_factory=lambda **_: None,
    )
    consumer.mark_connected()
    consumer.mark_subscribed(3)
    input_records = 0
    control_records = 0
    errors: list[str] = []
    for record in records:
        input_records += 1
        consumer.record_provider_frame()
        try:
            before = (
                adapter._definition_count
                + adapter._underlying_quote_count
                + adapter._option_trade_count
                + adapter._open_interest_count
            )
            await adapter._handle_live_record(record)
            after = (
                adapter._definition_count
                + adapter._underlying_quote_count
                + adapter._option_trade_count
                + adapter._open_interest_count
            )
            if after == before:
                control_records += 1
        except Exception as exc:
            consumer.record_provider_parse_error()
            errors.append(f"{type(exc).__name__}: {str(exc)[:300]}")

    snapshot = None
    if consumer.current_spot > 0 and consumer.contract_state:
        matrix = await consumer.process_latest_snapshot(
            days_to_expiry=config.days_to_expiry,
            expiry_filter=config.expiry_filter,
        )
        if "error" not in matrix:
            snapshot = build_snapshot(
                symbol=consumer.target_underlying,
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
            )

    timing_failures = (
        adapter._stale_underlying_count
        + adapter._future_underlying_count
        + adapter._missing_underlying_time_count
    )
    software_path_certified = bool(
        input_records
        and adapter._definition_count
        and adapter._underlying_quote_count
        and adapter._option_trade_count
        and adapter._inverted_iv_count
        and adapter._iv_fallback_count == 0
        and timing_failures == 0
        and adapter._dropped_underlying_mismatch_count == 0
        and adapter._crossed_underlying_book_count == 0
        and adapter._incomplete_underlying_book_count == 0
        and not errors
        and snapshot is not None
    )
    return {
        "schema": OFFLINE_REPLAY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source,
        "input": {"records": input_records, "network_used": False},
        "coverage": {
            "definitions": adapter._definition_count,
            "underlying_quotes": adapter._underlying_quote_count,
            "option_trades": adapter._option_trade_count,
            "open_interest_updates": adapter._open_interest_count,
            "control_or_dropped_records": control_records,
            "inverted_iv_ticks": adapter._inverted_iv_count,
            "fallback_iv_ticks": adapter._iv_fallback_count,
        },
        "temporal_integrity": {
            "maximum_underlying_age_ms": maximum_underlying_age_seconds * 1000.0,
            "stale_underlying_prices": adapter._stale_underlying_count,
            "future_underlying_prices": adapter._future_underlying_count,
            "missing_event_times": adapter._missing_underlying_time_count,
            "underlying_contract_mismatches": adapter._dropped_underlying_mismatch_count,
            "crossed_underlying_books": adapter._crossed_underlying_book_count,
            "incomplete_underlying_books": adapter._incomplete_underlying_book_count,
        },
        "feed_quality": consumer.feed_quality_snapshot(),
        "snapshot": snapshot,
        "result": {
            "software_path_certified": software_path_certified,
            "live_transport_certified": False,
            "predictive_validity": "unmeasured",
        },
        "errors": list(dict.fromkeys(errors)),
    }


async def replay_databento_file(
    path: str | Path,
    *,
    config: GexConfig,
    maximum_underlying_age_seconds: float = 2.0,
) -> dict[str, Any]:
    return await replay_databento_records(
        load_databento_records(path),
        config=config,
        source=portable_package_data_reference(path),
        maximum_underlying_age_seconds=maximum_underlying_age_seconds,
    )


async def build_offline_databento_certification(config: GexConfig) -> dict[str, Any]:
    """Run deterministic adversarial cases without claiming live certification."""
    base = _base_records()
    cases = {
        "aligned_happy_path": base,
        "trade_before_definition": [base[2], base[0], base[1]],
        "trade_before_underlying": [base[0], base[2], base[1]],
        "stale_underlying": [base[0], base[1], {**base[2], "ts_event": "2026-08-06T16:00:04Z"}],
        "future_underlying": [base[0], {**base[1], "ts_event": "2026-08-06T16:00:02Z"}, base[2]],
        "wrong_underlying_contract": [
            {**base[0], "underlying_id": 303}, base[1], base[2]
        ],
        "invalid_option_price": [base[0], base[1], {**base[2], "price": 99999.0}],
        "unknown_control_record": [base[0], {"record_type": "symbol_mapping"}, base[1], base[2]],
        "duplicate_sequence": [base[0], base[1], base[2], dict(base[2])],
        "crossed_underlying_book": [
            base[0], {**base[1], "bid_px_00": 6001.0, "ask_px_00": 6000.0}, base[2]
        ],
        "one_sided_underlying_book": [
            base[0], {k: v for k, v in base[1].items() if k != "ask_px_00"}, base[2]
        ],
        "provider_error_record": [base[0], {"record_type": "error", "message": "test"}],
    }
    results = {}
    for name, records in cases.items():
        results[name] = await replay_databento_records(
            records,
            config=config,
            source=f"adversarial:{name}",
        )
    expectations = {
        "aligned_happy_path": lambda r: r["result"]["software_path_certified"],
        "trade_before_definition": lambda r: r["coverage"]["option_trades"] == 0,
        "trade_before_underlying": lambda r: r["coverage"]["fallback_iv_ticks"] == 1,
        "stale_underlying": lambda r: r["temporal_integrity"]["stale_underlying_prices"] == 1,
        "future_underlying": lambda r: r["temporal_integrity"]["future_underlying_prices"] == 1,
        "wrong_underlying_contract": lambda r: r["temporal_integrity"]["underlying_contract_mismatches"] == 1,
        "invalid_option_price": lambda r: r["coverage"]["fallback_iv_ticks"] == 1,
        "unknown_control_record": lambda r: r["coverage"]["option_trades"] == 1,
        "duplicate_sequence": lambda r: r["feed_quality"]["duplicate_message_count"] == 1,
        "crossed_underlying_book": lambda r: r["temporal_integrity"]["crossed_underlying_books"] == 1,
        "one_sided_underlying_book": lambda r: r["temporal_integrity"]["incomplete_underlying_books"] == 1,
        "provider_error_record": lambda r: bool(r["errors"]),
    }
    case_rows = [
        {
            "name": name,
            "passed": bool(expectations[name](result)),
            "software_path_certified": result["result"]["software_path_certified"],
            "coverage": result["coverage"],
            "temporal_integrity": result["temporal_integrity"],
        }
        for name, result in results.items()
    ]
    return {
        "schema": OFFLINE_CERTIFICATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cases": case_rows,
        "result": {
            "passed": all(row["passed"] for row in case_rows),
            "software_path_certified": all(row["passed"] for row in case_rows),
            "live_transport_certified": False,
            "predictive_validity": "unmeasured",
        },
        "evidence_ceiling": (
            "deterministic adapter, temporal-integrity, and fail-closed behavior only; "
            "no authentication, entitlement, latency, payload-drift, or market-edge claim"
        ),
    }


def write_offline_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {".json", ""}:
        raise ValueError("Offline Databento reports currently require a .json path")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _base_records() -> list[dict[str, Any]]:
    return [
        {
            "record_type": "definition", "instrument_id": 101,
            "raw_symbol": "ESQ6 C6000", "asset": "ES", "underlying_id": 202,
            "strike_price": 6000.0, "instrument_class": "C",
            "expiration": "2026-08-20T20:00:00Z", "contract_multiplier": 50,
        },
        {
            "record_type": "mbp-1", "instrument_id": 202,
            "bid_px_00": 5999.75, "ask_px_00": 6000.25,
            "ts_event": "2026-08-06T16:00:00Z",
        },
        {
            "record_type": "trades", "instrument_id": 101,
            "price": 105.0, "size": 7, "side": "B", "sequence": 1,
            "ts_event": "2026-08-06T16:00:01Z",
        },
    ]

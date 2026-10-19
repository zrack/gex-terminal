"""Convert a bounded, local Databento historical sample into an app replay.

This tool never opens a provider connection. It accepts separate schema files,
preserves provider event time, and uses the production adapter and capture format.
Run from the checkout with ``python -m scripts.databento_trial_replay --help``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import warnings
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gex_terminal.adapters.databento import (
    DATABENTO_UNDEF_TIMESTAMP,
    DatabentoAdapter,
    _record_kind,
    _record_mapping,
)
from gex_terminal.capture_governance import capture_policy_identity, load_capture_policy
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.contracts import parse_market_datetime
from gex_terminal.databento_offline import replay_databento_records
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.session_capture import CapturedSessionWriter, RecordingConsumerProxy


MAX_INPUT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_RECORDS = 200_000
HARD_MAX_RECORDS = 1_000_000
_KINDS = {
    "definitions": "definition", "underlying": "underlying_quote",
    "trades": "option_trade", "statistics": "statistics",
}
_PRIORITY = {"definition": 0, "underlying_quote": 1, "option_trade": 2, "statistics": 3}


def _historical_underlying_record(record: Any) -> Any:
    """Adapt interval BBO locally; its last-trade time is not the quote time.

    Databento BBO-1s is available at ``ts_recv``, the interval end. Applying its
    book at ``ts_event`` (the last sale time) would make future prices visible.
    Keep the live adapter's MBP-1 subscription and record contract unchanged.
    """
    if isinstance(record, Mapping):
        schema = str(record.get("record_type") or record.get("schema") or "").lower()
        if schema != "bbo-1s":
            return record
        interval_end = record.get("ts_recv")
        last_trade_event = record.get("ts_event")
    else:
        if type(record).__name__ != "BBOMsg" or int(getattr(record, "rtype", -1)) != 195:
            return record
        interval_end = getattr(record, "ts_recv", None)
        last_trade_event = getattr(record, "ts_event", None)
    if interval_end in (None, ""):
        raise ValueError("BBO-1s underlying records require provider interval-end timestamps (ts_recv)")
    # Validate time before relabelling it, preserving integer nanosecond precision.
    _event_ns({"ts_event": interval_end})
    values = _record_mapping(record, "underlying_quote")
    # BBO.price is the last sale, which can be old and differs from the midpoint.
    for field in ("price", "close", "last_px", "last_price", "lastPrice"):
        values.pop(field, None)
    values.update({
        "record_type": "underlying_quote",
        "source_schema": "bbo-1s",
        "ts_event": interval_end,
        "ts_recv": interval_end,
        "underlying_price_source": "databento_bbo_1s_midpoint",
        "quote_time_basis": "interval_end",
        "provider_last_trade_ts_event": last_trade_event,
    })
    return values


def _event_ns(record: Any) -> int | None:
    """Sort nanosecond timestamps without converting their integer part to float."""
    value = record.get("ts_event") if isinstance(record, Mapping) else getattr(record, "ts_event", None)
    if value in (None, ""):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value < DATABENTO_UNDEF_TIMESTAMP:
            return value
        raise ValueError("input contains an undefined or negative event timestamp")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("input event timestamps must include a timezone")
        parsed = value.astimezone(timezone.utc)
        fraction = parsed.microsecond * 1000
    elif isinstance(value, str):
        if not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value):
            raise ValueError("input event timestamps must include a timezone")
        parsed = parse_market_datetime(value)
        if parsed is None:
            raise ValueError("input contains an invalid event timestamp")
        match = re.search(r"\.(\d+)(?:Z|[+-]\d{2}:\d{2})$", value)
        if match and len(match[1]) > 9:
            raise ValueError("input timestamp precision exceeds nanoseconds")
        fraction = int(match[1].ljust(9, "0")) if match else 0
    else:
        raise ValueError("input contains an unsupported event timestamp")
    delta = parsed.replace(microsecond=0) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + fraction


def _load_file(path: Path, role: str, remaining: int) -> list[Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{role} input must be a regular local file")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{role} input exceeds the 64 MiB file limit")
    lower = path.name.lower()
    store = None
    if lower.endswith((".dbn", ".dbn.zst", ".dbz")):
        try:
            import databento as db
        except ModuleNotFoundError:
            raise ValueError('DBN input requires the optional SDK: pip install -e ".[databento]"') from None
        store = db.DBNStore.from_file(path)
        iterator = iter(store)
    elif path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping):
            payload = payload.get("records", [payload])
        if not isinstance(payload, list):
            raise ValueError(f"{role} JSON must contain records")
        iterator = iter(payload)
    else:
        def json_lines():
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if line.strip() and not line.lstrip().startswith("#"):
                        yield json.loads(line)
        iterator = iter(json_lines())
    records = []
    try:
        with warnings.catch_warnings():
            # A truncated DBN stream must not silently become a complete capture.
            warnings.filterwarnings("error", message="DBN file is truncated.*")
            for record in iterator:
                if len(records) >= remaining:
                    raise ValueError("input exceeds --max-records; request a shorter historical window")
                if role == "underlying":
                    record = _historical_underlying_record(record)
                if _record_kind(record) != _KINDS[role]:
                    raise ValueError(f"{role} input contains a record from another schema")
                if role != "definitions" and _event_ns(record) is None:
                    raise ValueError(f"{role} records require provider event timestamps")
                records.append(record)
    except Warning as exc:
        raise ValueError(f"{role} DBN input is truncated") from exc
    finally:
        if hasattr(iterator, "close"):
            iterator.close()
        if store is not None:
            store.reader.close()
    if not records:
        raise ValueError(f"{role} input is empty")
    return records


def prepare_records(
    files: Mapping[str, str | Path], *, symbol: str, max_records: int = DEFAULT_MAX_RECORDS,
) -> tuple[list[Any], dict[str, Any]]:
    """Validate one futures identity and merge a declared option subset by time."""
    if symbol not in {"ES", "NQ"}:
        raise ValueError("symbol must be ES or NQ")
    if isinstance(max_records, bool) or not 1 <= max_records <= HARD_MAX_RECORDS:
        raise ValueError("max_records must be from 1 through 1000000")
    if not {"definitions", "underlying", "trades"} <= set(files) or set(files) - set(_KINDS):
        raise ValueError("definitions, underlying, and trades are required schema files")
    loaded: dict[str, list[Any]] = {}
    identities = []
    total = 0
    total_bytes = 0
    for role, source in files.items():
        path = Path(source)
        records = _load_file(path, role, max_records - total)
        total += len(records)
        total_bytes += path.stat().st_size
        if total_bytes > MAX_INPUT_BYTES:
            raise ValueError("combined inputs exceed the 64 MiB limit")
        loaded[role] = records
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        identities.append({"role": role, "file": path.name, "sha256": digest.hexdigest(), "records": len(records)})

    future_ids = {
        _record_mapping(record, "underlying_quote").get("instrument_id")
        for record in loaded["underlying"]
    }
    if len(future_ids) != 1 or next(iter(future_ids)) in (None, 0, "", "0"):
        raise ValueError("underlying input must identify exactly one futures contract")
    future_id = str(next(iter(future_ids)))
    eligible = set()
    excluded_definitions = 0
    for record in loaded["definitions"]:
        metadata = DatabentoAdapter._normalize_definition_record(_record_mapping(record, "definition"))
        if metadata is None:  # The definition request can also include futures metadata.
            continue
        if metadata["underlying"] != symbol:
            raise ValueError("definition input contains options for another underlying root")
        if str(metadata.get("underlying_id")) == future_id:
            eligible.add(str(metadata["instrument_id"]))
        else:
            excluded_definitions += 1
    if not eligible:
        raise ValueError("no option definitions match the underlying futures instrument ID")

    selected: list[Any] = []
    excluded_events = 0
    for role, records in loaded.items():
        for record in records:
            values = _record_mapping(record, _KINDS[role])
            if role == "definitions":
                if str(values.get("instrument_id")) not in eligible:
                    continue
            elif role != "underlying" and str(values.get("instrument_id")) not in eligible:
                excluded_events += 1
                continue
            selected.append(record)
    # Untimed decoded definitions are static metadata; all dated updates retain
    # their event time so future metadata cannot be applied to earlier trades.
    selected.sort(key=lambda record: (
        _event_ns(record) if _event_ns(record) is not None else -1,
        _PRIORITY[_record_kind(record)],
    ))
    underlying_schemas = sorted({
        str(_record_mapping(record, "underlying_quote").get("source_schema") or "mbp-1")
        for record in loaded["underlying"]
    })
    provenance = {
        "mode": "replay", "provider": "databento", "symbol": symbol,
        "source_kind": "historical_databento", "network_used": False,
        "transformation": "local schema merge and production-adapter normalization",
        "inputs": identities,
        "underlying_schema": underlying_schemas[0] if len(underlying_schemas) == 1 else "mixed",
        "underlying_schemas": underlying_schemas,
        "underlying_sampling": (
            "one-second interval-end BBO midpoint; last-sale ts_event retained separately"
            if underlying_schemas == ["bbo-1s"] else "provider quote events"
        ),
        "subset": {
            "underlying_instrument_id": future_id,
            "eligible_option_contracts": len(eligible),
            "excluded_other_future_definitions": excluded_definitions,
            "excluded_option_events": excluded_events,
            "complete_chain_coverage": "unverified",
            "position_inputs": "trade_volume_and_available_statistics" if "statistics" in files else "trade_volume_only",
        },
        "ordering": (
            "provider ts_event nanoseconds, except BBO-1s quotes use ts_recv interval end; "
            "definition/quote/trade/statistics tie priority; stable input order"
        ),
    }
    return selected, provenance


class _HistoricalRecordingConsumer(RecordingConsumerProxy):
    async def update_market_state(self, raw_message: str) -> bool:
        # Databento updates its quote cache only after the consumer accepts a
        # quote. Preserve that result while using the existing capture writer.
        await self.writer.append(raw_message)
        return await self.consumer.update_market_state(raw_message)


def _private_json(path: Path, payload: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")


async def convert_sample(
    *, files: Mapping[str, str | Path], symbol: str, output_dir: str | Path,
    capture_policy: str | Path | None = None, max_records: int = DEFAULT_MAX_RECORDS,
    max_underlying_age: float = 2.0, risk_free_rate: float = 0.045,
) -> dict[str, Path]:
    if not math.isfinite(max_underlying_age) or max_underlying_age < 0:
        raise ValueError("max_underlying_age must be finite and nonnegative")
    records, source = prepare_records(files, symbol=symbol, max_records=max_records)
    if capture_policy is not None:
        source["capture_policy"] = capture_policy_identity(load_capture_policy(capture_policy))
    config = GexConfig(
        symbol=symbol, symbols=(symbol,), data_mode="replay", data_provider="databento",
        contract_multiplier=50 if symbol == "ES" else 20, risk_free_rate=risk_free_rate,
        days_to_expiry=0.25, refresh_interval_seconds=1, stale_after_seconds=10,
        replay_path="", replay_delay_seconds=0, tradovate_environment="demo",
    )
    output = Path(output_dir)
    capture_path = output / f"{symbol.lower()}.gex-session.jsonl"
    report_path = output / f"{symbol.lower()}-replay-report.json"
    for target in (capture_path, Path(f"{capture_path}.partial"), report_path):
        if target.exists() or target.is_symlink():
            raise FileExistsError("output already exists; use a new output directory")
    report = await replay_databento_records(
        records, config=config, source="historical_databento",
        maximum_underlying_age_seconds=max_underlying_age,
    )
    report["historical_provenance"] = source
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    _private_json(report_path, report)
    if report["errors"] or report["snapshot"] is None:
        raise ValueError(f"historical sample did not produce a usable snapshot; inspect {report_path}")

    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier), target_underlying=symbol,
        risk_free_rate=risk_free_rate, data_mode="replay",
    )
    writer = CapturedSessionWriter(
        capture_path, source=source,
        model_inputs={"days_to_expiry": config.days_to_expiry, "risk_free_rate": risk_free_rate,
                      "contract_multiplier": config.contract_multiplier, "expiry_filter": "all"},
        label=f"Databento historical {symbol} bounded sample",
    )
    await writer.start()
    adapter = DatabentoAdapter(
        _HistoricalRecordingConsumer(consumer, writer), target_underlying=symbol,
        risk_free_rate=risk_free_rate, max_underlying_age_seconds=max_underlying_age,
        live_client_factory=lambda **_: None,
    )
    try:
        for record in records:
            consumer.record_provider_frame()
            await adapter._handle_live_record(record)
        await writer.finalize(feed_quality=consumer.feed_quality_snapshot())
    except BaseException as exc:
        await writer.abort(f"historical conversion failed: {type(exc).__name__}")
        raise
    return {"capture": capture_path, "report": report_path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definitions", required=True, type=Path)
    parser.add_argument("--underlying", required=True, type=Path)
    parser.add_argument("--trades", required=True, type=Path)
    parser.add_argument("--statistics", type=Path)
    parser.add_argument("--symbol", required=True, choices=("ES", "NQ"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--capture-policy", type=Path)
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS)
    parser.add_argument("--max-underlying-age", type=float, default=2.0)
    parser.add_argument("--risk-free-rate", type=float, default=0.045)
    args = parser.parse_args()
    files = {role: getattr(args, role) for role in _KINDS if getattr(args, role) is not None}
    try:
        result = asyncio.run(convert_sample(
            files=files, symbol=args.symbol, output_dir=args.output_dir,
            capture_policy=args.capture_policy, max_records=args.max_records,
            max_underlying_age=args.max_underlying_age, risk_free_rate=args.risk_free_rate,
        ))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print(f"Historical replay: {result['capture']}")
    print(f"Data-quality report: {result['report']}")
    print("Historical subset only; live transport uncertified; predictive validity unmeasured.")


if __name__ == "__main__":
    main()

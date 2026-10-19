"""Convert a full historical ES/NQ session with a disk-backed causal merge.

No provider connection is opened. Native input files remain unchanged. One
production adapter/consumer owns the whole session, including UTC midnight.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
import warnings

from gex_terminal.adapters.databento import DatabentoAdapter, _record_kind, _record_mapping
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.pricing_assumptions import pricing_coverage
from gex_terminal.saved_workspace import restrict_network_to_loopback
from gex_terminal.session_capture import CapturedSessionWriter
from scripts.databento_trial_replay import (
    _event_ns, _historical_underlying_record, _HistoricalRecordingConsumer, _private_json,
)

MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_RECORDS = 5_000_000
MAX_DECODED_BYTES = 2 * 1024 * 1024 * 1024
KINDS = {"definitions": "definition", "underlying": "underlying_quote", "trades": "option_trade"}
PRIORITIES = {"definitions": 0, "underlying": 1, "trades": 2}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _json_value(value):
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "item"):
        return value.item()
    # SDK pretty numeric fields can be Decimal; preserve their exact decimal
    # text rather than converting native fixed-price identity through float.
    if type(value).__name__ == "Decimal":
        return str(value)
    raise TypeError("Unsupported decoded provider field")


def _json_safe(value):
    """Keep native undefined numeric fields absent, without inventing prices."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def iter_input(path: Path, role: str):
    """Yield one decoded record at a time, rejecting truncated native files."""
    store = None
    if path.name.lower().endswith((".dbn", ".dbn.zst", ".dbz")):
        import databento as db
        store = db.DBNStore.from_file(path)
        iterator = iter(store)
    elif path.suffix.lower() == ".jsonl":
        def lines():
            with path.open(encoding="utf-8") as stream:
                while line := stream.readline(1024 * 1024 + 1):
                    if len(line) > 1024 * 1024:
                        raise ValueError("Decoded provider record exceeds 1 MiB")
                    if line.strip():
                        yield json.loads(line)
        iterator = lines()
    else:
        raise ValueError("Full-session inputs must be native DBN or decoded JSONL")
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message="DBN file is truncated.*")
            for record in iterator:
                if role == "underlying":
                    record = _historical_underlying_record(record)
                    if not isinstance(record, dict) or record.get("source_schema") != "bbo-1s":
                        raise ValueError("Full-session underlying input must be interval-end BBO-1s")
                if _record_kind(record) != KINDS[role]:
                    raise ValueError(f"{role} input contains another schema")
                yield record
    except Warning as exc:
        raise ValueError(f"{role} native input is truncated") from exc
    finally:
        if hasattr(iterator, "close"):
            iterator.close()
        if store is not None:
            store.reader.close()


def build_index(files: dict[str, Path], symbol: str, output: Path, *, max_records=MAX_RECORDS) -> tuple[sqlite3.Connection, dict]:
    if symbol not in {"ES", "NQ"} or set(files) != set(KINDS):
        raise ValueError("ES/NQ definitions, underlying and trades are required")
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
        raise ValueError("Full-session raw record limit must be from 1 through 5000000")
    if any(path.is_symlink() or not path.is_file() for path in files.values()):
        raise ValueError("Native inputs must be ordinary local files")
    if sum(path.stat().st_size for path in files.values()) > MAX_INPUT_BYTES:
        raise ValueError("Combined native inputs exceed 512 MiB")
    database = output / "index.sqlite"
    if database.exists() or database.is_symlink():
        raise FileExistsError("Full-session index already exists")
    connection = sqlite3.connect(database)
    database.chmod(0o600)
    try:
        connection.execute("PRAGMA cache_size=-16384")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, ns INTEGER, priority INTEGER, role TEXT, payload TEXT, instrument_id TEXT, quantity INTEGER, trade_id TEXT, selected INTEGER DEFAULT 0)")
        connection.execute("CREATE TABLE contracts(instrument_id TEXT PRIMARY KEY, underlying_id TEXT)")
        identities, future_ids = [], set()
        total = decoded = 0
        for role, path in files.items():
            before = digest(path)
            count = 0
            for record in iter_input(path, role):
                total += 1
                count += 1
                if total > max_records:
                    raise ValueError("Full-session raw record limit exceeded")
                ns = _event_ns(record)
                if ns is None:
                    raise ValueError("Full-session records, including definitions, require authoritative event time")
                values = _record_mapping(record, KINDS[role])
                values["record_type"] = KINDS[role]
                iid = str(values.get("instrument_id", ""))
                if role == "underlying":
                    if iid in {"", "0", "None"}:
                        raise ValueError("Underlying input requires a futures identity")
                    future_ids.add(iid)
                elif role == "definitions":
                    metadata = DatabentoAdapter._normalize_definition_record(values)
                    if metadata is not None:
                        if metadata["underlying"] != symbol:
                            raise ValueError("Definition contains another underlying root")
                        future = str(metadata.get("underlying_id"))
                        previous = connection.execute("SELECT underlying_id FROM contracts WHERE instrument_id=?", (iid,)).fetchone()
                        if previous is not None and previous[0] != future:
                            raise ValueError("Option underlying identity changed during the session")
                        connection.execute("INSERT OR IGNORE INTO contracts VALUES(?,?)", (iid, future))
                payload = json.dumps(_json_safe(values), default=_json_value, allow_nan=False, separators=(",", ":"))
                if len(payload.encode()) > 1024 * 1024:
                    raise ValueError("Decoded provider record exceeds 1 MiB")
                decoded += len(payload.encode())
                if decoded > MAX_DECODED_BYTES:
                    raise ValueError("Decoded native input exceeds 2 GiB")
                quantity = int(values.get("size", 0)) if role == "trades" else 0
                connection.execute("INSERT INTO records(ns,priority,role,payload,instrument_id,quantity,trade_id) VALUES(?,?,?,?,?,?,?)",
                                   (ns if ns is not None else -1, PRIORITIES[role], role, payload, iid, quantity,
                                    values.get("_provider_trade_event_id")))
                if total % 10_000 == 0:
                    connection.commit()
                    print(f"Indexed {total:,} {symbol} native records...", file=sys.stderr, flush=True)
            if not count or digest(path) != before:
                raise ValueError("Native input is empty or changed during indexing")
            identities.append({"role": role, "file": str(path.absolute()), "sha256": before, "records": count})
        if len(future_ids) != 1:
            raise ValueError("Full-session quotes must identify exactly one matched futures contract")
        future_id = next(iter(future_ids))
        eligible = connection.execute("SELECT COUNT(*) FROM contracts WHERE underlying_id=?", (future_id,)).fetchone()[0]
        if not eligible:
            raise ValueError("No option definitions match the quoted futures contract")
        connection.execute("UPDATE records SET selected=1 WHERE role='underlying' OR instrument_id IN (SELECT instrument_id FROM contracts WHERE underlying_id=?)", (future_id,))
        connection.execute("CREATE INDEX records_order ON records(selected,ns,priority,id)")
        connection.commit()
        excluded_definitions = connection.execute("SELECT COUNT(*) FROM records WHERE selected=0 AND role='definitions'").fetchone()[0]
        other_future_definitions = connection.execute("SELECT COUNT(*) FROM records WHERE selected=0 AND role='definitions' AND instrument_id IN (SELECT instrument_id FROM contracts WHERE underlying_id!=?)", (future_id,)).fetchone()[0]
        excluded_events = connection.execute("SELECT COUNT(*) FROM records WHERE selected=0 AND role='trades'").fetchone()[0]
        source = {"mode": "replay", "provider": "databento", "symbol": symbol,
                  "source_kind": "historical_databento_full_session", "network_used": False,
                  "inputs": identities, "underlying_schema": "bbo-1s",
                  "underlying_sampling": "one-second interval-end BBO midpoint; last-sale ts_event retained separately",
                  "subset": {"underlying_instrument_id": future_id, "eligible_option_contracts": eligible,
                             "excluded_definitions": excluded_definitions,
                             "excluded_other_future_option_definitions": other_future_definitions,
                             "excluded_option_events": excluded_events,
                             "complete_chain_coverage": "unverified", "position_inputs": "trade_volume_only"},
                  "ordering": "provider event nanoseconds; BBO interval-end availability; definition/quote/trade priority; stable native file order"}
        return connection, source
    except BaseException:
        connection.close()
        raise


async def convert_session(*, files: dict[str, Path], symbol: str, output_dir: Path,
                          start: str, end: str, risk_free_rate=.045,
                          max_records=MAX_RECORDS, max_underlying_age=2.) -> dict:
    start_ns, end_ns = _event_ns({"ts_event": start}), _event_ns({"ts_event": end})
    if start_ns is None or end_ns is None or not 0 < end_ns - start_ns <= 24 * 3600 * 10**9:
        raise ValueError("Session requires an increasing timezone-bearing window no longer than 24 hours")
    if not math.isfinite(risk_free_rate) or not -.1 <= risk_free_rate <= 1:
        raise ValueError("Configured rate must be between -0.1 and 1")
    if not math.isfinite(max_underlying_age) or max_underlying_age < 0:
        raise ValueError("Maximum futures quote age must be finite and nonnegative")
    output_dir = Path(output_dir).absolute()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    connection, source = build_index({key: Path(value) for key, value in files.items()}, symbol, output_dir, max_records=max_records)
    source["session"] = {"start": start, "end": end, "trade_window": "inclusive start, exclusive end"}
    # All source definitions can seed metadata; only trades inside the requested
    # trading session can seed accumulated volume. No UTC-midnight state reset.
    outside = connection.execute("SELECT COUNT(*) FROM records WHERE role='trades' AND NOT(ns>=? AND ns<?)", (start_ns, end_ns)).fetchone()[0]
    if outside:
        connection.close()
        raise ValueError("Option trade input extends outside the declared session")
    outside_quotes = connection.execute("SELECT COUNT(*) FROM records WHERE role='underlying' AND NOT(ns>=? AND ns<?)", (start_ns - 2 * 10**9, end_ns)).fetchone()[0]
    future_definitions = connection.execute("SELECT COUNT(*) FROM records WHERE role='definitions' AND ns>=?", (end_ns,)).fetchone()[0]
    if outside_quotes or future_definitions:
        connection.close()
        raise ValueError("Quote or definition input extends outside the declared session and two-second quote warmup")
    config = GexConfig(symbol=symbol, symbols=(symbol,), data_mode="replay", data_provider="databento",
                       contract_multiplier=50 if symbol == "ES" else 20, risk_free_rate=risk_free_rate,
                       days_to_expiry=.25, refresh_interval_seconds=.5, stale_after_seconds=10,
                       replay_path="", replay_delay_seconds=0, tradovate_environment="demo")
    capture = output_dir / f"{symbol.lower()}.gex-session.jsonl"
    consumer = StatefulGexConsumer(IntradayGexEngine(config.contract_multiplier), target_underlying=symbol,
                                   risk_free_rate=risk_free_rate, data_mode="replay")
    writer = CapturedSessionWriter(capture, source=source,
                                   model_inputs={"contract_multiplier": config.contract_multiplier,
                                                 "risk_free_rate": risk_free_rate, "days_to_expiry": .25, "expiry_filter": "all"},
                                   label=f"Databento {symbol} full session {start[:10]} to {end[:10]}")
    adapter = DatabentoAdapter(_HistoricalRecordingConsumer(consumer, writer), target_underlying=symbol,
                              risk_free_rate=risk_free_rate, max_underlying_age_seconds=max_underlying_age,
                              live_client_factory=lambda **_: None)
    processed = 0
    last_progress = time.monotonic()
    await writer.start()
    consumer.mark_connected()
    try:
        for payload, in connection.execute("SELECT payload FROM records WHERE selected=1 ORDER BY ns,priority,id"):
            consumer.record_provider_frame()
            await adapter._handle_live_record(json.loads(payload))
            processed += 1
            if processed % 5000 == 0 or time.monotonic() - last_progress >= 10:
                print(f"Converted {processed:,} {symbol} records; {adapter._option_trade_count:,} option trades...", file=sys.stderr, flush=True)
                await asyncio.sleep(0)
                last_progress = time.monotonic()
        if consumer.malformed_message_count:
            raise ValueError("Production consumer rejected conflicting full-session state")
        matrix = await consumer.process_latest_snapshot(days_to_expiry=.25)
        selected, _ = consumer._select_position_states(list(consumer.contract_state.values()))
        active, expired_count = consumer._active_contract_states(selected, consumer.market_time)
        raw_quantity = sum(int(row["accumulated_volume"]) for row in selected)
        active_quantity = sum(int(row["accumulated_volume"]) for row in active)
        final_selection = {"pricing_coverage": pricing_coverage(active),
                           "raw_retained_contracts": len(selected), "raw_retained_quantity": raw_quantity,
                           "expired_contract_count": expired_count, "expired_quantity": raw_quantity - active_quantity}
        await writer.finalize(feed_quality=consumer.feed_quality_snapshot())
        accounting = {row[0]: {"records": row[1], "selected_records": row[2], "raw_quantity": row[3], "selected_raw_quantity": row[4]}
                      for row in connection.execute("SELECT role,COUNT(*),SUM(selected),SUM(quantity),SUM(CASE WHEN selected=1 THEN quantity ELSE 0 END) FROM records GROUP BY role")}
        report = {"schema": "gex-terminal.full-session-conversion.v1", "source": source,
                  "historical_provenance": source, "input": {"records": sum(item["records"] for item in source["inputs"]), "network_used": False},
                  "raw_accounting": accounting,
                  "coverage": {"definitions": adapter._definition_count, "underlying_quotes": adapter._underlying_quote_count,
                               "option_trades": adapter._option_trade_count,
                               "american_futures_inverted_iv_ticks": adapter._american_inverted_iv_count,
                               "inverted_iv_ticks": adapter._inverted_iv_count + adapter._american_inverted_iv_count,
                               "retained_prior_iv_ticks": adapter._retained_iv_count, "unavailable_iv_ticks": adapter._unavailable_iv_count},
                  "temporal_integrity": adapter.diagnostics(), "feed_quality": consumer.feed_quality_snapshot(),
                  "final_matrix": matrix, "final_selection": final_selection,
                  "errors": [], "provider_requests": 0, "credits_used": 0}
        _private_json(output_dir / "report.json", report)
        return {"capture": str(capture), "report": str(output_dir / "report.json"),
                "index": str(output_dir / "index.sqlite"), "event_count": writer._sequence,
                "final_pricing_coverage": final_selection["pricing_coverage"]}
    except BaseException as exc:
        await writer.abort(f"Full-session conversion failed: {type(exc).__name__}")
        raise
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("ES", "NQ"), required=True)
    for role in KINDS:
        parser.add_argument("--" + role, type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    restrict_network_to_loopback()
    result = asyncio.run(convert_session(files={role: getattr(args, role) for role in KINDS}, symbol=args.symbol,
                                        output_dir=args.output_dir, start=args.start, end=args.end))
    print(json.dumps(result))


if __name__ == "__main__":
    main()

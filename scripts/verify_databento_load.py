"""Measure the actual offline Databento provider handler with synthetic ES/NQ records.

Run from the checkout with ``python -m scripts.verify_databento_load --output PATH``.
Timing excludes tracemalloc and snapshot work; a separate identical replay measures
memory. No SDK, credentials, subscriptions or network connection are used.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import math
import platform
import random
import sys
import time
import tracemalloc
from collections import Counter
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterator

from gex_terminal import __version__
from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.implied_volatility import black_76_option_price


SCHEMA = "gex-terminal.databento-provider-load.v1"
BASE_TIME = datetime(2026, 10, 12, 16, tzinfo=timezone.utc)
FAMILY_ROOTS = {
    "ES": ("ES", "EW", *(f"EW{i}" for i in range(1, 5)),
           *(f"E{i}{day}" for day in "ABCD" for i in range(1, 6))),
    "NQ": ("NQ", "QNE", *(f"QN{i}" for i in range(1, 5)),
           *(f"Q{i}{day}" for day in "ABCD" for i in range(1, 6))),
}


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _contracts(seed: int, contracts_per_family: int) -> list[dict[str, Any]]:
    specs = []
    for symbol_index, (symbol, families) in enumerate(FAMILY_ROOTS.items()):
        spot = 6000.0 if symbol == "ES" else 20000.0
        for family_index, family in enumerate(families):
            for slot in range(contracts_per_family):
                instrument_id = 100000 * (symbol_index + 1) + family_index * contracts_per_family + slot
                strike = spot + (slot - contracts_per_family // 2) * (5 if symbol == "ES" else 25)
                option_type = "C" if slot % 2 == 0 else "P"
                expiry = BASE_TIME + timedelta(days=30 + family_index % 3)
                specs.append({
                    "symbol": symbol, "family": family, "slot": slot,
                    "id": instrument_id, "future_id": 10 + symbol_index,
                    "spot": spot, "strike": strike, "option_type": option_type,
                    "expiry": expiry, "traded": slot % 4 in {1, 3},
                    "deleted": slot % 4 in {2, 3},
                    "option_price": black_76_option_price(
                        futures_price=spot, strike=strike,
                        time_to_expiry_years=(expiry - BASE_TIME).total_seconds() / (365 * 86400),
                        risk_free_rate=0.045, volatility=0.2, option_type=option_type,
                    ),
                })
    random.Random(seed).shuffle(specs)
    return specs


def _oi_quantity(spec: dict[str, Any], seed: int, round_number: int) -> int:
    return 0 if spec["slot"] % 8 == 0 and round_number > 0 else (
        100 + (seed + spec["id"] * 11 + round_number * 17) % 5000
    )


def _trade_quantity(spec: dict[str, Any], seed: int, round_number: int) -> int:
    return 1 + (seed + spec["id"] * 7 + round_number * 13) % 9


def raw_records(
    specs: list[dict[str, Any]], seed: int, rounds: int,
) -> Iterator[tuple[str | None, dict[str, Any] | None, datetime]]:
    """Yield provider-shaped records and checkpoint markers, never app messages."""
    old_reference = (BASE_TIME - timedelta(days=2)).date().isoformat()
    new_reference = (BASE_TIME - timedelta(days=1)).date().isoformat()

    def quote(symbol: str, stamp: datetime) -> dict[str, Any]:
        index = 0 if symbol == "ES" else 1
        spot = 6000.0 if symbol == "ES" else 20000.0
        return {"record_type": "mbp-1", "instrument_id": 10 + index,
                "bid_px_00": spot - 0.25, "ask_px_00": spot + 0.25,
                "ts_event": _iso(stamp)}

    def statistic(spec: dict[str, Any], stamp: datetime, reference: str,
                  quantity: int, action: int = 1) -> dict[str, Any]:
        return {"record_type": "statistics", "instrument_id": spec["id"],
                "stat_type": "open_interest", "quantity": quantity,
                "ts_ref": reference, "ts_event": _iso(stamp), "update_action": action}

    for spec in specs:
        multiplier = 50 if spec["symbol"] == "ES" else 20
        yield spec["symbol"], {
            "record_type": "definition", "instrument_id": spec["id"],
            "asset": spec["family"], "underlying": f"{spec['symbol']}Z6",
            "underlying_id": spec["future_id"],
            "raw_symbol": f"{spec['family']}Z6 {spec['option_type']}{spec['strike']:g}",
            "strike_price": spec["strike"], "instrument_class": spec["option_type"],
            "expiration": _iso(spec["expiry"]), "contract_multiplier": 1,
            "unit_of_measure": "USD", "unit_of_measure_qty": multiplier,
        }, BASE_TIME
    for symbol in FAMILY_ROOTS:
        yield symbol, quote(symbol, BASE_TIME), BASE_TIME
    for spec in specs:
        stamp = BASE_TIME + timedelta(microseconds=1)
        yield spec["symbol"], statistic(spec, stamp, old_reference,
                                         _oi_quantity(spec, seed, 0)), stamp
    sequences = Counter()
    for round_number in range(1, rounds + 1):
        stamp = BASE_TIME + timedelta(seconds=round_number)
        for symbol in FAMILY_ROOTS:
            yield symbol, quote(symbol, stamp), stamp
        for spec in specs:
            publication = stamp + timedelta(microseconds=100)
            yield spec["symbol"], statistic(spec, publication, new_reference,
                _oi_quantity(spec, seed, round_number)), publication
            # Later publication for an older trading date cannot replace current OI.
            later = publication + timedelta(microseconds=100)
            yield spec["symbol"], statistic(spec, later, old_reference, 999999), later
            # Same trading date but an older revision must also be rejected.
            earlier = publication - timedelta(microseconds=1)
            yield spec["symbol"], statistic(spec, earlier, new_reference, 888888), earlier
            if spec["traded"]:
                sequences[spec["symbol"]] += 1
                yield spec["symbol"], {
                    "record_type": "trades", "instrument_id": spec["id"],
                    "price": spec["option_price"],
                    "size": _trade_quantity(spec, seed, round_number),
                    "side": "B" if spec["slot"] % 2 else "A",
                    "sequence": sequences[spec["symbol"]], "ts_event": _iso(publication),
                }, publication
        yield None, None, stamp + timedelta(milliseconds=1)
    deletion_time = BASE_TIME + timedelta(seconds=rounds + 1)
    for spec in specs:
        if spec["deleted"]:
            yield spec["symbol"], statistic(spec, deletion_time, new_reference,
                                           2**63 - 1, 2), deletion_time
            earlier = deletion_time - timedelta(microseconds=1)
            yield spec["symbol"], statistic(spec, earlier, new_reference, 777777), earlier
            later = deletion_time + timedelta(microseconds=1)
            yield spec["symbol"], statistic(spec, later, old_reference, 666666), later
    yield None, None, deletion_time + timedelta(milliseconds=1)


def _reconcile(
    symbol: str, consumer: StatefulGexConsumer, adapter: DatabentoAdapter,
    specs: list[dict[str, Any]], seed: int, rounds: int,
    selected: list[dict[str, Any]], snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Compare all state keys/quantities to the scripted oracle, without mapper calls."""
    specs = [spec for spec in specs if spec["symbol"] == symbol]
    expected = {}
    selected_expected = {}
    for spec in specs:
        key = ("databento", str(spec["id"]), "open_interest")
        quantity = 0 if spec["deleted"] else _oi_quantity(spec, seed, rounds)
        expected[key] = (quantity, spec["deleted"])
        if spec["traded"]:
            trade_key = (*key[:2], "trade_volume")
            expected[trade_key] = (sum(_trade_quantity(spec, seed, r)
                                      for r in range(1, rounds + 1)), False)
            selected_expected[trade_key] = expected[trade_key][0]
        elif not spec["deleted"]:
            selected_expected[key] = quantity
    actual = {key: (int(state["accumulated_volume"]),
                   bool(state.get("open_interest_invalidated", False)))
              for key, state in consumer.contract_state.items()}
    actual_selected = {(row["provider"], row["contract_id"], row["position_source"]):
                       int(row["accumulated_volume"]) for row in selected}
    mismatches = [str(key) for key in expected.keys() | actual.keys()
                  if expected.get(key) != actual.get(key)]
    reference = (BASE_TIME - timedelta(days=1)).date().isoformat()
    provenance_ok = all(
        state.get("open_interest_reference_date") == reference
        and state.get("open_interest_update_action") == (
            "delete" if state.get("open_interest_invalidated") else "add"
        ) for state in consumer.contract_state.values()
        if state["position_source"] == "open_interest"
    )
    expected_revisions_rejected = len(specs) * (2 * rounds + 1)
    checks = {
        "exact_position_states": actual == expected,
        "exact_selected_positions": actual_selected == selected_expected,
        "deleted_oi_excluded": not any(row.get("open_interest_invalidated") for row in selected),
        "oi_reference_and_action": provenance_ok,
        "stale_revisions_rejected": consumer.duplicate_message_count == expected_revisions_rejected,
        "trade_count": adapter._option_trade_count == len(specs) // 2 * rounds,
        "definition_count": adapter._definition_count == len(specs),
        "quote_count": adapter._underlying_quote_count == rounds + 1,
        "trade_iv_inversions": adapter._inverted_iv_count == len(specs) // 2 * rounds,
        "oi_add_count": adapter._open_interest_count == len(specs) * (rounds + 1),
        "oi_delete_count": adapter._open_interest_delete_count == len(specs) // 2,
        "families_observed": set(adapter.diagnostics()["subscriptions"]["option_product_roots_observed"])
            == set(FAMILY_ROOTS[symbol]),
        "snapshot_selected_count": snapshot.get("selected_contract_count") == len(selected_expected),
        "snapshot_dollar_multiplier": snapshot.get("multiplier_provenance", {}).get("effective_multipliers")
            == [50.0 if symbol == "ES" else 20.0],
        "no_parse_errors": consumer.provider_parse_error_count == consumer.malformed_message_count == 0,
    }
    return {
        "checks": checks, "mismatched_contracts": len(mismatches),
        "mismatch_examples": sorted(mismatches)[:20],
        "expected_state_count": len(expected), "observed_state_count": len(actual),
        "expected_selected_count": len(selected_expected), "observed_selected_count": len(actual_selected),
        "expected_selected_quantity": sum(selected_expected.values()),
        "observed_selected_quantity": sum(actual_selected.values()),
        "expected_trade_quantity": sum(q for key, (q, _) in expected.items() if key[2] == "trade_volume"),
        "observed_trade_quantity": sum(q for key, (q, _) in actual.items() if key[2] == "trade_volume"),
        "expected_oi_quantity": sum(q for key, (q, _) in expected.items() if key[2] == "open_interest"),
        "observed_oi_quantity": sum(q for key, (q, _) in actual.items() if key[2] == "open_interest"),
        "deleted_oi_contracts": len(specs) // 2,
        "valid_zero_oi_contracts": sum(q == 0 and not deleted
            for key, (q, deleted) in expected.items() if key[2] == "open_interest"),
        "expected_revisions_rejected": expected_revisions_rejected,
        "observed_revisions_rejected": consumer.duplicate_message_count,
    }


async def _exercise(seed: int, contracts_per_family: int, rounds: int,
                    snapshot_every: int) -> dict[str, Any]:
    specs = _contracts(seed, contracts_per_family)
    consumers = {symbol: StatefulGexConsumer(
        IntradayGexEngine(multiplier=50 if symbol == "ES" else 20),
        target_underlying=symbol, data_mode="replay", expiry_filter="all",
    ) for symbol in FAMILY_ROOTS}
    adapters = {symbol: DatabentoAdapter(
        consumer, target_underlying=symbol,
        option_parents=tuple(f"{family}.OPT" for family in FAMILY_ROOTS[symbol]),
        live_client_factory=lambda **kwargs: (_ for _ in ()).throw(AssertionError("network disabled")),
    ) for symbol, consumer in consumers.items()}
    record_counts = Counter()
    peak_states = 0
    snapshot_samples = []
    snapshot_errors = []
    snapshots = {}
    checkpoint = 0
    ingest_seconds = 0.0
    started = time.perf_counter()
    for symbol, record, stamp in raw_records(specs, seed, rounds):
        if record is not None:
            record_counts[record["record_type"]] += 1
            consumers[symbol].record_provider_frame()
            await adapters[symbol]._handle_live_record(record)
            peak_states = max(peak_states, sum(len(c.contract_state) for c in consumers.values()))
            continue
        ingest_seconds += time.perf_counter() - started
        checkpoint += 1
        if checkpoint % snapshot_every == 0 or checkpoint == rounds + 1:
            for target, consumer in consumers.items():
                snapshot_started = time.perf_counter()
                snapshot = await consumer.process_latest_snapshot(days_to_expiry=30, as_of=stamp)
                snapshot_samples.append((time.perf_counter() - snapshot_started) * 1000)
                snapshots[target] = snapshot
                if "error" in snapshot:
                    snapshot_errors.append({"symbol": target, "error": snapshot["error"]})
        started = time.perf_counter()
    ingest_seconds += time.perf_counter() - started
    final_time = BASE_TIME + timedelta(seconds=rounds + 1, milliseconds=1)
    reconciliations = {}
    for symbol, consumer in consumers.items():
        selected = await consumer.selected_contract_rows(as_of=final_time)
        reconciliations[symbol] = _reconcile(
            symbol, consumer, adapters[symbol], specs, seed, rounds, selected, snapshots[symbol],
        )
    return {"raw_record_counts": dict(record_counts), "ingest_seconds": ingest_seconds,
            "snapshot_samples_milliseconds": snapshot_samples, "snapshot_errors": snapshot_errors,
            "peak_position_states": peak_states, "state_limit": len(specs) * 2,
            "reconciliation": reconciliations}


def _peak_rss_megabytes() -> float | None:
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError):
        return None
    return value / (1024 * 1024 if sys.platform == "darwin" else 1024)


def _source_identity() -> dict[str, str]:
    source_root = Path(__file__).resolve().parents[1]
    names = ("scripts/verify_databento_load.py", "gex_terminal/adapters/databento.py",
             "gex_terminal/consumer.py", "gex_terminal/contracts.py",
             "gex_terminal/market_data_adapter.py", "gex_terminal/engine.py",
             "gex_terminal/implied_volatility.py")
    return {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest() for name in names}


async def build_load_report(
    *, seed: int = 35, contracts_per_family: int = 4, rounds: int = 8,
    snapshot_every: int = 2, minimum_ingest_records_per_second: float = 50,
    maximum_snapshot_milliseconds: float = 1000, maximum_peak_megabytes: float = 256,
) -> dict[str, Any]:
    if any(not isinstance(value, int) or isinstance(value, bool)
           for value in (seed, contracts_per_family, rounds, snapshot_every)):
        raise ValueError("seed and workload counts must be integers")
    if contracts_per_family < 4 or contracts_per_family > 128 or contracts_per_family % 4:
        raise ValueError("contracts_per_family must be a multiple of 4 between 4 and 128")
    if not 1 <= rounds <= 1000 or snapshot_every < 1:
        raise ValueError("rounds must be 1..1000 and snapshot_every must be positive")
    expected_records = (rounds + 1) * (182 * contracts_per_family + 2)
    if expected_records > 250000:
        raise ValueError("workload exceeds 250000 raw records; use a smaller bounded run")
    budgets = {"minimum_ingest_records_per_second": minimum_ingest_records_per_second,
               "maximum_snapshot_milliseconds": maximum_snapshot_milliseconds,
               "maximum_peak_megabytes": maximum_peak_megabytes}
    if any(not math.isfinite(value) or value <= 0 for value in budgets.values()):
        raise ValueError("budgets must be positive and finite")
    if tracemalloc.is_tracing():
        raise ValueError("run with tracemalloc disabled so the timing pass is uninstrumented")
    loop = asyncio.get_running_loop()
    previous_debug = loop.get_debug()
    source_before = _source_identity()
    loop.set_debug(False)
    try:
        timed = await _exercise(seed, contracts_per_family, rounds, snapshot_every)
        gc.collect()
        tracemalloc.start()
        try:
            memory_run = await _exercise(seed, contracts_per_family, rounds, snapshot_every)
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    finally:
        loop.set_debug(previous_debug)
    records = sum(timed["raw_record_counts"].values())
    samples = sorted(timed["snapshot_samples_milliseconds"])
    rss = _peak_rss_megabytes()
    traced_peak = peak_bytes / (1024 * 1024)
    peak_memory = max(traced_peak, rss) if rss is not None else None
    ingest_rate = records / max(timed["ingest_seconds"], 1e-12)
    gates = {
        "source_unchanged_during_run": source_before == _source_identity(),
        "record_count": records == expected_records,
        "correctness": all(all(item["checks"].values()) for item in timed["reconciliation"].values()),
        "memory_pass_correctness": all(all(item["checks"].values())
                                       for item in memory_run["reconciliation"].values()),
        "bounded_position_states": timed["peak_position_states"] <= timed["state_limit"],
        "memory_pass_bounded_states": memory_run["peak_position_states"] <= memory_run["state_limit"],
        "snapshot_success": not timed["snapshot_errors"] and not memory_run["snapshot_errors"],
        "ingest_rate": ingest_rate >= minimum_ingest_records_per_second,
        "snapshot_latency": bool(samples) and max(samples) <= maximum_snapshot_milliseconds,
        "peak_memory": peak_memory is not None and peak_memory <= maximum_peak_megabytes,
    }
    return {
        "schema": SCHEMA, "generated_at": _iso(datetime.now(timezone.utc)),
        "workload": {"synthetic": True, "seed": seed, "symbols": list(FAMILY_ROOTS),
                     "option_families": {symbol: list(families) for symbol, families in FAMILY_ROOTS.items()},
                     "total_families": 52, "contracts_per_family": contracts_per_family,
                     "unique_option_contracts": 52 * contracts_per_family, "rounds": rounds,
                     "snapshot_every_rounds": snapshot_every, "raw_records": records,
                     "expected_raw_records": expected_records, "record_types": timed["raw_record_counts"],
                     "provider_path": "DatabentoAdapter._handle_live_record -> StatefulGexConsumer -> snapshot",
                     "record_form": "decoded provider-shaped mappings, not normalized app messages",
                     "network_used": False},
        "environment": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                        "platform": platform.platform(), "application_version": __version__,
                        "numpy_version": version("numpy"),
                        "asyncio_debug_during_measurement": False, "tracemalloc_during_timing": False,
                        "memory_method": "separate traced replay and process-lifetime peak RSS",
                        "rss_peak_includes": "imports, timing pass and traced memory pass",
                        "source_sha256": source_before},
        "observed": {"ingest_seconds": timed["ingest_seconds"],
                     "ingest_records_per_second": ingest_rate, "snapshot_samples": len(samples),
                     "snapshot_max_milliseconds": max(samples),
                     "snapshot_p95_milliseconds": samples[math.ceil(len(samples) * 0.95) - 1],
                     "python_peak_megabytes": traced_peak, "process_peak_rss_megabytes": rss,
                     "peak_megabytes": peak_memory, "peak_position_states": timed["peak_position_states"],
                     "position_state_limit": timed["state_limit"]},
        "reconciliation": timed["reconciliation"], "snapshot_errors": timed["snapshot_errors"],
        "budgets": budgets, "gates": gates,
        "result": {"passed": all(gates.values()), "live_capacity_certified": False,
                   "predictive_validity": "unmeasured"},
        "evidence_ceiling": "synthetic offline provider-handler load only; no live authentication, "
                            "entitlements, DBN transport throughput, complete market coverage or production capacity claim",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=35)
    parser.add_argument("--contracts-per-family", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--snapshot-every", type=int, default=2)
    parser.add_argument("--minimum-ingest-records-per-second", type=float, default=50)
    parser.add_argument("--maximum-snapshot-milliseconds", type=float, default=1000)
    parser.add_argument("--maximum-peak-megabytes", type=float, default=256)
    args = parser.parse_args(argv)
    if args.output.suffix.lower() != ".json":
        parser.error("output must have a .json suffix")
    kwargs = vars(args).copy()
    output = kwargs.pop("output")
    try:
        report = asyncio.run(build_load_report(**kwargs))
    except Exception as exc:
        report = {"schema": SCHEMA, "generated_at": _iso(datetime.now(timezone.utc)),
                  "requested": {key: str(value) if isinstance(value, float) and not math.isfinite(value)
                                else value for key, value in kwargs.items()},
                  "result": {"passed": False, "live_capacity_certified": False},
                  "error": {"type": type(exc).__name__, "message": str(exc)}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": report["result"]["passed"],
                      "observed": report.get("observed"), "gates": report.get("gates")}))
    return 0 if report["result"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

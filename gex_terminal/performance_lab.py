"""Generated-chain performance envelope for offline regression detection."""

from __future__ import annotations

import json
import platform
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import dumps_normalized_message


PERFORMANCE_SCHEMA = "gex-terminal.generated-chain-performance.v1"


async def build_performance_report(
    config: GexConfig,
    *,
    contracts: int = 500,
    minimum_ingest_records_per_second: float = 50.0,
    maximum_snapshot_milliseconds: float = 1000.0,
    maximum_peak_megabytes: float = 256.0,
) -> dict[str, Any]:
    if contracts < 10 or contracts > 20_000:
        raise ValueError("contracts must be between 10 and 20000")
    if minimum_ingest_records_per_second <= 0:
        raise ValueError("minimum ingest rate must be positive")
    if maximum_snapshot_milliseconds <= 0 or maximum_peak_megabytes <= 0:
        raise ValueError("performance ceilings must be positive")
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode="replay",
        expiry_filter="all",
    )
    base_time = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)
    expiry_time = base_time + timedelta(days=30)
    underlying = {
        "schema_version": 2,
        "type": "underlying_tick",
        "provider": "generated-performance",
        "symbol": config.symbol,
        "price": 6000.0,
        "event_time": base_time.isoformat().replace("+00:00", "Z"),
    }
    messages = [underlying]
    for index in range(contracts):
        strike = 5000.0 + float(index % 401) * 5.0
        option_type = "C" if index % 2 == 0 else "P"
        messages.append({
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "generated-performance",
            "contract_id": f"generated-{index:06d}",
            "symbol": config.symbol,
            "strike": strike,
            "option_type": option_type,
            "volume": 1 + index % 25,
            "volume_semantics": "incremental",
            "position_source": "trade_volume",
            "iv": 0.12 + (index % 12) * 0.01,
            "iv_source": "provider",
            "instrument_class": "futures_option",
            "pricing_model": "black_76",
            "expiry": expiry_time.date().isoformat(),
            "expiry_timestamp": expiry_time.isoformat().replace("+00:00", "Z"),
            "event_time": (base_time + timedelta(microseconds=index + 1)).isoformat().replace("+00:00", "Z"),
            "aggressor_side": "buy" if index % 3 == 0 else "sell" if index % 3 == 1 else "unknown",
            "direction_source": "provider" if index % 3 != 2 else "unknown",
            "sequence": index + 1,
        })
    tracemalloc.start()
    ingest_started = time.perf_counter()
    for message in messages:
        await consumer.update_market_state(dumps_normalized_message(message))
    ingest_seconds = time.perf_counter() - ingest_started
    snapshot_started = time.perf_counter()
    result = await consumer.process_latest_snapshot(
        days_to_expiry=config.days_to_expiry,
        expiry_filter="all",
        as_of=base_time,
    )
    snapshot_milliseconds = (time.perf_counter() - snapshot_started) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if "error" in result:
        raise ValueError(f"generated-chain snapshot failed: {result['error']}")
    ingest_rate = len(messages) / max(ingest_seconds, 1e-12)
    peak_megabytes = peak_bytes / (1024.0 * 1024.0)
    gates = {
        "ingest_rate": ingest_rate >= minimum_ingest_records_per_second,
        "snapshot_latency": snapshot_milliseconds <= maximum_snapshot_milliseconds,
        "peak_memory": peak_megabytes <= maximum_peak_megabytes,
    }
    return {
        "schema": PERFORMANCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workload": {
            "generated": True,
            "symbol": config.symbol,
            "option_contracts": contracts,
            "normalized_records": len(messages),
            "unique_strikes": len(result["strikes"]),
            "position_source": "trade_volume",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "observed": {
            "ingest_seconds": ingest_seconds,
            "ingest_records_per_second": ingest_rate,
            "snapshot_milliseconds": snapshot_milliseconds,
            "peak_megabytes": peak_megabytes,
        },
        "budgets": {
            "minimum_ingest_records_per_second": minimum_ingest_records_per_second,
            "maximum_snapshot_milliseconds": maximum_snapshot_milliseconds,
            "maximum_peak_megabytes": maximum_peak_megabytes,
        },
        "gates": gates,
        "result": {
            "passed": all(gates.values()),
            "live_capacity_certified": False,
            "predictive_validity": "unmeasured",
        },
        "evidence_ceiling": (
            "local generated-chain regression envelope only; observed values are not live-feed "
            "throughput, exchange latency, production capacity, or a service-level objective"
        ),
    }


def write_performance_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("performance output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target

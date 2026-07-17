"""Offline feed-quality scenario simulation for demo and replay sessions."""

import json
import time
from typing import Iterable


QUALITY_SCENARIOS = ("stale", "partial-chain", "dropped", "latency", "all")


async def apply_quality_scenario(consumer, scenario: str) -> None:
    """Mutate a seeded consumer to exercise provider-health UI states."""
    scenario = scenario.strip().lower()
    if scenario not in QUALITY_SCENARIOS:
        expected = ", ".join(QUALITY_SCENARIOS)
        raise ValueError(f"Unknown quality scenario '{scenario}'. Expected one of: {expected}")

    if scenario in {"dropped", "all"}:
        await _simulate_dropped_messages(consumer)
    if scenario in {"partial-chain", "all"}:
        _simulate_partial_chain(consumer)
    if scenario in {"latency", "all"}:
        _simulate_latency(consumer)
    if scenario in {"stale", "all"}:
        _simulate_stale_feed(consumer)


def quality_scenario_names() -> tuple[str, ...]:
    return QUALITY_SCENARIOS


async def _simulate_dropped_messages(consumer) -> None:
    await consumer.update_market_state(json.dumps({
        "type": "underlying_tick",
        "symbol": f"{consumer.target_underlying}_OFFSYMBOL",
        "price": 1.0,
    }))
    await consumer.update_market_state(json.dumps({
        "type": "unknown_tick",
        "symbol": consumer.target_underlying,
    }))
    _append_note(consumer, "dropped/off-symbol messages simulated")


def _simulate_partial_chain(consumer) -> None:
    strikes = sorted(consumer.chain_state)
    if len(strikes) <= 3:
        _append_note(consumer, "partial-chain simulation requested on already-small chain")
        return
    removed = strikes[1::3]
    for strike in removed:
        consumer.chain_state.pop(strike, None)
        for expiry_bucket in consumer.expiry_state.values():
            expiry_bucket.pop(strike, None)
    consumer.dropped_message_count += max(1, len(removed))
    _append_note(consumer, "missing option strikes simulated")


def _simulate_latency(consumer) -> None:
    consumer.simulated_latency_ms = 325.0
    _append_note(consumer, "latency spike simulated")


def _simulate_stale_feed(consumer) -> None:
    consumer.data_mode = "LIVE"
    consumer.mark_connected()
    consumer.last_message_at = time.monotonic() - (consumer.stale_after_seconds + 5.0)
    _append_note(consumer, "stale tick stream simulated")


def _append_note(consumer, note: str) -> None:
    notes: Iterable[str] = getattr(consumer, "quality_notes", ())
    consumer.quality_notes = tuple(dict.fromkeys((*notes, note)))

"""Explicit offline batching changes projection work, never accepted economics."""
import asyncio
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint
from tests.test_pricing_coverage import unavailable
from tests.test_wind_tunnel_checkpoint import AS_OF, option


def consumer(mode="replay"):
    return StatefulGexConsumer(IntradayGexEngine(50), data_mode=mode)


def spot(contract_id="202", event_time=AS_OF, price=6000):
    return {"schema_version": 2, "provider": "databento", "type": "underlying_tick", "symbol": "ES",
            "contract_id": contract_id, "event_time": event_time, "price": price}


def trade(contract_id="call", option_type="C", **updates):
    return option(contract_id, option_type, **{"provider": "databento", "underlying_contract_id": "202", **updates})


async def apply(target, events):
    return [await target.update_market_state(json.dumps(event)) for event in events]


def plain(value):
    def encode(item):
        if isinstance(item, datetime):
            return item.isoformat()
        return item.tolist() if isinstance(item, np.ndarray) else item.item()
    def without_elapsed_ages(item):
        if isinstance(item, dict):
            return {key: without_elapsed_ages(child) for key, child in item.items()
                    if key not in {"last_message_age_seconds", "last_snapshot_age_seconds"}}
        if isinstance(item, list):
            return [without_elapsed_ages(child) for child in item]
        return item
    return without_elapsed_ages(json.loads(json.dumps(value, default=encode, sort_keys=True)))


class OfflineProjectionBatchTests(unittest.IsolatedAsyncioTestCase):
    async def assert_same_state(self, first, second, *, checkpoint=True):
        for name in ("contract_state", "chain_state", "expiry_state", "current_spot", "session_open", "market_time",
                     "message_count", "malformed_message_count", "duplicate_message_count", "cumulative_reset_count",
                     "fallback_iv_tick_count", "_underlying_contract_state", "_retired_underlying_contract_ids"):
            self.assertEqual(getattr(first, name), getattr(second, name), name)
        self.assertEqual(first.runtime_status, second.runtime_status)
        self.assertEqual(first.available_expiries(), second.available_expiries())
        self.assertEqual(plain(await first.process_latest_snapshot(.25)), plain(await second.process_latest_snapshot(.25)))
        self.assertEqual(await first.process_expiry_breakdown(.25), await second.process_expiry_breakdown(.25))
        self.assertEqual(await first.selected_contract_rows(), await second.selected_contract_rows())
        if checkpoint:
            self.assertEqual(await build_terminal_checkpoint(first, fallback_dte=.25),
                             await build_terminal_checkpoint(second, fallback_dte=.25))

    async def test_batch_matches_default_dedup_cumulative_reset_rollover_expiry_and_unpriced(self):
        first_fill = trade(volume=7, sequence=10, provider_trade_event_id="a" * 64)
        events = [spot(), trade(source="open_interest", volume=100, sequence=1), first_fill,
                  copy.deepcopy(first_fill), {**first_fill, "volume": 3, "provider_trade_event_id": "b" * 64},
                  trade("counter", "P", volume=20, sequence=1, volume_semantics="cumulative"),
                  trade("counter", "P", volume=5, sequence=2, volume_semantics="cumulative"),
                  spot("303", "2026-09-04T14:00:00Z", 6010),
                  trade("new-future", volume=9, underlying_contract_id="303", event_time="2026-09-04T14:00:01Z"),
                  trade("expired", volume=11, underlying_contract_id="303", event_time="2026-09-04T14:00:01Z",
                        expiry_timestamp="2026-09-04T14:00:30Z"),
                  unavailable(provider="databento", underlying_contract_id="303", event_time="2026-09-04T14:00:02Z"),
                  spot("202", "2026-09-04T14:01:00Z", 5900),
                  spot("303", "2026-09-04T14:01:01Z", 6011)]
        normal, batched = consumer(), consumer()
        expected = await apply(normal, events)
        async with batched.offline_projection_batch():
            actual = await apply(batched, events)
            self.assertEqual(actual, expected)
            self.assertEqual(batched.runtime_status, normal.runtime_status)
        await self.assert_same_state(normal, batched)
        self.assertEqual(batched.duplicate_message_count, 1)
        self.assertEqual(batched.cumulative_reset_count, 1)

    async def test_inspections_flush_the_accepted_prefix_inside_a_batch(self):
        normal, batched = consumer(), consumer()
        async with batched.offline_projection_batch():
            await apply(normal, [spot(), trade(sequence=1)])
            await apply(batched, [spot(), trade(sequence=1)])
            self.assertTrue(batched._public_projections_dirty)
            for index, inspect in enumerate((
                lambda c: c.process_latest_snapshot(.25), lambda c: c.process_expiry_breakdown(.25),
                lambda c: c.selected_contract_rows(), lambda c: c.capture_wind_tunnel_state(),
            ), start=2):
                event = trade(sequence=index)
                await apply(normal, [event])
                await apply(batched, [event])
                self.assertEqual(plain(await inspect(batched)), plain(await inspect(normal)))
                self.assertFalse(batched._public_projections_dirty)
                self.assertEqual(batched.chain_state, normal.chain_state)

    async def test_legacy_midnight_and_mixed_projection_behaviour_are_identical(self):
        legacy = [{"type": "underlying_tick", "symbol": "ES", "price": 6000, "timestamp": "2026-09-03T23:59:59Z"},
                  {"type": "options_volume_tick", "strike": 6000, "option_type": "C", "volume": 7,
                   "iv": .2, "expiry": "2026-09-04", "timestamp": "2026-09-03T23:59:59Z"},
                  {"type": "options_volume_tick", "strike": 6000, "option_type": "P", "volume": 3,
                   "iv": .25, "expiry": "2026-09-05", "timestamp": "2026-09-04T00:00:01Z"}]
        mixed = trade("mixed")
        mixed.pop("underlying_contract_id")
        for events in (legacy, [*legacy, mixed]):
            with self.subTest(mixed=len(events) > 3):
                normal, batched = consumer(), consumer()
                await apply(normal, events)
                async with batched.offline_projection_batch():
                    await apply(batched, events)
                await self.assert_same_state(normal, batched, checkpoint=len(events) == 3)
                self.assertEqual(batched.chain_state[6000.]["C"], 7 if len(events) == 3 else 17)

    async def test_explicit_scope_reduces_rebuilds_and_keeps_default_per_event(self):
        events = [spot(), *(trade(f"contract-{i % 40}", volume=1, sequence=i) for i in range(1000))]
        normal, batched = consumer(), consumer()
        with patch.object(normal, "_rebuild_public_projections_locked", wraps=normal._rebuild_public_projections_locked) as regular:
            await apply(normal, events)
        with patch.object(batched, "_rebuild_public_projections_locked", wraps=batched._rebuild_public_projections_locked) as grouped:
            async with batched.offline_projection_batch():
                await apply(batched, events)
            self.assertEqual(grouped.call_count, 1)
        self.assertEqual(regular.call_count, len(events))
        await self.assert_same_state(normal, batched)

    async def test_exception_and_cancellation_flush_accepted_prefix_and_restore_default(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                target = consumer()
                ready = asyncio.Event()

                async def ingest():
                    async with target.offline_projection_batch():
                        await apply(target, [spot(), trade()])
                        ready.set()
                        if cancelled:
                            await asyncio.Event().wait()
                        raise RuntimeError("stop after accepted prefix")

                task = asyncio.create_task(ingest())
                await ready.wait()
                if cancelled:
                    task.cancel()
                with self.assertRaises(asyncio.CancelledError if cancelled else RuntimeError):
                    await task
                self.assertEqual(target._projection_batch_depth, 0)
                self.assertFalse(target._public_projections_dirty)
                self.assertEqual(target.chain_state[6000.]["C"], 10)
                await apply(target, [trade(sequence=2)])
                self.assertEqual(target.chain_state[6000.]["C"], 20)

    async def test_nested_scope_reset_and_live_rejection_keep_batch_ownership_consistent(self):
        target = consumer()
        async with target.offline_projection_batch():
            await apply(target, [spot(), trade()])
            async with target.offline_projection_batch():
                await apply(target, [trade(sequence=2)])
            self.assertEqual(target.chain_state[6000.]["C"], 20)
            with self.assertRaisesRegex(ValueError, "live"):
                await target.reset_state(data_mode="live")
            await target.reset_state(data_mode="replay")
            await apply(target, [spot(), trade(volume=1)])
        self.assertEqual(target.chain_state[6000.]["C"], 1)
        self.assertEqual(target._projection_batch_depth, 0)
        live = consumer("live")
        with self.assertRaisesRegex(ValueError, "offline"):
            async with live.offline_projection_batch():
                self.fail("A live consumer entered the offline batch")
        self.assertEqual(live._projection_batch_depth, 0)

    async def test_fast_replay_flushes_each_500_events_before_yield_and_at_end(self):
        events = [spot(), *(trade(f"contract-{i % 40}", volume=1, sequence=i) for i in range(1020))]
        normal, batched = consumer(), consumer()
        await apply(normal, events)
        published = []

        async def observe_yield(delay):
            self.assertEqual(delay, 0)
            self.assertFalse(batched._public_projections_dirty)
            published.append(sum(row["C"] + row["P"] for row in batched.chain_state.values()))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "normalized.jsonl"
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            with patch.object(batched, "_rebuild_public_projections_locked", wraps=batched._rebuild_public_projections_locked) as rebuilt, \
                    patch("gex_terminal.adapters.replay.asyncio.sleep", side_effect=observe_yield):
                await ReplayAdapter(batched, path, replay_clock="none").stream_market_data()
            self.assertEqual(rebuilt.call_count, 3)
        self.assertEqual(published, [499, 999])
        await self.assert_same_state(normal, batched)


if __name__ == "__main__":
    unittest.main()

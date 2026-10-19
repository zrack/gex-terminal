"""Large local captures stream with strict integrity and bounded Python memory."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import tracemalloc
import unittest
from unittest.mock import patch

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal import saved_workspace
from gex_terminal.session_capture import (
    CaptureIntegrityError, CapturedSessionWriter, iter_verified_captured_events,
    open_verified_capture, verify_captured_session_bytes, verify_captured_session_file,
)
from gex_terminal.wind_tunnel import calculate
from gex_terminal.wind_tunnel_checkpoint import read_checkpoint
from tests.test_pricing_coverage import unavailable
from tests.test_session_intake import capture_bytes, messages


class CountingConsumer:
    def __init__(self):
        self.count = 0
        self.first = self.last = None
        self.connected = False

    def mark_connected(self):
        self.connected = True

    def mark_disconnected(self):
        self.connected = False

    async def update_market_state(self, raw):
        self.count += 1
        message = json.loads(raw)
        self.first = self.first or message
        self.last = message


async def write_large_capture(path):
    start = datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc)
    writer = CapturedSessionWriter(
        path, source={"provider": "synthetic", "mode": "replay", "symbol": "ES"},
        model_inputs={"contract_multiplier": 50, "risk_free_rate": .037, "days_to_expiry": .6},
    )
    await writer.start()
    for index in range(6000):
        await writer.append({"schema_version": 2, "provider": "synthetic", "symbol": "ES",
                             "type": "underlying_tick", "price": 6000 + index / 10000,
                             "event_time": (start + timedelta(milliseconds=index)).isoformat(),
                             "retained_extension": "x" * 800})
    final = (start + timedelta(seconds=6)).isoformat()
    await writer.append({**messages()[1], "position_source": "trade_volume", "volume": 10,
                         "contract_id": "priced", "strike": 6000, "event_time": final})
    await writer.append(unavailable("unpriced", volume=1, event_time=final,
                                    expiry="2026-10-19", expiry_timestamp="2026-10-19T20:00:00Z"))
    await writer.finalize()


class FullSessionSavedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="gex full local session ")
        cls.root = Path(cls.temporary.name)
        cls.large = cls.root / "large.gex-session.jsonl"
        asyncio.run(write_large_capture(cls.large))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_stream_verification_exceeds_upload_bounds_without_retaining_events(self):
        self.assertGreater(self.large.stat().st_size, 4 * 1024 * 1024)
        count = 0

        def event_seen(_event):
            nonlocal count
            count += 1

        tracemalloc.start()
        try:
            header, footer, stats = verify_captured_session_file(self.large, on_event=event_seen)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual((count, footer["event_count"], stats["event_count"]), (6002, 6002, 6002))
        self.assertEqual(header["source"]["symbol"], "ES")
        self.assertEqual(stats["bytes"], self.large.stat().st_size)
        # The >8 MiB capture must not become an in-memory decoded event tuple.
        self.assertLess(peak, 4 * 1024 * 1024)
        with self.assertRaises(CaptureIntegrityError):
            verify_captured_session_bytes(self.large.read_bytes())

    def test_full_capture_fast_load_retains_assumptions_coverage_and_unpriced_row(self):
        destination = self.root / "large-workspace"
        plan = saved_workspace.prepare_saved_workspace(self.large, "ES", destination)
        self.assertEqual(plan["event_count"], 6002)
        self.assertEqual(plan["replay_policy"], "fast_load")
        self.assertEqual(plan["duration_seconds"], 6)
        self.assertEqual(plan["terminal_args"][plan["terminal_args"].index("--replay-clock") + 1], "none")
        self.assertEqual((plan["risk_free_rate"], plan["fallback_dte"]), (.037, .6))
        checkpoint = read_checkpoint(plan["checkpoint_path"])
        self.assertEqual(checkpoint["source"]["as_of"], "2026-10-18T15:30:06Z")
        result = asyncio.run(calculate({"terminal_checkpoint": checkpoint}))["baseline"]
        self.assertEqual(result["pricing_coverage"]["selected_quantity"], 11)
        self.assertEqual(result["pricing_coverage"]["priced_quantity"], 10)
        self.assertEqual(result["pricing_coverage"]["unpriced_quantity"], 1)
        self.assertIsNone(next(row for row in checkpoint["rows"] if row["contract_id"] == "unpriced")["iv"])
        digest = hashlib.sha256()
        with Path(plan["capture_path"]).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        self.assertEqual(digest.hexdigest(), plan["capture_sha256"])

    def test_duration_alone_selects_fast_load_and_short_capture_keeps_event_time(self):
        for name, final, expected in (("long", "2026-10-18T16:30:00Z", "fast_load"),
                                      ("short", "2026-10-18T15:45:00Z", "event_time_60x")):
            with self.subTest(name=name):
                events = messages()
                events[-1]["event_time"] = final
                path = self.root / f"{name}.gex-session.jsonl"
                path.write_bytes(asyncio.run(capture_bytes(events)))
                plan = saved_workspace.prepare_saved_workspace(path, "ES", self.root / f"{name}-workspace")
                self.assertEqual(plan["replay_policy"], expected)

    def test_verified_iterator_rejects_footer_before_first_event_and_detaches_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.gex-session.jsonl"
            original = asyncio.run(capture_bytes())
            path.write_bytes(original.replace(b'"completed":true', b'"completed":false'))
            with self.assertRaises(CaptureIntegrityError):
                next(iter(iter_verified_captured_events(path)))
            path.write_bytes(original)
            iterator = iter(iter_verified_captured_events(path))
            first = next(iterator)
            path.write_text("source replaced after first verified event")
            remaining = list(iterator)
            self.assertEqual(first["sequence"], 0)
            self.assertEqual([row["sequence"] for row in remaining], [1, 2, 3])

    def test_local_byte_line_event_and_symlink_bounds_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.gex-session.jsonl"
            path.write_bytes(asyncio.run(capture_bytes()))
            for limits in ({"max_bytes": 10}, {"max_line_bytes": 50}, {"max_events": 2}):
                with self.subTest(limits=limits), self.assertRaises(CaptureIntegrityError):
                    verify_captured_session_file(path, **limits)
            link = Path(directory) / "linked.gex-session.jsonl"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                verify_captured_session_file(link)

    def test_local_verification_cancellation_stops_before_reading_all_events(self):
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks == 3

        with self.assertRaisesRegex(CaptureIntegrityError, "cancelled"):
            open_verified_capture(self.large, cancelled=cancelled)
        self.assertEqual(checks, 3)

    def test_saved_validation_still_rejects_late_mixed_symbol_and_cleans_frozen_copy(self):
        events = messages()
        events[-1]["symbol"] = "NQ"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.gex-session.jsonl"
            path.write_bytes(asyncio.run(capture_bytes(events)))
            destination = Path(directory) / "workspace"
            with self.assertRaisesRegex(ValueError, "symbol"):
                saved_workspace.prepare_saved_workspace(path, "ES", destination)
            self.assertFalse(destination.exists())

    def test_replay_streams_large_capture_without_legacy_tuple_loader_or_delays(self):
        consumer = CountingConsumer()
        sleeps = []

        async def sleep(delay):
            sleeps.append(delay)

        replay = ReplayAdapter(consumer, self.large, replay_clock="none", sleep=sleep)
        with patch("gex_terminal.session_capture._verify_capture", side_effect=AssertionError("legacy tuple loader")):
            asyncio.run(replay.stream_market_data())
        self.assertEqual(consumer.count, 6002)
        self.assertFalse(consumer.connected)
        self.assertEqual(sleeps, [])

    def test_cancel_during_thread_verification_closes_owned_disk_spool(self):
        consumer = CountingConsumer()
        ready, release = threading.Event(), threading.Event()
        spool = tempfile.TemporaryFile(mode="w+b")

        def blocked_preparation(_path, **_options):
            ready.set()
            release.wait(timeout=5)
            return spool

        async def cancel():
            task = asyncio.create_task(ReplayAdapter(consumer, self.large).stream_market_data())
            self.assertTrue(await asyncio.to_thread(ready.wait, 3))
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with patch("gex_terminal.adapters.replay.open_verified_capture", side_effect=blocked_preparation):
            asyncio.run(cancel())
        self.assertTrue(spool.closed)
        self.assertEqual(consumer.count, 0)
        self.assertFalse(consumer.connected)


if __name__ == "__main__":
    unittest.main()

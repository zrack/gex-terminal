import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import validate_normalized_message
from gex_terminal.package_data import replay_data_path
from gex_terminal.session_capture import CapturedSessionWriter


class _RecordingConsumer:
    def __init__(self):
        self.messages = []
        self.connected = False
        self.disconnected = False

    def mark_connected(self):
        self.connected = True

    def mark_disconnected(self):
        self.disconnected = True

    async def update_market_state(self, payload):
        self.messages.append(json.loads(payload))


def _underlying_tick(event_time, price):
    return {
        "schema_version": 2,
        "type": "underlying_tick",
        "provider": "capture-test",
        "symbol": "ES",
        "price": price,
        "event_time": event_time,
    }


class ReplayAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def _write_capture(self, path, messages):
        writer = CapturedSessionWriter(path, source="replay-adapter-test")
        await writer.start()
        for message in messages:
            await writer.append(message)
        return await writer.finalize()

    def test_bundled_synthetic_es_session_uses_normalized_messages(self):
        adapter = ReplayAdapter(
            consumer=None,
            replay_path=replay_data_path("es_synthetic_full_session.jsonl"),
            delay_seconds=0,
        )
        messages = list(adapter._load_messages())

        self.assertGreater(len(messages), 20)
        self.assertEqual(messages[0]["type"], "underlying_tick")
        self.assertEqual(messages[-1]["session_phase"], "late")
        for message in messages:
            validate_normalized_message(message)

    async def test_replay_feeds_consumer_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "replay.jsonl"
            replay_path.write_text(
                "\n".join((
                    '{"type":"underlying_tick","symbol":"ES","price":5943.25}',
                    '{"type":"options_volume_tick","strike":5950,"option_type":"C","volume":100,"iv":0.15}',
                    '{"type":"options_volume_tick","strike":5950,"option_type":"P","volume":40,"iv":0.15}',
                )),
                encoding="utf-8",
            )
            consumer = StatefulGexConsumer(
                IntradayGexEngine(),
                target_underlying="ES",
                data_mode="replay",
            )
            adapter = ReplayAdapter(consumer, replay_path, delay_seconds=0)

            await adapter.stream_market_data()

        self.assertEqual(consumer.current_spot, 5943.25)
        self.assertEqual(consumer.chain_state[5950.0]["C"], 100)
        self.assertEqual(consumer.chain_state[5950.0]["P"], 40)

    async def test_bundled_synthetic_es_session_produces_snapshot(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="replay",
        )
        adapter = ReplayAdapter(
            consumer,
            replay_path=replay_data_path("es_synthetic_full_session.jsonl"),
            delay_seconds=0,
        )

        await adapter.stream_market_data()
        snapshot = await consumer.process_latest_snapshot(days_to_expiry=0.01)
        breakdown = await consumer.process_expiry_breakdown(days_to_expiry=0.01)

        self.assertEqual(consumer.current_spot, 5962.75)
        self.assertEqual(len(consumer.chain_state), 7)
        self.assertIn("gamma_wall_strike", snapshot)
        self.assertIn("zero_gamma_strike", snapshot)
        self.assertIn("0DTE", breakdown)

    async def test_captured_session_replays_event_time_delays_with_speed_and_gap_cap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "captured.jsonl"
            messages = [
                _underlying_tick("2026-08-04T20:00:00Z", 5_000.0),
                _underlying_tick("2026-08-04T20:00:02Z", 5_001.0),
                _underlying_tick("2026-08-04T20:00:10Z", 5_002.0),
            ]
            await self._write_capture(replay_path, messages)
            consumer = _RecordingConsumer()
            delays = []

            async def record_sleep(delay):
                delays.append(delay)

            adapter = ReplayAdapter(
                consumer,
                replay_path,
                replay_clock="event_time",
                replay_speed=2.0,
                max_gap_seconds=4.0,
                sleep=record_sleep,
            )

            await adapter.stream_market_data()

        self.assertEqual(consumer.messages, messages)
        self.assertEqual(delays, [1.0, 2.0])
        self.assertTrue(consumer.connected)
        self.assertTrue(consumer.disconnected)

    async def test_event_time_regression_clamps_in_lenient_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "regression.jsonl"
            messages = [
                _underlying_tick("2026-08-04T20:00:02Z", 5_000.0),
                _underlying_tick("2026-08-04T20:00:01Z", 5_001.0),
            ]
            await self._write_capture(replay_path, messages)
            consumer = _RecordingConsumer()
            delays = []

            async def record_sleep(delay):
                delays.append(delay)

            adapter = ReplayAdapter(
                consumer,
                replay_path,
                replay_clock="event_time",
                strict_event_time=False,
                sleep=record_sleep,
            )

            await adapter.stream_market_data()

        self.assertEqual(consumer.messages, messages)
        self.assertTrue(all(delay >= 0 for delay in delays))
        self.assertEqual(sum(delays), 0.0)

    async def test_event_time_regression_raises_in_strict_mode_and_disconnects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "regression.jsonl"
            messages = [
                _underlying_tick("2026-08-04T20:00:02Z", 5_000.0),
                _underlying_tick("2026-08-04T20:00:01Z", 5_001.0),
            ]
            await self._write_capture(replay_path, messages)
            consumer = _RecordingConsumer()

            async def no_wait(_delay):
                return None

            adapter = ReplayAdapter(
                consumer,
                replay_path,
                replay_clock="event_time",
                strict_event_time=True,
                sleep=no_wait,
            )

            with self.assertRaisesRegex(ValueError, "event time.*regress"):
                await adapter.stream_market_data()

        self.assertEqual(consumer.messages, messages[:1])
        self.assertTrue(consumer.disconnected)

    async def test_legacy_fixed_clock_keeps_delay_after_each_message(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "legacy.jsonl"
            messages = [
                {"type": "underlying_tick", "symbol": "ES", "price": 5_000.0},
                {"type": "underlying_tick", "symbol": "ES", "price": 5_001.0},
            ]
            replay_path.write_text(
                "\n".join(json.dumps(message) for message in messages),
                encoding="utf-8",
            )
            consumer = _RecordingConsumer()
            delays = []

            async def record_sleep(delay):
                delays.append(delay)

            adapter = ReplayAdapter(
                consumer,
                replay_path,
                delay_seconds=0.25,
                replay_clock="fixed",
                sleep=record_sleep,
            )

            await adapter.stream_market_data()

        self.assertEqual(consumer.messages, messages)
        self.assertEqual(delays, [0.25, 0.25])


if __name__ == "__main__":
    unittest.main()

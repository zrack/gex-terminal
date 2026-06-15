import tempfile
import unittest
from pathlib import Path

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import validate_normalized_message


class ReplayAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_bundled_synthetic_es_session_uses_normalized_messages(self):
        adapter = ReplayAdapter(
            consumer=None,
            replay_path="sample_data/es_synthetic_full_session.jsonl",
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
            replay_path="sample_data/es_synthetic_full_session.jsonl",
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


if __name__ == "__main__":
    unittest.main()

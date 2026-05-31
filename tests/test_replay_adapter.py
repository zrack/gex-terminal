import tempfile
import unittest
from pathlib import Path

from gex_consumer import StatefulGexConsumer
from gex_engine import IntradayGexEngine
from replay_adapter import ReplayAdapter


class ReplayAdapterTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()

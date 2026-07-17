import unittest

from gex_terminal.cli import seed_demo_session
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.offline_quality import apply_quality_scenario


class OfflineQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_scenario_simulates_stale_dropped_partial_and_latency(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="demo",
            stale_after_seconds=10.0,
        )
        await seed_demo_session(consumer)
        original_strike_count = len(consumer.chain_state)

        await apply_quality_scenario(consumer, "all")
        quality = consumer.feed_quality_snapshot()

        self.assertEqual(consumer.runtime_status, "STALE")
        self.assertLess(len(consumer.chain_state), original_strike_count)
        self.assertGreaterEqual(quality["dropped_count"], 2)
        self.assertGreaterEqual(quality["latency_ms"], 325.0)
        self.assertIn("stale tick stream simulated", quality["notes"])
        self.assertIn("missing option strikes simulated", quality["notes"])


if __name__ == "__main__":
    unittest.main()

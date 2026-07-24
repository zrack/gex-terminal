import time
import unittest
import json

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


class StatefulGexConsumerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def test_demo_mode_reports_sim(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="demo")

        self.assertEqual(consumer.runtime_status, "SIM")

    def test_live_mode_reports_live_after_recent_message(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")
        consumer.mark_connected()
        consumer.last_message_at = time.monotonic()

        self.assertEqual(consumer.runtime_status, "LIVE")

    def test_live_mode_reports_stale_after_timeout(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(),
            data_mode="live",
            stale_after_seconds=1.0,
        )
        consumer.mark_connected()
        consumer.last_message_at = time.monotonic() - 2.0

        self.assertEqual(consumer.runtime_status, "STALE")

    def test_live_mode_reports_disconnected_after_connection_loss(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")

        consumer.mark_connected()
        consumer.mark_disconnected()
        quality = consumer.feed_quality_snapshot()

        self.assertEqual(consumer.runtime_status, "DISCONNECTED")
        self.assertEqual(quality["connection_state"], "DISCONNECTED")
        self.assertEqual(quality["health"], "down")

    async def test_first_underlying_tick_sets_session_open(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="replay")

        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick",
            "symbol": "ES",
            "price": 5943.25,
        }))
        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick",
            "symbol": "ES",
            "price": 5960.0,
        }))

        self.assertEqual(consumer.session_open, 5943.25)
        self.assertEqual(consumer.current_spot, 5960.0)

    def test_records_live_adapter_subscription_and_reconnect_diagnostics(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")

        consumer.mark_connected()
        consumer.mark_reconnected()
        consumer.mark_subscribed(12)

        quality = consumer.feed_quality_snapshot()

        self.assertEqual(quality["reconnect_count"], 1)
        self.assertEqual(quality["subscribed_symbol_count"], 12)
        self.assertEqual(quality["subscription_status"], "subscribed")


if __name__ == "__main__":
    unittest.main()

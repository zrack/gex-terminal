import time
import unittest

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


class StatefulGexConsumerLifecycleTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

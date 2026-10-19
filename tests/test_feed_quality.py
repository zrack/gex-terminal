import time
import unittest

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.feed_quality import build_feed_quality_snapshot


class FeedQualitySnapshotTests(unittest.TestCase):
    def test_demo_feed_reports_simulated_health(self):
        snapshot = build_feed_quality_snapshot(
            status="SIM",
            data_mode="DEMO",
            connection_state="SIM",
            message_count=18,
            malformed_count=0,
            dropped_count=0,
            entitlement_error_count=0,
            last_message_age_seconds=0.4,
            last_snapshot_age_seconds=0.1,
            stale_after_seconds=10.0,
            latency_ms=1.2,
            p95_latency_ms=2.3,
        )

        self.assertEqual(snapshot.health, "simulated")
        self.assertFalse(snapshot.stale)
        self.assertIn("simulated local feed", snapshot.notes)

    def test_stale_live_feed_reports_stale_health(self):
        snapshot = build_feed_quality_snapshot(
            status="STALE",
            data_mode="LIVE",
            connection_state="CONNECTED",
            message_count=12,
            malformed_count=0,
            dropped_count=0,
            entitlement_error_count=0,
            last_message_age_seconds=11.5,
            last_snapshot_age_seconds=4.0,
            stale_after_seconds=10.0,
        )

        self.assertEqual(snapshot.health, "stale")
        self.assertTrue(snapshot.stale)

    def test_payload_counters_degrade_feed_health(self):
        snapshot = build_feed_quality_snapshot(
            status="LIVE",
            data_mode="LIVE",
            connection_state="CONNECTED",
            message_count=10,
            malformed_count=1,
            dropped_count=2,
            entitlement_error_count=0,
            last_message_age_seconds=0.2,
            last_snapshot_age_seconds=0.1,
            stale_after_seconds=10.0,
        )

        self.assertEqual(snapshot.health, "degraded")
        self.assertIn("malformed payloads recorded", snapshot.notes)

    def test_invalid_stale_threshold_fails_closed(self):
        for threshold in (float("nan"), float("inf"), 0.0, -1.0):
            with self.subTest(threshold=threshold):
                with self.assertRaisesRegex(
                    ValueError,
                    "stale_after_seconds must be finite and greater than 0",
                ):
                    build_feed_quality_snapshot(
                        status="LIVE",
                        data_mode="LIVE",
                        connection_state="CONNECTED",
                        message_count=1,
                        malformed_count=0,
                        dropped_count=0,
                        entitlement_error_count=0,
                        last_message_age_seconds=86_400.0,
                        last_snapshot_age_seconds=86_400.0,
                        stale_after_seconds=threshold,
                    )


class ConsumerFeedQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_consumer_counts_ok_malformed_and_dropped_payloads(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(),
            target_underlying="ES",
            data_mode="live",
        )
        consumer.mark_connected()

        await consumer.update_market_state('{"type":"underlying_tick","symbol":"ES","price":5943.25}')
        await consumer.update_market_state('{"type":"underlying_tick","symbol":"NQ","price":18400.00}')
        await consumer.update_market_state('{"type":"options_volume_tick","strike":5950}')

        quality = consumer.feed_quality_snapshot(
            latency_ms=1.5,
            p95_latency_ms=2.0,
            now=time.monotonic(),
        )

        self.assertEqual(quality["message_count"], 1)
        self.assertEqual(quality["dropped_count"], 1)
        self.assertEqual(quality["malformed_count"], 1)
        self.assertEqual(quality["health"], "degraded")

    async def test_consumer_rejects_invalid_health_inputs_before_state_mutation(self):
        for field, value in (
            ("risk_free_rate", float("nan")),
            ("stale_after_seconds", float("nan")),
            ("stale_after_seconds", float("inf")),
            ("stale_after_seconds", 0.0),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, field):
                    StatefulGexConsumer(
                        IntradayGexEngine(),
                        **{field: value},
                    )

        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")
        consumer.current_spot = 5_943.25
        with self.assertRaisesRegex(ValueError, "stale_after_seconds"):
            await consumer.reset_state(stale_after_seconds=float("nan"))

        self.assertEqual(consumer.current_spot, 5_943.25)
        self.assertEqual(consumer.data_mode, "LIVE")

    async def test_one_day_old_live_source_reports_stale_with_valid_threshold(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(),
            data_mode="live",
            stale_after_seconds=10.0,
        )
        consumer.mark_connected()
        consumer.last_message_at = time.monotonic() - 86_400.0

        quality = consumer.feed_quality_snapshot(now=time.monotonic())

        self.assertEqual(consumer.runtime_status, "STALE")
        self.assertTrue(quality["stale"])
        self.assertEqual(quality["health"], "stale")


if __name__ == "__main__":
    unittest.main()

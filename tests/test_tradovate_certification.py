import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.tradovate_certification import (
    CERTIFICATION_SCHEMA,
    build_tradovate_certification_report,
    write_tradovate_certification_report,
)


class _PassingAdapter:
    def __init__(self, consumer, **kwargs):
        self.consumer = consumer
        self.environment = kwargs["environment"]
        self.target_underlying = kwargs["target_underlying"].upper()
        self.auth_capabilities = {"has_live": False, "has_market_data": True}
        self.auth_failure_reason = None
        self.md_access_token = "never-export-this-token"
        self.contract_metadata = {
            "101": {
                "contract_id": "101",
                "instrument_class": "futures_option",
            }
        }
        self._connected_once = False
        self._iv_fallback_count = 0
        self._receipt_time_fallback_count = 0

    async def authenticate(self):
        return True

    async def stream_market_data(self):
        self._connected_once = True
        self.consumer.mark_connected()
        self.consumer.mark_subscribed(2)
        self.consumer.record_provider_frame()
        await self._emit_underlying()
        await self._emit_option()

    async def _emit_underlying(self):
        await self.consumer.update_market_state(json.dumps({
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "tradovate",
            "symbol": self.target_underlying,
            "price": 5000,
            "event_time": "2026-08-04T16:00:00Z",
        }))

    async def _emit_option(self):
        await self.consumer.update_market_state(json.dumps({
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "tradovate",
            "contract_id": "101",
            "symbol": self.target_underlying,
            "strike": 5000,
            "option_type": "C",
            "volume": 10,
            "volume_semantics": "cumulative",
            "position_source": "trade_volume",
            "iv": 0.15,
            "iv_source": "provider",
            "expiry": "2026-08-05T20:00:00Z",
            "expiry_timestamp": "2026-08-05T20:00:00Z",
            "instrument_class": "futures_option",
            "pricing_model": "black_76",
            "contract_multiplier": 50,
            "event_time": "2026-08-04T16:00:01Z",
        }))


class TradovateCertificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_explicit_live_network_acknowledgement(self):
        with self.assertRaisesRegex(ValueError, "ack-live-network"):
            await build_tradovate_certification_report(
                symbol="ES",
                environment="demo",
                contract_multiplier=50,
            )

    async def test_builds_bounded_redacted_passing_report(self):
        with patch(
            "gex_terminal.tradovate_certification.TradovateAdapter",
            _PassingAdapter,
        ):
            report = await build_tradovate_certification_report(
                symbol="ES",
                environment="demo",
                contract_multiplier=50,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertEqual(report["schema"], CERTIFICATION_SCHEMA)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertTrue(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["evidence_ceiling"]["predictive_market_validity"], "unmeasured")
        self.assertNotIn("never-export-this-token", json.dumps(report))
        self.assertNotIn("name", report["authentication"])

    async def _report(self, adapter_class):
        with patch("gex_terminal.tradovate_certification.TradovateAdapter", adapter_class):
            return await build_tradovate_certification_report(
                symbol="ES", environment="demo", contract_multiplier=50,
                duration_seconds=0.01, ack_live_network=True,
            )

    async def test_nonfinite_nonpositive_and_boolean_duration_never_construct_adapter(self):
        for duration in (float("nan"), float("inf"), float("-inf"), 0, -1, True, "1", 10**1000):
            with self.subTest(duration=duration):
                with patch("gex_terminal.tradovate_certification.TradovateAdapter") as adapter:
                    with self.assertRaisesRegex(ValueError, "finite and positive"):
                        await build_tradovate_certification_report(
                            symbol="ES", environment="demo", contract_multiplier=50,
                            duration_seconds=duration, ack_live_network=True,
                        )
                adapter.assert_not_called()

    async def test_authentication_failure_cannot_certify_or_export_arbitrary_reason(self):
        class Rejected(_PassingAdapter):
            async def authenticate(self):
                self.auth_failure_reason = "unlabelled-private-provider-account"
                return False

            async def stream_market_data(self):
                raise AssertionError("authentication failure must not start streaming")

        report = await self._report(Rejected)
        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["authentication"]["failure_reason"], "authentication_failed")
        self.assertNotIn("unlabelled-private-provider-account", json.dumps(report))

    async def test_underlying_only_transport_does_not_certify_option_inputs(self):
        class UnderlyingOnly(_PassingAdapter):
            async def _emit_option(self):
                pass

        report = await self._report(UnderlyingOnly)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["transport"]["normalized_option_contracts"], 0)
        self.assertFalse(report["model_inputs"]["native_implied_volatility_observed"])

    async def test_options_without_underlying_do_not_certify_quantitative_inputs(self):
        class OptionsOnly(_PassingAdapter):
            async def _emit_underlying(self):
                pass

        report = await self._report(OptionsOnly)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["transport"]["normalized_option_contracts"], 1)

    async def test_volume_and_open_interest_states_count_as_one_option_contract(self):
        class BothPositions(_PassingAdapter):
            async def _emit_option(self):
                await super()._emit_option()
                await self.consumer.update_market_state(json.dumps({
                    "schema_version": 2,
                    "type": "options_volume_tick",
                    "provider": "tradovate",
                    "contract_id": "101",
                    "symbol": self.target_underlying,
                    "strike": 5000,
                    "option_type": "C",
                    "volume": 100,
                    "volume_semantics": "cumulative",
                    "position_source": "open_interest",
                    "iv": 0.15,
                    "iv_source": "provider",
                    "expiry": "2026-08-05T20:00:00Z",
                    "expiry_timestamp": "2026-08-05T20:00:00Z",
                    "instrument_class": "futures_option",
                    "pricing_model": "black_76",
                    "contract_multiplier": 50,
                    "event_time": "2026-08-04T16:00:02Z",
                }))

        report = await self._report(BothPositions)
        self.assertEqual(report["transport"]["normalized_option_contracts"], 1)
        self.assertTrue(report["result"]["quantitative_gex_certified"])

    async def test_untimed_legacy_underlying_cannot_certify_with_valid_v2_options(self):
        class UntimedUnderlying(_PassingAdapter):
            async def _emit_underlying(self):
                await self.consumer.update_market_state(json.dumps({
                    "type": "underlying_tick", "symbol": self.target_underlying,
                    "price": 5000,
                }))

        report = await self._report(UntimedUnderlying)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["model_inputs"]["receipt_time_fallback_tick_count"], 0)
        self.assertEqual(report["model_inputs"]["untimed_market_event_count"], 1)
        self.assertEqual(report["model_inputs"]["legacy_option_tick_count"], 0)

    async def test_timed_legacy_option_demotes_mixed_state_despite_valid_v2_option(self):
        class MixedOptions(_PassingAdapter):
            async def _emit_option(self):
                await super()._emit_option()
                await self.consumer.update_market_state(json.dumps({
                    "type": "options_volume_tick", "strike": 5000,
                    "option_type": "C", "volume": 1, "iv": 0.15,
                    "event_time": "2026-08-04T16:00:02Z",
                }))

        report = await self._report(MixedOptions)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["transport"]["normalized_option_contracts"], 1)
        self.assertEqual(report["model_inputs"]["untimed_market_event_count"], 0)
        self.assertEqual(report["model_inputs"]["legacy_option_tick_count"], 1)

    async def test_iv_or_receipt_time_fallback_prevents_quantitative_certification(self):
        for field in ("_iv_fallback_count", "_receipt_time_fallback_count"):
            with self.subTest(field=field):
                class Fallback(_PassingAdapter):
                    async def stream_market_data(self):
                        await super().stream_market_data()
                        setattr(self, field, 1)

                report = await self._report(Fallback)
                self.assertTrue(report["result"]["transport_certified"])
                self.assertFalse(report["result"]["quantitative_gex_certified"])
                self.assertEqual(report["model_inputs"]["native_implied_volatility_observed"],
                                 field != "_iv_fallback_count")

    async def test_recorded_quality_errors_prevent_quantitative_certification(self):
        for method, expected_transport in (
            ("record_entitlement_error", False),
            ("mark_subscription_error", False),
            ("record_provider_parse_error", True),
            ("record_dropped_message", True),
        ):
            with self.subTest(method=method):
                class Degraded(_PassingAdapter):
                    async def stream_market_data(self):
                        await super().stream_market_data()
                        getattr(self.consumer, method)()

                report = await self._report(Degraded)
                self.assertEqual(report["result"]["transport_certified"], expected_transport)
                self.assertFalse(report["result"]["quantitative_gex_certified"])

    async def test_post_tick_exception_is_reported_once_without_private_text(self):
        for error_type in (OSError, RuntimeError, ValueError, TypeError, TimeoutError):
            with self.subTest(error_type=error_type.__name__):
                class Failing(_PassingAdapter):
                    async def stream_market_data(self):
                        await super().stream_market_data()
                        raise error_type("unlabelled-private-account never-export-this-token")

                report = await self._report(Failing)
                self.assertFalse(report["result"]["transport_certified"])
                self.assertFalse(report["result"]["quantitative_gex_certified"])
                self.assertEqual(report["errors"], [f"{error_type.__name__}: probe_failed"])
                serialized = json.dumps(report)
                self.assertNotIn("unlabelled-private-account", serialized)
                self.assertNotIn("never-export-this-token", serialized)

    async def test_stream_disconnection_after_valid_ticks_cannot_certify(self):
        class Disconnected(_PassingAdapter):
            async def stream_market_data(self):
                await super().stream_market_data()
                self.consumer.mark_disconnected()

        report = await self._report(Disconnected)
        self.assertEqual(report["transport"]["connection_state_at_probe_end"], "DISCONNECTED")
        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])

    async def test_probe_deadline_awaits_owned_stream_cleanup_without_invalidating_healthy_window(self):
        instances = []

        class Waiting(_PassingAdapter):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.stopped = False
                instances.append(self)

            async def stream_market_data(self):
                try:
                    await super().stream_market_data()
                    await asyncio.Event().wait()
                finally:
                    self.consumer.mark_disconnected()
                    self.stopped = True

        report = await self._report(Waiting)
        self.assertTrue(instances[0].stopped)
        self.assertEqual(instances[0].consumer.connection_state, "DISCONNECTED")
        self.assertEqual(report["transport"]["connection_state_at_probe_end"], "CONNECTED")
        self.assertTrue(report["result"]["transport_certified"])
        self.assertTrue(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["errors"], [])

    async def test_errors_discovered_during_shutdown_still_prevent_certification(self):
        for method in ("mark_subscription_error", "record_entitlement_error"):
            with self.subTest(method=method):
                class LateFailure(_PassingAdapter):
                    async def stream_market_data(self):
                        try:
                            await super().stream_market_data()
                            await asyncio.Event().wait()
                        finally:
                            getattr(self.consumer, method)()
                            self.consumer.mark_disconnected()

                report = await self._report(LateFailure)
                self.assertEqual(report["transport"]["connection_state_at_probe_end"], "CONNECTED")
                self.assertFalse(report["result"]["transport_certified"])
                self.assertFalse(report["result"]["quantitative_gex_certified"])

    async def test_cleanup_failure_invalidates_report_and_omits_private_reason(self):
        class BadCleanup(_PassingAdapter):
            async def stream_market_data(self):
                try:
                    await super().stream_market_data()
                    await asyncio.Event().wait()
                finally:
                    raise OSError("private-provider-body")

        report = await self._report(BadCleanup)
        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["quantitative_gex_certified"])
        self.assertEqual(report["errors"], ["OSError: cleanup_failed"])
        self.assertNotIn("private-provider-body", json.dumps(report))

    async def test_writes_json_and_markdown_without_secret_fields(self):
        report = {
            "schema": CERTIFICATION_SCHEMA,
            "generated_at": "2026-08-04T16:00:00Z",
            "target": {"environment": "demo", "symbol": "ES"},
            "authentication": {
                "passed": False,
                "failure_reason": "no_access_token",
                "has_market_data": None,
            },
            "transport": {
                "websocket_authorized": False,
                "subscription_status": "not_subscribed",
                "subscribed_symbols": 0,
                "provider_frames": 0,
                "normalized_messages": 0,
                "normalized_option_contracts": 0,
            },
            "model_inputs": {
                "native_implied_volatility_observed": False,
                "fallback_iv_tick_count": 0,
            },
            "result": {
                "transport_certified": False,
                "quantitative_gex_certified": False,
                "adapter_registry_status": "scaffold",
            },
            "evidence_ceiling": {
                "transport": "run bounded",
                "model": "not certified",
                "predictive_market_validity": "unmeasured",
            },
            "errors": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = write_tradovate_certification_report(
                report, Path(temp_dir) / "report.json"
            )
            markdown_path = write_tradovate_certification_report(
                report, Path(temp_dir) / "report.md"
            )
            self.assertEqual(json.loads(json_path.read_text())["schema"], CERTIFICATION_SCHEMA)
            self.assertIn("Transport certified: **false**", markdown_path.read_text())


if __name__ == "__main__":
    unittest.main()

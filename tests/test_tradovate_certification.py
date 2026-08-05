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
        await self.consumer.update_market_state(json.dumps({
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "tradovate",
            "symbol": self.target_underlying,
            "price": 5000,
            "event_time": "2026-08-04T16:00:00Z",
        }))
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

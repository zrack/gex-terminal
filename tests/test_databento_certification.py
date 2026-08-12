import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.databento_certification import (
    CERTIFICATION_SCHEMA,
    build_databento_certification_report,
    write_databento_certification_report,
)


class _PassingAdapter:
    def __init__(self, consumer, **kwargs):
        self.consumer = consumer
        self.target_underlying = kwargs["target_underlying"].upper()
        self.dataset = "GLBX.MDP3"
        self.api_key = "never-export-this-key"
        self.subscription_ids = [1, 2, 3]
        self._sdk_version = "test"
        self._connected_once = False
        self._definition_count = 0
        self._underlying_quote_count = 0
        self._option_trade_count = 0
        self._inverted_iv_count = 0
        self._iv_fallback_count = 0
        self._dropped_before_definition_count = 0
        self._dropped_before_underlying_count = 0
        self._dropped_underlying_mismatch_count = 0
        self._stale_underlying_count = 0
        self._future_underlying_count = 0
        self._missing_underlying_time_count = 0
        self._crossed_underlying_book_count = 0
        self._incomplete_underlying_book_count = 0
        self.max_underlying_age_seconds = 2.0

    async def stream_market_data(self):
        self._connected_once = True
        self._definition_count = 1
        self._underlying_quote_count = 1
        self._option_trade_count = 1
        self._inverted_iv_count = 1
        self.consumer.mark_connected()
        self.consumer.mark_subscribed(2)
        self.consumer.record_provider_frame()
        await self.consumer.update_market_state(json.dumps({
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "databento",
            "symbol": self.target_underlying,
            "price": 6000.0,
            "event_time": "2026-08-06T16:00:00Z",
        }))
        await self.consumer.update_market_state(json.dumps({
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "databento",
            "contract_id": "101",
            "symbol": self.target_underlying,
            "strike": 6050.0,
            "option_type": "C",
            "volume": 10,
            "volume_semantics": "incremental",
            "position_source": "trade_volume",
            "iv": 0.22,
            "iv_source": "black_76_inverted",
            "iv_provenance": {
                "method": "black_76_bisection",
                "status": "converged",
                "option_price": 100.0,
                "option_price_source": "databento_trade",
                "underlying_price": 6000.0,
                "underlying_price_source": "databento_mbp1_midpoint",
                "underlying_price_age_ms": 1000.0,
                "maximum_underlying_age_ms": 2000.0,
                "risk_free_rate": 0.045,
                "time_to_expiry_years": 0.04,
                "iterations": 30,
                "absolute_price_error": 1e-9,
            },
            "expiry": "2026-08-20",
            "expiry_timestamp": "2026-08-20T20:00:00Z",
            "instrument_class": "futures_option",
            "pricing_model": "black_76",
            "event_time": "2026-08-06T16:00:01Z",
        }))


class DatabentoCertificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_explicit_live_network_acknowledgement(self):
        with self.assertRaisesRegex(ValueError, "ack-live-network"):
            await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
            )

    async def test_builds_redacted_passing_report(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _PassingAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertEqual(report["schema"], CERTIFICATION_SCHEMA)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertTrue(report["result"]["chain_ingestion_certified"])
        self.assertTrue(report["result"]["quantitative_gex_input_certified"])
        self.assertEqual(report["model_inputs"]["iv_sources_observed"], ["black_76_inverted"])
        self.assertEqual(report["evidence_ceiling"]["predictive_market_validity"], "unmeasured")
        self.assertNotIn("never-export-this-key", json.dumps(report))

    async def test_writes_json_and_markdown(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _PassingAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="NQ",
                contract_multiplier=20,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = write_databento_certification_report(
                report, Path(temp_dir) / "report.json"
            )
            md_path = write_databento_certification_report(
                report, Path(temp_dir) / "report.md"
            )
            self.assertEqual(json.loads(json_path.read_text())["schema"], CERTIFICATION_SCHEMA)
            self.assertIn("Transport certified: **true**", md_path.read_text())


if __name__ == "__main__":
    unittest.main()

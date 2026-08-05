import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.adapters.tradovate import (
    TradovateAdapter,
    missing_tradovate_credentials,
    validate_tradovate_credentials,
)
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.package_data import provider_fixture_path


class RecordingConsumer:
    def __init__(self):
        self.messages = []
        self.provider_frame_count = 0
        self.provider_parse_error_count = 0
        self.dropped_message_count = 0

    async def update_market_state(self, raw_message: str):
        self.messages.append(json.loads(raw_message))

    def record_provider_frame(self):
        self.provider_frame_count += 1

    def record_provider_parse_error(self):
        self.provider_parse_error_count += 1

    def record_dropped_message(self):
        self.dropped_message_count += 1


class TradovateAdapterTests(unittest.TestCase):
    def test_reports_missing_credentials_before_network_calls(self):
        with patch.dict(os.environ, {}, clear=True):
            missing = missing_tradovate_credentials()

            self.assertIn("TRADOVATE_NAME", missing)
            with self.assertRaises(ValueError):
                validate_tradovate_credentials()

    def test_extracts_contract_list_from_common_payload_shapes(self):
        payload = {"items": [{"name": "ESM6 C5950", "strikePrice": 5950}]}

        contracts = TradovateAdapter._extract_contract_list(payload)

        self.assertEqual(contracts, payload["items"])

    def test_routes_contract_discovery_fixture_to_option_metadata(self):
        fixture_path = provider_fixture_path("tradovate_contract_discovery.json")
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        contracts = TradovateAdapter._extract_contract_list(payload)
        option_metadata = {
            TradovateAdapter._contract_symbol(contract): TradovateAdapter._option_metadata(contract)
            for contract in contracts
            if TradovateAdapter._looks_like_option_contract(contract)
        }

        self.assertEqual(
            option_metadata,
            {
                "ESM6 C5950": {"strike": 5950, "option_type": "C", "iv": 0.16},
                "ESM6 P5900": {"strike": 5900, "option_type": "P", "iv": 0.18},
            },
        )

    def test_normalizes_underlying_quote(self):
        adapter = TradovateAdapter(consumer=None, target_underlying="ES")

        message = adapter._normalize_underlying_quote({
            "symbol": "ES",
            "bidPrice": 5943.0,
            "offerPrice": 5943.5,
        })

        self.assertEqual(message["type"], "underlying_tick")
        self.assertEqual(message["price"], 5943.25)

    def test_option_metadata_normalizes_contract_shape(self):
        contract = {
            "name": "ESM6 C5950",
            "strikePrice": 5950,
            "callPut": "Call",
            "impliedVol": 0.16,
        }

        self.assertTrue(TradovateAdapter._looks_like_option_contract(contract))
        self.assertEqual(TradovateAdapter._contract_symbol(contract), "ESM6 C5950")
        self.assertEqual(
            TradovateAdapter._option_metadata(contract),
            {"strike": 5950, "option_type": "C", "iv": 0.16},
        )


class TradovatePayloadFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_sanitized_md_quote_fixture(self):
        fixture_path = provider_fixture_path("tradovate_md_quotes.json")
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        consumer = RecordingConsumer()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = {
            "ESM6 C5950": {"strike": 5950, "option_type": "C", "iv": 0.16},
            "ESM6 P5900": {"strike": 5900, "option_type": "P", "iv": 0.18},
        }

        await adapter._parse_and_route("a" + json.dumps(payload))

        self.assertEqual(
            consumer.messages,
            [
                {"type": "underlying_tick", "symbol": "ES", "price": 5943.25},
                {"type": "options_volume_tick", "strike": 5950.0, "option_type": "C", "volume": 125, "iv": 0.16},
                {"type": "options_volume_tick", "strike": 5900.0, "option_type": "P", "volume": 80, "iv": 0.18},
            ],
        )
        self.assertEqual(consumer.provider_frame_count, 1)

    async def test_quarantines_bad_quotes_without_blocking_good_quotes(self):
        consumer = RecordingConsumer()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = {
            "ESM6 C5950": {"strike": 5950, "option_type": "C", "iv": 0.16},
        }
        payload = [{
            "e": "md",
            "d": {
                "quotes": [
                    {"symbol": "ESM6 C5950", "tradeVol": "bad", "impliedVol": 0.16},
                    {"symbol": "ESM6 C5950", "tradeVol": 20, "impliedVol": 0.16},
                    {"symbol": "UNKNOWN", "tradeVol": 1},
                ]
            },
        }]

        await adapter._parse_and_route("a" + json.dumps(payload))

        self.assertEqual(
            consumer.messages,
            [{"type": "options_volume_tick", "strike": 5950.0, "option_type": "C", "volume": 20, "iv": 0.16}],
        )
        self.assertEqual(consumer.provider_parse_error_count, 1)
        self.assertEqual(consumer.dropped_message_count, 1)

    async def test_live_sample_fixture_drives_consumer_and_engine(self):
        fixture_path = provider_fixture_path("tradovate_live_sample.jsonl")
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        consumer.mark_connected()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = {
            "ESM6 C5950": {"strike": 5950, "option_type": "C", "iv": 0.16},
            "ESM6 P5900": {"strike": 5900, "option_type": "P", "iv": 0.18},
            "ESM6 C5975": {"strike": 5975, "option_type": "C", "iv": 0.15},
        }

        for line in fixture_path.read_text(encoding="utf-8").splitlines():
            await adapter._parse_and_route(line)

        snapshot = await consumer.process_latest_snapshot(days_to_expiry=0.01)
        quality = consumer.feed_quality_snapshot()

        self.assertEqual(consumer.current_spot, 5943.25)
        self.assertEqual(consumer.chain_state[5950.0]["C"], 150)
        self.assertEqual(consumer.chain_state[5900.0]["P"], 115)
        self.assertEqual(consumer.chain_state[5975.0]["C"], 40)
        self.assertEqual(snapshot["strikes"], [5900.0, 5950.0, 5975.0])
        self.assertIn("gamma_wall_strike", snapshot)
        self.assertIn("zero_gamma_strike", snapshot)
        self.assertEqual(quality["frame_count"], 3)
        self.assertEqual(quality["parse_error_count"], 1)
        self.assertEqual(quality["dropped_count"], 1)
        self.assertEqual(quality["health"], "degraded")


if __name__ == "__main__":
    unittest.main()

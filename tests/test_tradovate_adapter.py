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


class RecordingConsumer:
    def __init__(self):
        self.messages = []

    async def update_market_state(self, raw_message: str):
        self.messages.append(json.loads(raw_message))


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
        fixture_path = Path(__file__).parent / "fixtures" / "tradovate_contract_discovery.json"
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
        fixture_path = Path(__file__).parent / "fixtures" / "tradovate_md_quotes.json"
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


if __name__ == "__main__":
    unittest.main()

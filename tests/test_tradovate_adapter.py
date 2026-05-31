import os
import unittest
from unittest.mock import patch

from tradovate_adapter import (
    TradovateAdapter,
    missing_tradovate_credentials,
    validate_tradovate_credentials,
)


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

    def test_normalizes_underlying_quote(self):
        adapter = TradovateAdapter(consumer=None, target_underlying="ES")

        message = adapter._normalize_underlying_quote({
            "symbol": "ES",
            "bidPrice": 5943.0,
            "offerPrice": 5943.5,
        })

        self.assertEqual(message["type"], "underlying_tick")
        self.assertEqual(message["price"], 5943.25)


if __name__ == "__main__":
    unittest.main()

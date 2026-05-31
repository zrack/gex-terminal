import unittest

from gex_terminal.market_data_adapter import dumps_normalized_message, validate_normalized_message


class MarketDataAdapterContractTests(unittest.TestCase):
    def test_accepts_underlying_tick(self):
        validate_normalized_message({
            "type": "underlying_tick",
            "symbol": "ES",
            "price": 5943.25,
        })

    def test_rejects_invalid_option_type(self):
        with self.assertRaises(ValueError):
            validate_normalized_message({
                "type": "options_volume_tick",
                "strike": 5950,
                "option_type": "X",
                "volume": 100,
            })

    def test_dumps_validated_message(self):
        payload = dumps_normalized_message({
            "type": "options_volume_tick",
            "strike": 5950,
            "option_type": "C",
            "volume": 100,
        })

        self.assertIn('"options_volume_tick"', payload)


if __name__ == "__main__":
    unittest.main()

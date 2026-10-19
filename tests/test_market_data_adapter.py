import unittest

from gex_terminal.market_data_adapter import dumps_normalized_message, validate_normalized_message


class MarketDataAdapterContractTests(unittest.TestCase):
    @staticmethod
    def _v2_option(**updates):
        message = {
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "databento",
            "contract_id": "9001001",
            "symbol": "ES",
            "expiry": "2026-06-19",
            "strike": 5950,
            "option_type": "C",
            "volume": 42,
            "iv": 0.16,
            "iv_source": "provider",
            "instrument_class": "futures_option",
            "volume_semantics": "incremental",
            "position_source": "trade_volume",
            "event_time": "2026-06-18T14:30:00Z",
        }
        message.update(updates)
        return message

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

    def test_rejects_non_positive_numeric_fields(self):
        with self.assertRaises(ValueError):
            validate_normalized_message({
                "type": "underlying_tick",
                "symbol": "ES",
                "price": 0,
            })

        with self.assertRaises(ValueError):
            validate_normalized_message({
                "type": "options_volume_tick",
                "strike": 5950,
                "option_type": "C",
                "volume": 0,
            })

    def test_dumps_validated_message(self):
        payload = dumps_normalized_message({
            "type": "options_volume_tick",
            "strike": 5950,
            "option_type": "C",
            "volume": 100,
        })

        self.assertIn('"options_volume_tick"', payload)

    def test_accepts_contract_aware_v2_option_tick(self):
        validate_normalized_message(self._v2_option())

    def test_v2_cumulative_snapshot_can_clear_a_position(self):
        validate_normalized_message(self._v2_option(
            volume=0,
            volume_semantics="cumulative",
        ))

    def test_v2_requires_identity_and_timezone_aware_event_time(self):
        missing_id = self._v2_option()
        missing_id.pop("contract_id")
        with self.assertRaisesRegex(ValueError, "contract_id"):
            validate_normalized_message(missing_id)

        with self.assertRaisesRegex(ValueError, "timezone-bearing"):
            validate_normalized_message(self._v2_option(
                event_time="2026-06-18T14:30:00",
            ))

    def test_v2_requires_position_and_iv_provenance(self):
        for field in ("position_source", "iv", "iv_source"):
            message = self._v2_option()
            message.pop(field)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_normalized_message(message)

        with self.assertRaisesRegex(ValueError, "iv_source"):
            validate_normalized_message(self._v2_option(iv_source="unknown"))

    def test_v2_rejects_invalid_semantics_and_model_conflicts(self):
        with self.assertRaisesRegex(ValueError, "volume_semantics"):
            validate_normalized_message(self._v2_option(volume_semantics="unknown"))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            validate_normalized_message(self._v2_option(pricing_model="black_scholes"))
        with self.assertRaisesRegex(ValueError, "position_source"):
            validate_normalized_message(self._v2_option(position_source="both"))

    def test_v2_accepts_optional_aggressor_direction_provenance(self):
        validate_normalized_message(self._v2_option(
            aggressor_side="buy",
            direction_source="provider",
        ))

    def test_v2_direction_requires_incremental_trade_volume_and_provenance(self):
        with self.assertRaisesRegex(ValueError, "direction_source provenance"):
            validate_normalized_message(self._v2_option(aggressor_side="buy"))
        with self.assertRaisesRegex(ValueError, "incremental"):
            validate_normalized_message(self._v2_option(
                aggressor_side="sell",
                direction_source="quote_inference",
                volume_semantics="cumulative",
            ))
        with self.assertRaisesRegex(ValueError, "position_source=trade_volume"):
            validate_normalized_message(self._v2_option(
                aggressor_side="sell",
                direction_source="provider",
                position_source="open_interest",
            ))

    def test_v2_rejects_non_finite_numbers(self):
        with self.assertRaises(ValueError):
            validate_normalized_message(self._v2_option(strike=float("nan")))


if __name__ == "__main__":
    unittest.main()

import unittest

from gex_terminal.implied_volatility import (
    black_76_option_price,
    invert_black_76_iv,
)


class Black76ImpliedVolatilityTests(unittest.TestCase):
    def test_round_trips_call_and_put_prices(self):
        for option_type in ("C", "P"):
            price = black_76_option_price(
                futures_price=6000.0,
                strike=6050.0,
                time_to_expiry_years=14.0 / 365.0,
                risk_free_rate=0.045,
                volatility=0.22,
                option_type=option_type,
            )

            result = invert_black_76_iv(
                option_price=price,
                futures_price=6000.0,
                strike=6050.0,
                time_to_expiry_years=14.0 / 365.0,
                risk_free_rate=0.045,
                option_type=option_type,
            )

            self.assertEqual(result.status, "converged")
            self.assertAlmostEqual(result.iv, 0.22, places=7)
            self.assertLessEqual(result.absolute_price_error, 1e-8)

    def test_rejects_price_outside_no_arbitrage_bounds(self):
        result = invert_black_76_iv(
            option_price=7000.0,
            futures_price=6000.0,
            strike=6050.0,
            time_to_expiry_years=14.0 / 365.0,
            risk_free_rate=0.045,
            option_type="C",
        )

        self.assertIsNone(result.iv)
        self.assertEqual(result.status, "outside_no_arbitrage_bounds")

    def test_intrinsic_boundary_does_not_invent_positive_iv(self):
        result = invert_black_76_iv(
            option_price=0.000000001,
            futures_price=6000.0,
            strike=6050.0,
            time_to_expiry_years=14.0 / 365.0,
            risk_free_rate=0.045,
            option_type="C",
        )

        self.assertIsNone(result.iv)
        self.assertEqual(result.status, "at_intrinsic_boundary")


if __name__ == "__main__":
    unittest.main()

import unittest

import numpy as np

from gex_terminal.engine import IntradayGexEngine


class IntradayGexEngineTests(unittest.TestCase):
    def test_interpolates_zero_gamma_between_sign_changes(self):
        strikes = np.array([100.0, 110.0])
        net_gex = np.array([-50.0, 50.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 105.0)

    def test_zero_gamma_falls_back_to_nearest_absolute_exposure_without_sign_change(self):
        strikes = np.array([100.0, 110.0, 120.0])
        net_gex = np.array([80.0, 20.0, 40.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 110.0)

    def test_compute_matrix_returns_gamma_and_nearest_zero_strike(self):
        engine = IntradayGexEngine(multiplier=50)

        matrix = engine.compute_intraday_gex_matrix(
            spot_price=100.0,
            strikes=np.array([95.0, 100.0, 105.0]),
            days_to_expiry=1.0,
            risk_free_rate=0.045,
            implied_vols=np.array([0.2, 0.2, 0.2]),
            accumulated_call_vol=np.array([10.0, 20.0, 100.0]),
            accumulated_put_vol=np.array([100.0, 20.0, 10.0]),
        )

        self.assertEqual(len(matrix["gammas"]), 3)
        self.assertIn("nearest_zero_strike", matrix)
        self.assertGreaterEqual(matrix["zero_gamma_strike"], 95.0)
        self.assertLessEqual(matrix["zero_gamma_strike"], 105.0)


if __name__ == "__main__":
    unittest.main()

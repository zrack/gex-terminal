import unittest

import numpy as np

from gex_terminal.engine import IntradayGexEngine


class WallAndConcentrationTests(unittest.TestCase):
    def _matrix(self):
        engine = IntradayGexEngine(multiplier=50)
        return engine.compute_intraday_gex_matrix(
            spot_price=100.0,
            strikes=np.array([90.0, 95.0, 100.0, 105.0, 110.0]),
            days_to_expiry=1.0,
            risk_free_rate=0.045,
            implied_vols=np.array([0.2, 0.2, 0.2, 0.2, 0.2]),
            accumulated_call_vol=np.array([10.0, 50.0, 400.0, 900.0, 50.0]),
            accumulated_put_vol=np.array([800.0, 300.0, 200.0, 20.0, 10.0]),
        )

    def test_matrix_exposes_call_and_put_walls(self):
        matrix = self._matrix()
        self.assertIn("call_wall_strike", matrix)
        self.assertIn("put_wall_strike", matrix)
        # heavy call volume sits above spot; heavy put volume below
        self.assertGreaterEqual(matrix["call_wall_strike"], 100.0)
        self.assertLessEqual(matrix["put_wall_strike"], 100.0)

    def test_concentration_ratio_is_a_fraction(self):
        matrix = self._matrix()
        self.assertGreater(matrix["concentration_ratio"], 0.0)
        self.assertLessEqual(matrix["concentration_ratio"], 1.0)

    def test_concentration_band_is_ordered_and_within_strikes(self):
        matrix = self._matrix()
        low, high = matrix["concentration_band_low"], matrix["concentration_band_high"]
        self.assertLessEqual(low, high)
        self.assertGreaterEqual(low, 90.0)
        self.assertLessEqual(high, 110.0)


class ConcentrationBandUnitTests(unittest.TestCase):
    def test_single_dominant_strike_collapses_band(self):
        strikes = np.array([90.0, 100.0, 110.0])
        abs_net = np.array([1.0, 100.0, 1.0])
        low, high = IntradayGexEngine.concentration_band(strikes, abs_net, threshold=0.70)
        self.assertEqual((low, high), (100.0, 100.0))

    def test_flat_exposure_widens_band(self):
        strikes = np.array([90.0, 100.0, 110.0])
        abs_net = np.array([10.0, 10.0, 10.0])
        low, high = IntradayGexEngine.concentration_band(strikes, abs_net, threshold=0.70)
        # need at least two of the three equal strikes to reach 70%
        self.assertLess(low, high)

    def test_zero_exposure_returns_full_range(self):
        strikes = np.array([90.0, 100.0, 110.0])
        abs_net = np.array([0.0, 0.0, 0.0])
        low, high = IntradayGexEngine.concentration_band(strikes, abs_net)
        self.assertEqual((low, high), (90.0, 110.0))


if __name__ == "__main__":
    unittest.main()

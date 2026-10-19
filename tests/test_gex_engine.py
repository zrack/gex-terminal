import unittest
from math import erf, exp, log, sqrt

import numpy as np

from gex_terminal.engine import IntradayGexEngine


class IntradayGexEngineTests(unittest.TestCase):
    def test_black_scholes_gamma_matches_independent_oracle(self):
        gamma = IntradayGexEngine().calculate_gamma(
            100.0,
            np.array([100.0]),
            np.array([1.0]),
            0.05,
            np.array([0.20]),
        )

        self.assertAlmostEqual(gamma[0], 0.018762017345847, places=14)

    def test_black_scholes_carry_gamma_matches_independent_oracle(self):
        gamma = IntradayGexEngine().calculate_gamma(
            100.0,
            np.array([100.0]),
            np.array([1.0]),
            0.05,
            np.array([0.20]),
            carry_rate=0.02,
        )

        self.assertAlmostEqual(gamma[0], 0.018950578755009, places=14)

    def test_black_76_gamma_matches_independent_oracle(self):
        gamma = IntradayGexEngine().calculate_gamma(
            100.0,
            np.array([100.0]),
            np.array([1.0]),
            0.05,
            np.array([0.20]),
            pricing_model="black_76",
        )

        self.assertAlmostEqual(gamma[0], 0.018879647164533, places=14)

    def test_black_scholes_gamma_matches_price_finite_difference(self):
        spot = 100.0
        strike = 100.0
        time_to_expiry = 1.0
        risk_free_rate = 0.05
        carry_rate = 0.02
        volatility = 0.20
        step = 0.01

        def normal_cdf(value):
            return 0.5 * (1.0 + erf(value / sqrt(2.0)))

        def independent_call_price(value):
            d1 = (
                log(value / strike)
                + (risk_free_rate - carry_rate + 0.5 * volatility**2)
                * time_to_expiry
            ) / (volatility * sqrt(time_to_expiry))
            d2 = d1 - volatility * sqrt(time_to_expiry)
            return (
                value * exp(-carry_rate * time_to_expiry) * normal_cdf(d1)
                - strike
                * exp(-risk_free_rate * time_to_expiry)
                * normal_cdf(d2)
            )

        finite_difference = (
            independent_call_price(spot + step)
            - 2.0 * independent_call_price(spot)
            + independent_call_price(spot - step)
        ) / step**2
        calculated = IntradayGexEngine().calculate_gamma(
            spot,
            np.array([strike]),
            np.array([time_to_expiry]),
            risk_free_rate,
            np.array([volatility]),
            carry_rate=carry_rate,
        )[0]

        self.assertAlmostEqual(calculated, finite_difference, places=8)

    def test_black_76_gex_matches_independent_es_scaling_oracle(self):
        matrix = IntradayGexEngine(multiplier=50).compute_intraday_gex_matrix(
            spot_price=5000.0,
            strikes=np.array([5000.0]),
            days_to_expiry=1.0,
            risk_free_rate=0.045,
            implied_vols=np.array([0.15]),
            accumulated_call_vol=np.array([100.0]),
            accumulated_put_vol=np.array([0.0]),
            pricing_model="black_76",
        )

        self.assertAlmostEqual(matrix["gammas"][0], 0.010161044305958, places=14)
        self.assertAlmostEqual(matrix["call_gex"][0], 12_701_305.382447, places=6)

    def test_interpolates_zero_gamma_between_sign_changes(self):
        strikes = np.array([100.0, 110.0])
        net_gex = np.array([-50.0, 50.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 105.0)

    def test_interpolates_zero_gamma_between_uneven_adjacent_strikes(self):
        strikes = np.array([100.0, 125.0])
        net_gex = np.array([-25.0, 75.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 106.25)

    def test_exact_zero_gamma_returns_that_strike(self):
        strikes = np.array([100.0, 110.0, 120.0])
        net_gex = np.array([-50.0, 0.0, 50.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 110.0)

    def test_zero_gamma_falls_back_to_nearest_absolute_exposure_without_sign_change(self):
        strikes = np.array([100.0, 110.0, 120.0])
        net_gex = np.array([80.0, 20.0, 40.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 110.0)

    def test_zero_gamma_falls_back_for_all_negative_exposure(self):
        strikes = np.array([100.0, 110.0, 120.0])
        net_gex = np.array([-80.0, -20.0, -40.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 110.0)

    def test_multiple_sign_changes_choose_candidate_nearest_lowest_absolute_exposure(self):
        strikes = np.array([90.0, 100.0, 110.0, 120.0])
        net_gex = np.array([-10.0, 10.0, 1.0, -1.0])

        zero = IntradayGexEngine.interpolate_zero_gamma_strike(strikes, net_gex)

        self.assertEqual(zero, 115.0)

    def test_empty_zero_gamma_input_returns_zero(self):
        zero = IntradayGexEngine.interpolate_zero_gamma_strike(
            np.array([]),
            np.array([]),
        )

        self.assertEqual(zero, 0.0)

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

    def test_contract_rows_price_before_same_strike_aggregation(self):
        engine = IntradayGexEngine(multiplier=50)

        matrix = engine.compute_intraday_gex_matrix(
            spot_price=100.0,
            strikes=np.array([100.0, 100.0]),
            days_to_expiry=np.array([1.0, 30.0]),
            risk_free_rate=0.05,
            implied_vols=np.array([0.20, 0.30]),
            accumulated_call_vol=np.array([10.0, 20.0]),
            accumulated_put_vol=np.array([0.0, 0.0]),
            pricing_model=np.array(["black_scholes", "black_76"]),
        )

        self.assertEqual(matrix["contract_count"], 2)
        self.assertEqual(matrix["strikes"], [100.0])
        self.assertEqual(matrix["call_volume"], [30.0])
        self.assertEqual(matrix["pricing_models"], ["black_76", "black_scholes"])
        self.assertGreater(matrix["call_gex"][0], 0.0)

    def test_contract_specific_multipliers_scale_each_row(self):
        engine = IntradayGexEngine(multiplier=100)
        common = dict(
            spot_price=100.0,
            strikes=np.array([95.0, 105.0]),
            days_to_expiry=7.0,
            risk_free_rate=0.04,
            implied_vols=np.array([0.2, 0.2]),
            accumulated_call_vol=np.array([10.0, 10.0]),
            accumulated_put_vol=np.array([0.0, 0.0]),
        )

        baseline = engine.compute_intraday_gex_matrix(**common)
        scaled = engine.compute_intraday_gex_matrix(
            **common,
            contract_multipliers=np.array([50.0, 100.0]),
        )

        self.assertAlmostEqual(scaled["call_gex"][0], baseline["call_gex"][0] / 2)
        self.assertAlmostEqual(scaled["call_gex"][1], baseline["call_gex"][1])

    def test_call_and_put_gex_have_equal_opposite_signs(self):
        engine = IntradayGexEngine(multiplier=50)
        common = dict(
            spot_price=5000.0,
            strikes=np.array([5000.0]),
            days_to_expiry=1.0,
            risk_free_rate=0.045,
            implied_vols=np.array([0.15]),
            pricing_model="black_76",
        )
        call = engine.compute_intraday_gex_matrix(
            **common,
            accumulated_call_vol=np.array([25.0]),
            accumulated_put_vol=np.array([0.0]),
        )
        put = engine.compute_intraday_gex_matrix(
            **common,
            accumulated_call_vol=np.array([0.0]),
            accumulated_put_vol=np.array([25.0]),
        )

        self.assertGreater(call["total_net_gex"], 0.0)
        self.assertLess(put["total_net_gex"], 0.0)
        self.assertAlmostEqual(call["total_net_gex"], -put["total_net_gex"])

    def test_gex_scales_linearly_with_volume_and_multiplier(self):
        common = dict(
            spot_price=5000.0,
            strikes=np.array([5000.0]),
            days_to_expiry=1.0,
            risk_free_rate=0.045,
            implied_vols=np.array([0.15]),
            accumulated_put_vol=np.array([4.0]),
            pricing_model="black_76",
        )
        base = IntradayGexEngine(multiplier=50).compute_intraday_gex_matrix(
            **common,
            accumulated_call_vol=np.array([10.0]),
        )
        double_volume = IntradayGexEngine(multiplier=50).compute_intraday_gex_matrix(
            **{**common, "accumulated_put_vol": np.array([8.0])},
            accumulated_call_vol=np.array([20.0]),
        )
        double_multiplier = IntradayGexEngine(multiplier=100).compute_intraday_gex_matrix(
            **common,
            accumulated_call_vol=np.array([10.0]),
        )

        self.assertAlmostEqual(
            double_volume["total_net_gex"], 2.0 * base["total_net_gex"]
        )
        self.assertAlmostEqual(
            double_multiplier["total_net_gex"], 2.0 * base["total_net_gex"]
        )

    def test_contract_row_order_does_not_change_aggregated_outputs(self):
        inputs = {
            "spot_price": 100.0,
            "strikes": np.array([105.0, 95.0, 100.0, 100.0]),
            "days_to_expiry": np.array([2.0, 3.0, 7.0, 30.0]),
            "risk_free_rate": 0.04,
            "implied_vols": np.array([0.22, 0.24, 0.20, 0.30]),
            "accumulated_call_vol": np.array([8.0, 3.0, 10.0, 20.0]),
            "accumulated_put_vol": np.array([2.0, 9.0, 4.0, 1.0]),
            "pricing_model": np.array(
                ["black_scholes", "black_scholes", "black_76", "black_scholes"]
            ),
            "contract_multipliers": np.array([100.0, 100.0, 50.0, 100.0]),
        }
        order = np.array([2, 0, 3, 1])
        reordered = {
            name: value[order] if isinstance(value, np.ndarray) else value
            for name, value in inputs.items()
        }
        engine = IntradayGexEngine()

        first = engine.compute_intraday_gex_matrix(**inputs)
        second = engine.compute_intraday_gex_matrix(**reordered)

        for name in ("strikes", "call_gex", "put_gex", "net_gex", "call_volume", "put_volume"):
            np.testing.assert_allclose(first[name], second[name], rtol=0.0, atol=1e-9)
        self.assertAlmostEqual(first["total_net_gex"], second["total_net_gex"])

    def test_public_gamma_rejects_invalid_or_nonfinite_inputs(self):
        engine = IntradayGexEngine()
        valid = {
            "S": 100.0,
            "K": np.array([100.0]),
            "t": np.array([1.0]),
            "r": 0.05,
            "sigma": np.array([0.20]),
        }
        invalid_cases = (
            {"S": 0.0},
            {"S": float("inf")},
            {"K": np.array([0.0])},
            {"K": np.array([float("nan")])},
            {"t": np.array([0.0])},
            {"t": np.array([float("inf")])},
            {"r": float("nan")},
            {"sigma": np.array([0.0])},
            {"sigma": np.array([float("inf")])},
        )

        for override in invalid_cases:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    engine.calculate_gamma(**{**valid, **override})

    def test_engine_rejects_non_one_dimensional_contract_arrays(self):
        engine = IntradayGexEngine()

        with self.assertRaises(ValueError):
            engine.compute_intraday_gex_matrix(
                spot_price=100.0,
                strikes=np.array([[95.0, 105.0]]),
                days_to_expiry=np.array([[1.0, 1.0]]),
                risk_free_rate=0.05,
                implied_vols=np.array([[0.20, 0.20]]),
                accumulated_call_vol=np.array([[1.0, 1.0]]),
                accumulated_put_vol=np.array([[0.0, 0.0]]),
            )

    def test_truthful_strike_profile_flip_has_no_fallback(self):
        strikes = np.array([100.0, 110.0, 120.0])
        same_sign = np.array([80.0, 20.0, 40.0])

        self.assertIsNone(IntradayGexEngine.strike_profile_flip(strikes, same_sign))
        self.assertEqual(
            IntradayGexEngine.interpolate_zero_gamma_strike(strikes, same_sign),
            110.0,
        )


if __name__ == "__main__":
    unittest.main()

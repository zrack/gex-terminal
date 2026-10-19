"""American futures pricing against an independent finite-difference engine.

Golden values were generated with test-only QuantLib 1.40's
FdBlackScholesVanillaEngine (3200 time/space nodes, checked at 1600).
The BlackScholesMertonProcess uses q=r, hence zero futures drift.  An exact
one-year ACT/365 clock with r'=r*T and sigma'=sigma*sqrt(T) preserves each
fractional maturity. QuantLib is not an application or test dependency.
Reference implementation:
https://github.com/lballabio/QuantLib/blob/v1.40/ql/pricingengines/vanilla/fdblackscholesvanillaengine.cpp
"""

import math
import unittest

import numpy as np

from gex_terminal.american_futures import (
    american_futures_option_price,
    american_futures_price_gamma,
    invert_american_futures_iv,
    numerical_provenance,
)
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.implied_volatility import black_76_option_price


def inputs(**updates):
    result = dict(futures_price=100.0, strike=100.0, time_to_expiry_years=0.5,
                  risk_free_rate=0.045, volatility=0.2, option_type="C")
    result.update(updates)
    return result


class AmericanFuturesNumericalTests(unittest.TestCase):
    def test_independent_quantlib_finite_difference_prices_and_gamma(self):
        # side, strike, maturity, rate, vol, reference price, reference gamma.
        # Reference grid price changes were <=3.83e-5 except the two-year
        # stress case (3.71e-4); gamma changes were <=1.35e-7 throughout.
        vectors = [
            ("C", 100, .5, .045, .2, 5.53554841378386, .027914677596800316),
            ("P", 100, .5, .045, .2, 5.5355484031877245, .02791467757691537),
            ("C", 80, .5, .045, .2, 20.1296877110728, .008961724594275808),
            ("P", 120, .5, .045, .2, 20.48495378441971, .014947878486627923),
            ("C", 50, .5, .045, .2, 50.0, 0.0),
            ("P", 150, .5, .045, .2, 50.0, 0.0),
            ("C", 120, .5, .045, .2, .7056460915031536, .013172038973668936),
            ("P", 80, .5, .045, .2, .3026899720354848, .007105070098317951),
            ("C", 100, 1 / 365, .045, .2, .41758332684780486, .38105115535349354),
            ("P", 110, 2, .1, .35, 22.802508129353072, .008714928109658175),
        ]
        for side, strike, maturity, rate, vol, price, gamma in vectors:
            with self.subTest(side=side, strike=strike, maturity=maturity):
                actual = american_futures_price_gamma(**inputs(
                    option_type=side, strike=strike, time_to_expiry_years=maturity,
                    risk_free_rate=rate, volatility=vol,
                ))
                self.assertAlmostEqual(actual.price, price, delta=8e-4)
                self.assertAlmostEqual(actual.gamma, gamma,
                                       delta=max(2e-8, abs(gamma) * 6e-4))

    def test_resolution_refinement_reduces_error_on_continuation_cases(self):
        for strike, side, price, gamma in [
            (100, "C", 5.53554841378386, .027914677596800316),
            (80, "C", 20.1296877110728, .008961724594275808),
            (120, "P", 20.48495378441971, .014947878486627923),
        ]:
            base = american_futures_price_gamma(**inputs(strike=strike, option_type=side))
            refined = american_futures_price_gamma(**inputs(strike=strike, option_type=side), steps=2048)
            self.assertLess(abs(refined.price - price), abs(base.price - price))
            self.assertLess(abs(refined.gamma - gamma), abs(base.gamma - gamma))

    def test_immediate_exercise_price_and_gamma_are_exact(self):
        for strike, side in [(50, "C"), (150, "P")]:
            value = american_futures_price_gamma(**inputs(strike=strike, option_type=side))
            self.assertEqual(value.price, 50.0)
            self.assertEqual(value.gamma, 0.0)
            self.assertTrue(value.exercise_now)

    def test_nonpositive_rate_limit_matches_european_model(self):
        for rate in (0.0, -0.02):
            for side in ("C", "P"):
                args = inputs(strike=110, risk_free_rate=rate, option_type=side)
                actual = american_futures_price_gamma(**args)
                self.assertEqual(actual.price, black_76_option_price(**args))
                d1 = (math.log(100 / 110) + .5 * .2 ** 2 * .5) / (.2 * math.sqrt(.5))
                gamma = math.exp(-rate * .5 - d1 ** 2 / 2) / (math.sqrt(2 * math.pi) * 100 * .2 * math.sqrt(.5))
                self.assertAlmostEqual(actual.gamma, gamma, places=15)
                self.assertFalse(actual.exercise_now)

    def test_price_is_above_european_and_immediate_exercise(self):
        for strike in (80, 100, 120):
            for side in ("C", "P"):
                args = inputs(strike=strike, option_type=side)
                actual = american_futures_option_price(**args)
                self.assertGreaterEqual(actual + 1e-12, black_76_option_price(**args))
                self.assertGreaterEqual(actual, max((100 - strike) * (1 if side == "C" else -1), 0))

    def test_input_and_resolution_guards(self):
        for field, value in [("volatility", float("nan")), ("volatility", 0),
                             ("volatility", 5.01), ("futures_price", -1),
                             ("strike", float("inf")), ("time_to_expiry_years", 0),
                             ("risk_free_rate", float("nan")), ("option_type", "X")]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                american_futures_option_price(**inputs(**{field: value}))
        for steps in (True, 31, 4097, 512.0):
            with self.assertRaises(ValueError):
                american_futures_option_price(**inputs(), steps=steps)
        with self.assertRaises(ValueError):
            american_futures_option_price(**inputs(time_to_expiry_years=100, volatility=5), steps=4096)
        self.assertEqual(numerical_provenance()["tree_pair_steps"], [512, 513])

    def test_iv_round_trip_both_sides(self):
        for side in ("C", "P"):
            args = inputs(strike=110, option_type=side)
            premium = american_futures_option_price(**args)
            args.pop("volatility")
            actual = invert_american_futures_iv(**args, option_price=premium)
            self.assertEqual(actual.status, "converged")
            self.assertAlmostEqual(actual.iv, .2, places=7)
            self.assertLessEqual(actual.absolute_price_error, 1e-8)

    def test_iv_uses_undiscounted_american_bounds_and_does_not_invent_boundary_iv(self):
        args = inputs(futures_price=120, strike=100, time_to_expiry_years=1, risk_free_rate=.1)
        args.pop("volatility")
        # 19 is above European discounted intrinsic, below American exercise.
        for premium, status in [(19, "outside_no_arbitrage_bounds"),
                                (20, "at_intrinsic_boundary"),
                                (121, "outside_no_arbitrage_bounds"),
                                (float("nan"), "invalid_option_price")]:
            result = invert_american_futures_iv(**args, option_price=premium)
            self.assertIsNone(result.iv)
            self.assertEqual(result.status, status)

    def test_nonconvergence_is_unavailable(self):
        args = inputs()
        args.pop("volatility")
        result = invert_american_futures_iv(**args, option_price=5.5, maximum_iterations=1)
        self.assertIsNone(result.iv)
        self.assertEqual(result.status, "iteration_limit")


class AmericanFuturesEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = IntradayGexEngine(50)
        self.args = dict(S=100, K=np.array([120., 120.]), t=np.array([.5, .5]),
                         r=.045, sigma=np.array([.2, .2]), pricing_model="american_futures_crr")

    def test_side_specific_gamma_requires_and_respects_explicit_option_sides(self):
        gamma = self.engine.calculate_gamma(**self.args, option_types=np.array(["C", "P"]))
        self.assertNotAlmostEqual(gamma[0], gamma[1], places=5)
        for missing in (None, "X", np.array(["C"])):
            with self.assertRaises(ValueError):
                self.engine.calculate_gamma(**self.args, option_types=missing)

    def test_both_matrix_paths_apply_side_specific_american_gamma(self):
        args = dict(spot_price=100, strikes=np.array([120., 120.]), days_to_expiry=182.5,
                    risk_free_rate=.045, implied_vols=np.array([.2, .2]),
                    pricing_model="american_futures_crr", option_types=np.array(["C", "P"]))
        gamma = self.engine.calculate_gamma(**self.args, option_types=np.array(["C", "P"]))
        expected = (gamma[0] - gamma[1]) * 100 * 100 * .01 * 50
        matrix = self.engine.compute_intraday_gex_matrix(**args, accumulated_call_vol=np.array([1., 0.]),
                                                         accumulated_put_vol=np.array([0., 1.]))
        self.assertAlmostEqual(matrix["total_net_gex"], expected, places=9)
        directional = self.engine.compute_directionalized_gex_matrix(
            **args, buy_aggressor_vol=np.array([0., 1.]), sell_aggressor_vol=np.array([1., 0.]),
            unknown_aggressor_vol=np.zeros(2))
        self.assertAlmostEqual(directional["total_net_gex"], expected, places=9)

    def test_mixed_models_preserve_legacy_gamma_exactly(self):
        args = {key: value for key, value in self.args.items() if key != "pricing_model"}
        legacy = self.engine.calculate_gamma(**args, pricing_model="black_76")
        mixed = self.engine.calculate_gamma(**args, pricing_model=np.array(["black_76", "american_futures_crr"]),
                                             option_types=np.array(["C", "P"]))
        self.assertEqual(legacy[0], mixed[0])


if __name__ == "__main__":
    unittest.main()

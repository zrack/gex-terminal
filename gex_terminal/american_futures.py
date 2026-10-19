"""Numerical, premium-paid American options on lognormal futures.

The futures process has zero risk-neutral drift.  Discounted continuation is
compared with immediate, undiscounted exercise at every CRR node.  Adjacent
even/odd trees and a European Black-76 control variate reduce lattice bias.
This is a numerical constant-volatility model, not observed market fair value.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np

from .implied_volatility import (
    ImpliedVolatilityResult,
    _validate_common_inputs,
    black_76_option_price,
    invert_black_76_iv,
)


DEFAULT_TREE_STEPS = 512
NUMERICAL_METHOD = "crr_even_odd_european_control_variate"


@dataclass(frozen=True)
class AmericanFuturesResult:
    price: float
    gamma: float
    steps: int
    method: str
    exercise_now: bool


def numerical_provenance(steps: int = DEFAULT_TREE_STEPS) -> dict:
    """Describe resolution; solver residuals are not discretization errors."""
    _validate_steps(steps)
    return {
        "numerical_method": NUMERICAL_METHOD,
        "tree_steps": steps,
        "tree_pair_steps": [steps, steps + 1],
        "futures_risk_neutral_drift": 0.0,
        "early_exercise_modeled": True,
        "gamma_method": "second_layer_delta_slopes_with_european_control_variate",
        "error_scope": "numerical_model_only",
        "empirical_pricing_accuracy": "unmeasured",
    }


def _validate_steps(steps: int) -> None:
    if isinstance(steps, bool) or not isinstance(steps, int) or not 32 <= steps <= 4096:
        raise ValueError("tree steps must be an integer from 32 through 4096")


def american_futures_price_gamma(
    *, futures_price: float, strike: float, time_to_expiry_years: float,
    risk_free_rate: float, volatility: float, option_type: str,
    steps: int = DEFAULT_TREE_STEPS,
) -> AmericanFuturesResult:
    """Return premium in index points and gamma with respect to futures price.

    Gamma uses the deltas at the second lattice layer, rather than a small bump
    of the piecewise-linear lattice payoff.  Immediate exercise has zero gamma.
    The bounded cache is particularly useful when Terminal and Wind Tunnel
    reprice the same checkpoint.  No provider or optional numerical dependency
    is used.
    """
    _validate_common_inputs(
        futures_price=futures_price, strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate, option_type=option_type,
    )
    _validate_steps(steps)
    if not math.isfinite(volatility) or not 0 < volatility <= 5.0:
        raise ValueError("volatility must be finite, positive, and at most 5")
    # Bound exponential tails and discount factors before allocating a lattice.
    if (volatility * math.sqrt(time_to_expiry_years * (steps + 1)) > 500
            or abs(risk_free_rate * time_to_expiry_years) > 500):
        raise ValueError("American lattice exponent exceeds the numerical domain")
    jump = volatility * math.sqrt(time_to_expiry_years / (steps + 1))
    if jump < 1e-14:
        raise ValueError("American lattice jumps are below numerical resolution")
    return _price_gamma_cached(
        float(futures_price), float(strike), float(time_to_expiry_years),
        float(risk_free_rate), float(volatility), option_type.upper(), steps,
    )


def american_futures_option_price(**kwargs) -> float:
    """Return the premium from :func:`american_futures_price_gamma`."""
    return american_futures_price_gamma(**kwargs).price


@lru_cache(maxsize=4096)
def _price_gamma_cached(f: float, k: float, t: float, r: float, sigma: float,
                        side: str, steps: int) -> AmericanFuturesResult:
    european = black_76_option_price(
        futures_price=f, strike=k, time_to_expiry_years=t,
        risk_free_rate=r, volatility=sigma, option_type=side,
    )
    d1 = (math.log(f / k) + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    european_gamma = math.exp(-r * t - 0.5 * d1 * d1) / (
        math.sqrt(2 * math.pi) * f * sigma * math.sqrt(t)
    )
    # Convex payoff of a futures martingale with nonpositive discount rate:
    # waiting dominates immediate exercise.  This is an exact model limit.
    if r <= 0:
        return AmericanFuturesResult(european, european_gamma, steps,
                                     NUMERICAL_METHOD, False)

    sign = 1 if side == "C" else -1
    intrinsic = max(sign * (f - k), 0.0)
    prices, gammas = [], []
    for count in (steps, steps + 1):
        american, gamma_a, european_tree, gamma_e = _tree(
            f, k, t, r, sigma, sign, count,
        )
        # A tree already exercising at its root is exact intrinsic there.  A
        # control variate must not add optionality to that exercise decision.
        exercise_tolerance = max(1e-12, max(f, k) * 1e-12)
        if american <= intrinsic + exercise_tolerance and intrinsic > 0:
            prices.append(intrinsic)
            gammas.append(0.0)
        else:
            corrected = american - european_tree + european
            if corrected <= intrinsic:
                prices.append(intrinsic)
                gammas.append(0.0)
            else:
                prices.append(corrected)
                gammas.append(gamma_a - gamma_e + european_gamma)
    price = 0.5 * (prices[0] + prices[1])
    gamma = 0.5 * (gammas[0] + gammas[1])
    # Material negative gamma signals a failed numerical approximation.  Do
    # not silently turn it into European gamma or a plausible positive value.
    if not math.isfinite(price) or not math.isfinite(gamma) or gamma < -1e-12:
        raise ValueError("American lattice produced invalid price or gamma")
    return AmericanFuturesResult(price, max(0.0, gamma), steps, NUMERICAL_METHOD,
                                 intrinsic > 0 and price == intrinsic)


def _tree(f: float, k: float, t: float, r: float, sigma: float,
          sign: int, count: int) -> tuple[float, float, float, float]:
    dt = t / count
    jump = sigma * math.sqrt(dt)
    up = math.exp(jump)
    probability_up = 1.0 / (1.0 + up)  # (1-d)/(u-d), zero futures drift
    discount = math.exp(-r * dt)
    nodes = f * np.exp((2 * np.arange(count + 1) - count) * jump)
    american = np.maximum(sign * (nodes - k), 0.0)
    european = american.copy()
    gamma_a = gamma_e = 0.0
    for level in range(count - 1, -1, -1):
        american = discount * ((1 - probability_up) * american[:-1]
                               + probability_up * american[1:])
        european = discount * ((1 - probability_up) * european[:-1]
                               + probability_up * european[1:])
        nodes = nodes[:-1] * up
        american = np.maximum(american, sign * (nodes - k))
        if level == 2:
            lower = f * math.exp(-2 * jump)
            upper = f * math.exp(2 * jump)
            # expm1 keeps the two price differences accurate at tiny vol/DTE.
            upper_gap = f * math.expm1(2 * jump)
            lower_gap = -f * math.expm1(-2 * jump)
            width = 0.5 * (upper - lower)
            gamma_a = ((american[2] - american[1]) / upper_gap
                       - (american[1] - american[0]) / lower_gap) / width
            gamma_e = ((european[2] - european[1]) / upper_gap
                       - (european[1] - european[0]) / lower_gap) / width
    return float(american[0]), float(gamma_a), float(european[0]), float(gamma_e)


def invert_american_futures_iv(
    *, option_price: float, futures_price: float, strike: float,
    time_to_expiry_years: float, risk_free_rate: float, option_type: str,
    minimum_volatility: float = 1e-6, maximum_volatility: float = 5.0,
    price_tolerance: float = 1e-8, maximum_iterations: int = 160,
    steps: int = DEFAULT_TREE_STEPS,
) -> ImpliedVolatilityResult:
    """Invert the numerical American model without manufacturing boundary IVs."""
    _validate_common_inputs(
        futures_price=futures_price, strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate, option_type=option_type,
    )
    _validate_steps(steps)
    if (not math.isfinite(minimum_volatility)
            or not math.isfinite(maximum_volatility)
            or not 0 < minimum_volatility < maximum_volatility <= 5.0):
        raise ValueError("volatility bounds must be finite, positive, ordered, and at most 5")
    if (not math.isfinite(price_tolerance) or price_tolerance <= 0
            or isinstance(maximum_iterations, bool)
            or not isinstance(maximum_iterations, int) or not 1 <= maximum_iterations <= 256):
        raise ValueError("solver tolerance must be positive and iteration limit from 1 through 256")
    if not math.isfinite(option_price) or option_price <= 0:
        return ImpliedVolatilityResult(None, "invalid_option_price", 0, None)
    if risk_free_rate <= 0:
        return invert_black_76_iv(
            option_price=option_price, futures_price=futures_price, strike=strike,
            time_to_expiry_years=time_to_expiry_years, risk_free_rate=risk_free_rate,
            option_type=option_type, minimum_volatility=minimum_volatility,
            maximum_volatility=maximum_volatility, price_tolerance=price_tolerance,
            maximum_iterations=maximum_iterations,
        )
    sign = 1 if option_type.upper() == "C" else -1
    intrinsic = max(sign * (futures_price - strike), 0.0)
    upper = futures_price if sign == 1 else strike
    tolerance = max(price_tolerance, upper * 1e-12)
    if option_price < intrinsic - tolerance or option_price > upper + tolerance:
        return ImpliedVolatilityResult(None, "outside_no_arbitrage_bounds", 0, None)
    if option_price <= intrinsic + tolerance:
        return ImpliedVolatilityResult(None, "at_intrinsic_boundary", 0,
                                       abs(option_price - intrinsic))
    arguments = dict(futures_price=futures_price, strike=strike,
                     time_to_expiry_years=time_to_expiry_years,
                     risk_free_rate=risk_free_rate, option_type=option_type, steps=steps)
    low, high = minimum_volatility, maximum_volatility
    low_price = american_futures_option_price(**arguments, volatility=low)
    high_price = american_futures_option_price(**arguments, volatility=high)
    if option_price < low_price - tolerance:
        return ImpliedVolatilityResult(None, "below_solver_range", 0,
                                       abs(option_price - low_price))
    if option_price > high_price + tolerance:
        return ImpliedVolatilityResult(None, "above_solver_range", 0,
                                       abs(option_price - high_price))
    for iteration in range(1, maximum_iterations + 1):
        mid = 0.5 * (low + high)
        price = american_futures_option_price(**arguments, volatility=mid)
        error = abs(price - option_price)
        if error <= price_tolerance:
            return ImpliedVolatilityResult(mid, "converged", iteration, error)
        if price < option_price:
            low = mid
        else:
            high = mid
    # A nonconverged result must not become a priced contract downstream.
    return ImpliedVolatilityResult(None, "iteration_limit", maximum_iterations, error)

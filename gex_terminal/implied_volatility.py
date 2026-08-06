"""Bounded Black-76 option pricing and implied-volatility inversion."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ImpliedVolatilityResult:
    iv: float | None
    status: str
    iterations: int
    absolute_price_error: float | None


def black_76_option_price(
    *,
    futures_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str,
) -> float:
    """Return the discounted Black-76 price for a European futures option."""
    _validate_common_inputs(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate,
        option_type=option_type,
    )
    if not math.isfinite(volatility) or volatility <= 0:
        raise ValueError("volatility must be finite and positive")

    root_t = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(futures_price / strike)
        + 0.5 * volatility * volatility * time_to_expiry_years
    ) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    discount = math.exp(-risk_free_rate * time_to_expiry_years)
    if option_type.upper() == "C":
        return discount * (
            futures_price * _normal_cdf(d1) - strike * _normal_cdf(d2)
        )
    return discount * (
        strike * _normal_cdf(-d2) - futures_price * _normal_cdf(-d1)
    )


def invert_black_76_iv(
    *,
    option_price: float,
    futures_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    option_type: str,
    minimum_volatility: float = 1e-6,
    maximum_volatility: float = 5.0,
    price_tolerance: float = 1e-8,
    maximum_iterations: int = 160,
) -> ImpliedVolatilityResult:
    """Invert a Black-76 option price using a deterministic bisection solver.

    Invalid or boundary prices return an explicit status instead of silently
    manufacturing an IV. The caller decides whether to quarantine the tick or
    use a separately labeled fallback.
    """
    _validate_common_inputs(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate,
        option_type=option_type,
    )
    if not math.isfinite(option_price) or option_price <= 0:
        return ImpliedVolatilityResult(None, "invalid_option_price", 0, None)
    if (
        not math.isfinite(minimum_volatility)
        or not math.isfinite(maximum_volatility)
        or minimum_volatility <= 0
        or maximum_volatility <= minimum_volatility
    ):
        raise ValueError("volatility bounds must be finite, positive, and ordered")
    if price_tolerance <= 0 or maximum_iterations <= 0:
        raise ValueError("solver tolerance and iteration limit must be positive")

    discount = math.exp(-risk_free_rate * time_to_expiry_years)
    if option_type.upper() == "C":
        intrinsic = discount * max(futures_price - strike, 0.0)
        upper_bound = discount * futures_price
    else:
        intrinsic = discount * max(strike - futures_price, 0.0)
        upper_bound = discount * strike
    bound_tolerance = max(price_tolerance, upper_bound * 1e-12)
    if option_price < intrinsic - bound_tolerance or option_price > upper_bound + bound_tolerance:
        return ImpliedVolatilityResult(None, "outside_no_arbitrage_bounds", 0, None)
    if option_price <= intrinsic + bound_tolerance:
        return ImpliedVolatilityResult(None, "at_intrinsic_boundary", 0, abs(option_price - intrinsic))

    low = minimum_volatility
    high = maximum_volatility
    low_price = black_76_option_price(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate,
        volatility=low,
        option_type=option_type,
    )
    high_price = black_76_option_price(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        risk_free_rate=risk_free_rate,
        volatility=high,
        option_type=option_type,
    )
    if option_price < low_price - bound_tolerance:
        return ImpliedVolatilityResult(None, "below_solver_range", 0, abs(option_price - low_price))
    if option_price > high_price + bound_tolerance:
        return ImpliedVolatilityResult(None, "above_solver_range", 0, abs(option_price - high_price))

    error = None
    for iteration in range(1, maximum_iterations + 1):
        mid = 0.5 * (low + high)
        model_price = black_76_option_price(
            futures_price=futures_price,
            strike=strike,
            time_to_expiry_years=time_to_expiry_years,
            risk_free_rate=risk_free_rate,
            volatility=mid,
            option_type=option_type,
        )
        error = abs(model_price - option_price)
        if error <= price_tolerance:
            return ImpliedVolatilityResult(mid, "converged", iteration, error)
        if model_price < option_price:
            low = mid
        else:
            high = mid

    iv = 0.5 * (low + high)
    return ImpliedVolatilityResult(iv, "iteration_limit", maximum_iterations, error)


def _validate_common_inputs(
    *,
    futures_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    option_type: str,
) -> None:
    for name, value in (
        ("futures_price", futures_price),
        ("strike", strike),
        ("time_to_expiry_years", time_to_expiry_years),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if not math.isfinite(risk_free_rate):
        raise ValueError("risk_free_rate must be finite")
    if option_type.upper() not in {"C", "P"}:
        raise ValueError("option_type must be C or P")


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))

"""Deterministic property and differential evidence for the GEX model."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.implied_volatility import black_76_option_price, invert_black_76_iv
from gex_terminal.market_data_adapter import dumps_normalized_message


MODEL_PROPERTY_SCHEMA = "gex-terminal.model-property-evidence.v1"


async def build_model_property_report() -> dict[str, Any]:
    checks = [
        _black_76_round_trip_check(),
        _black_76_put_call_parity_check(),
        _black_76_gamma_differential_check(),
        _matrix_permutation_and_scaling_check(),
        await _position_state_semantics_check(),
        _time_to_expiry_boundary_check(),
        _nonfinite_failure_check(),
    ]
    return {
        "schema": MODEL_PROPERTY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": checks,
        "result": {
            "passed": all(check["passed"] for check in checks),
            "passed_checks": sum(check["passed"] for check in checks),
            "total_checks": len(checks),
            "predictive_validity": "unmeasured",
        },
        "evidence_ceiling": (
            "deterministic numerical, state, and metamorphic properties only; not market-data "
            "accuracy, dealer positioning, forecast validity, or live profitability"
        ),
    }


def write_model_property_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("model property output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _black_76_round_trip_check() -> dict[str, Any]:
    errors = []
    cases = 0
    for futures in (100.0, 5000.0):
        for moneyness in (0.95, 1.0, 1.05):
            for years in (30.0 / 365.0, 180.0 / 365.0):
                for volatility in (0.15, 0.35):
                    for option_type in ("C", "P"):
                        strike = futures * moneyness
                        price = black_76_option_price(
                            futures_price=futures,
                            strike=strike,
                            time_to_expiry_years=years,
                            risk_free_rate=0.045,
                            volatility=volatility,
                            option_type=option_type,
                        )
                        inversion = invert_black_76_iv(
                            option_price=price,
                            futures_price=futures,
                            strike=strike,
                            time_to_expiry_years=years,
                            risk_free_rate=0.045,
                            option_type=option_type,
                        )
                        cases += 1
                        if inversion.iv is None:
                            errors.append(f"{futures}:{moneyness}:{years}:{volatility}:{option_type}:{inversion.status}")
                        else:
                            errors.append(abs(inversion.iv - volatility))
    numeric_errors = [value for value in errors if isinstance(value, float)]
    failures = [value for value in errors if not isinstance(value, float)]
    maximum_error = max(numeric_errors, default=math.inf)
    passed = not failures and maximum_error <= 1e-6
    return {
        "name": "black_76_price_iv_round_trip",
        "cases": cases,
        "maximum_absolute_iv_error": maximum_error,
        "failures": failures[:5],
        "passed": passed,
    }


def _black_76_put_call_parity_check() -> dict[str, Any]:
    errors = []
    for futures in (100.0, 5000.0):
        for strike in (futures * 0.9, futures, futures * 1.1):
            for years in (7.0 / 365.0, 0.5):
                call = black_76_option_price(
                    futures_price=futures,
                    strike=strike,
                    time_to_expiry_years=years,
                    risk_free_rate=0.045,
                    volatility=0.2,
                    option_type="C",
                )
                put = black_76_option_price(
                    futures_price=futures,
                    strike=strike,
                    time_to_expiry_years=years,
                    risk_free_rate=0.045,
                    volatility=0.2,
                    option_type="P",
                )
                expected = math.exp(-0.045 * years) * (futures - strike)
                errors.append(abs((call - put) - expected))
    maximum_error = max(errors)
    return {
        "name": "black_76_put_call_parity",
        "cases": len(errors),
        "maximum_absolute_price_error": maximum_error,
        "passed": maximum_error <= 1e-9,
    }


def _black_76_gamma_differential_check() -> dict[str, Any]:
    engine = IntradayGexEngine(multiplier=50)
    errors = []
    for futures in (100.0, 5000.0):
        for strike in (futures * 0.9, futures, futures * 1.1):
            years = 30.0 / 365.0
            step = futures * 1e-4
            center = black_76_option_price(
                futures_price=futures,
                strike=strike,
                time_to_expiry_years=years,
                risk_free_rate=0.045,
                volatility=0.2,
                option_type="C",
            )
            high = black_76_option_price(
                futures_price=futures + step,
                strike=strike,
                time_to_expiry_years=years,
                risk_free_rate=0.045,
                volatility=0.2,
                option_type="C",
            )
            low = black_76_option_price(
                futures_price=futures - step,
                strike=strike,
                time_to_expiry_years=years,
                risk_free_rate=0.045,
                volatility=0.2,
                option_type="C",
            )
            differential = (high - 2.0 * center + low) / (step * step)
            analytical = float(engine.calculate_gamma(
                futures,
                np.array([strike]),
                np.array([years]),
                0.045,
                np.array([0.2]),
                pricing_model="black_76",
            )[0])
            errors.append(abs(differential - analytical) / max(abs(analytical), 1e-12))
    maximum_error = max(errors)
    return {
        "name": "black_76_gamma_finite_difference",
        "cases": len(errors),
        "maximum_relative_error": maximum_error,
        "passed": maximum_error <= 1e-5,
    }


def _matrix_permutation_and_scaling_check() -> dict[str, Any]:
    engine = IntradayGexEngine(multiplier=50)
    strikes = np.array([5900.0, 5950.0, 6000.0, 6050.0])
    ivs = np.array([0.18, 0.16, 0.15, 0.17])
    calls = np.array([100.0, 250.0, 400.0, 150.0])
    puts = np.array([300.0, 200.0, 100.0, 50.0])
    base = engine.compute_intraday_gex_matrix(
        6000.0, strikes, 7.0, 0.045, ivs, calls, puts, pricing_model="black_76"
    )
    order = np.array([2, 0, 3, 1])
    permuted = engine.compute_intraday_gex_matrix(
        6000.0,
        strikes[order],
        7.0,
        0.045,
        ivs[order],
        calls[order],
        puts[order],
        pricing_model="black_76",
    )
    scaled = engine.compute_intraday_gex_matrix(
        6000.0, strikes, 7.0, 0.045, ivs, calls * 3.0, puts * 3.0,
        pricing_model="black_76",
    )
    order_equal = bool(np.array_equal(base["strikes"], permuted["strikes"]))
    values_equal = bool(np.allclose(base["net_gex"], permuted["net_gex"], rtol=0, atol=1e-8))
    scale_equal = math.isclose(
        float(scaled["total_net_gex"]),
        3.0 * float(base["total_net_gex"]),
        rel_tol=1e-12,
        abs_tol=1e-6,
    )
    return {
        "name": "matrix_permutation_and_linear_scaling",
        "order_equal": order_equal,
        "values_equal": values_equal,
        "scale_equal": scale_equal,
        "passed": order_equal and values_equal and scale_equal,
    }


async def _position_state_semantics_check() -> dict[str, Any]:
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=50), target_underlying="ES", data_mode="replay"
    )
    await consumer.update_market_state(dumps_normalized_message({
        "schema_version": 2,
        "type": "underlying_tick",
        "provider": "property",
        "symbol": "ES",
        "price": 6000,
        "event_time": "2026-08-19T16:00:00Z",
    }))
    base = {
        "schema_version": 2,
        "type": "options_volume_tick",
        "provider": "property",
        "contract_id": "oi-call",
        "symbol": "ES",
        "strike": 6000,
        "option_type": "C",
        "volume": 100,
        "volume_semantics": "cumulative",
        "position_source": "open_interest",
        "iv": 0.2,
        "iv_source": "provider",
        "instrument_class": "futures_option",
        "pricing_model": "black_76",
        "expiry": "2026-09-18",
        "expiry_timestamp": "2026-09-18T20:00:00Z",
        "event_time": "2026-08-19T16:00:01Z",
        "aggressor_side": "unknown",
        "direction_source": "unknown",
        "sequence": 1,
    }
    await consumer.update_market_state(dumps_normalized_message(base))
    await consumer.update_market_state(dumps_normalized_message({**base, "volume": 125, "sequence": 2}))
    await consumer.update_market_state(dumps_normalized_message({**base, "volume": 999, "sequence": 2}))
    state = consumer.contract_state[("property", "oi-call", "open_interest")]
    passed = state["accumulated_volume"] == 125 and consumer.duplicate_message_count == 1
    return {
        "name": "cumulative_replacement_and_duplicate_idempotence",
        "accumulated_volume": state["accumulated_volume"],
        "duplicate_messages": consumer.duplicate_message_count,
        "passed": passed,
    }


def _nonfinite_failure_check() -> dict[str, Any]:
    engine = IntradayGexEngine(multiplier=50)
    rejected = 0
    for bad_value in (math.nan, math.inf, -math.inf):
        try:
            engine.calculate_gamma(
                6000.0,
                np.array([6000.0]),
                np.array([7.0 / 365.0]),
                0.045,
                np.array([bad_value]),
                pricing_model="black_76",
            )
        except ValueError:
            rejected += 1
    return {
        "name": "nonfinite_volatility_fails_closed",
        "cases": 3,
        "rejected": rejected,
        "passed": rejected == 3,
    }


def _time_to_expiry_boundary_check() -> dict[str, Any]:
    engine = IntradayGexEngine(multiplier=50)
    rejected = 0
    for years in (0.0, -1.0 / 365.0, math.nan):
        try:
            engine.calculate_gamma(
                6000.0,
                np.array([6000.0]),
                np.array([years]),
                0.045,
                np.array([0.2]),
                pricing_model="black_76",
            )
        except ValueError:
            rejected += 1
    return {
        "name": "time_to_expiry_boundary_fails_closed",
        "cases": 3,
        "rejected": rejected,
        "passed": rejected == 3,
    }

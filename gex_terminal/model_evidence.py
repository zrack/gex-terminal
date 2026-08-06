"""Bounded numerical evidence for the GEX pricing and aggregation model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from gex_terminal.engine import IntradayGexEngine


MODEL_EVIDENCE_SCHEMA = "gex-terminal.model-evidence.v1"
MODEL_VERSION = "gex-terminal.gex-model.v2"
SNAPSHOT_SCHEMA_VERSION = 2
DAY_COUNT_CONVENTION = "ACT/365"
GEX_UNITS = "USD gamma exposure per 1% underlying move"

_REFERENCE_CASES = (
    {
        "name": "black_scholes_atm",
        "spot": 100.0,
        "strike": 100.0,
        "time_years": 1.0,
        "rate": 0.05,
        "volatility": 0.20,
        "pricing_model": "black_scholes",
        "carry_rate": 0.0,
        "expected_gamma": 0.018762017345847,
    },
    {
        "name": "black_scholes_with_carry",
        "spot": 100.0,
        "strike": 100.0,
        "time_years": 1.0,
        "rate": 0.05,
        "volatility": 0.20,
        "pricing_model": "black_scholes",
        "carry_rate": 0.02,
        "expected_gamma": 0.018950578755009,
    },
    {
        "name": "black_76_atm",
        "spot": 100.0,
        "strike": 100.0,
        "time_years": 1.0,
        "rate": 0.05,
        "volatility": 0.20,
        "pricing_model": "black_76",
        "carry_rate": 0.0,
        "expected_gamma": 0.018879647164533,
    },
)


def build_model_evidence_report() -> dict[str, Any]:
    """Run analytical-oracle and deterministic-pipeline checks.

    This evidence intentionally does not claim that GEX predicts future market
    behavior. It proves numerical implementation facts and replay determinism.
    """
    engine = IntradayGexEngine(multiplier=50)
    cases = []
    for case in _REFERENCE_CASES:
        actual = float(engine.calculate_gamma(
            case["spot"],
            np.array([case["strike"]]),
            np.array([case["time_years"]]),
            case["rate"],
            np.array([case["volatility"]]),
            pricing_model=case["pricing_model"],
            carry_rate=case["carry_rate"],
        )[0])
        expected = float(case["expected_gamma"])
        absolute_error = abs(actual - expected)
        passed = bool(np.isclose(actual, expected, rtol=1e-12, atol=1e-14))
        cases.append({
            "name": case["name"],
            "pricing_model": case["pricing_model"],
            "expected_gamma": expected,
            "actual_gamma": actual,
            "absolute_error": absolute_error,
            "rtol": 1e-12,
            "atol": 1e-14,
            "passed": passed,
        })

    es_matrix = engine.compute_intraday_gex_matrix(
        spot_price=5000.0,
        strikes=np.array([5000.0]),
        days_to_expiry=np.array([1.0]),
        risk_free_rate=0.045,
        implied_vols=np.array([0.15]),
        accumulated_call_vol=np.array([100.0]),
        accumulated_put_vol=np.array([0.0]),
        pricing_model=np.array(["black_76"]),
        contract_multipliers=np.array([50.0]),
    )
    expected_es_gex = 12_701_305.382447
    actual_es_gex = float(es_matrix["call_gex"][0])
    es_passed = bool(
        np.isclose(actual_es_gex, expected_es_gex, rtol=1e-12, atol=1e-6)
    )
    cases.append({
        "name": "es_black_76_dollar_gex_scaling",
        "pricing_model": "black_76",
        "expected_gex": expected_es_gex,
        "actual_gex": actual_es_gex,
        "absolute_error": abs(actual_es_gex - expected_es_gex),
        "rtol": 1e-12,
        "atol": 1e-6,
        "passed": es_passed,
    })

    directional = engine.compute_directionalized_gex_matrix(
        spot_price=5000.0,
        strikes=np.array([5000.0]),
        days_to_expiry=np.array([1.0]),
        risk_free_rate=0.045,
        implied_vols=np.array([0.15]),
        buy_aggressor_vol=np.array([100.0]),
        sell_aggressor_vol=np.array([25.0]),
        unknown_aggressor_vol=np.array([50.0]),
        pricing_model=np.array(["black_76"]),
        contract_multipliers=np.array([50.0]),
    )
    expected_directional_gex = expected_es_gex * -0.75
    actual_directional_gex = float(directional["total_net_gex"])
    directional_passed = bool(
        np.isclose(
            actual_directional_gex,
            expected_directional_gex,
            rtol=1e-12,
            atol=1e-6,
        )
        and np.isclose(directional["directional_coverage"], 125 / 175)
        and directional["participant_classification"] == "unobserved"
    )
    cases.append({
        "name": "aggressor_directionalized_sign_scaling_and_coverage",
        "pricing_model": "black_76",
        "expected_gex": expected_directional_gex,
        "actual_gex": actual_directional_gex,
        "absolute_error": abs(actual_directional_gex - expected_directional_gex),
        "expected_directional_coverage": 125 / 175,
        "actual_directional_coverage": directional["directional_coverage"],
        "rtol": 1e-12,
        "atol": 1e-6,
        "passed": directional_passed,
    })

    deterministic_checks = _deterministic_checks(engine)
    numerical_passed = all(case["passed"] for case in cases)
    deterministic_passed = all(check["passed"] for check in deterministic_checks)
    passed = numerical_passed and deterministic_passed
    return {
        "schema": MODEL_EVIDENCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model_contract": {
            "model_version": MODEL_VERSION,
            "day_count_convention": DAY_COUNT_CONVENTION,
            "gex_units": GEX_UNITS,
            "pricing_models": ["black_scholes", "black_76"],
            "aggregation": "price each contract row, then aggregate by strike",
            "zero_gamma_semantics": "adjacent strike-profile crossing; not an underlying-price portfolio flip",
            "parallel_models": ["gex-terminal.aggressor-directionalized.v1"],
        },
        "evidence": {
            "numerical_validity": {
                "status": "passed" if numerical_passed else "failed",
                "passed": sum(1 for case in cases if case["passed"]),
                "total": len(cases),
                "cases": cases,
            },
            "deterministic_pipeline": {
                "status": "passed" if deterministic_passed else "failed",
                "checks": deterministic_checks,
            },
            "predictive_market_validity": {
                "status": "unmeasured",
                "claim": "No predictive return, trading edge, calibration, or live P&L validity is established.",
            },
        },
        "result": {
            "passed": passed,
            "evidence_ceiling": "numerical correctness and deterministic aggregation only",
        },
    }


def _deterministic_checks(engine: IntradayGexEngine) -> list[dict[str, Any]]:
    common = {
        "spot_price": 100.0,
        "strikes": np.array([95.0, 100.0, 105.0]),
        "days_to_expiry": np.array([1.0, 3.0, 7.0]),
        "risk_free_rate": 0.04,
        "implied_vols": np.array([0.22, 0.20, 0.21]),
        "accumulated_call_vol": np.array([10.0, 50.0, 20.0]),
        "accumulated_put_vol": np.array([40.0, 25.0, 5.0]),
        "pricing_model": np.array(["black_76", "black_76", "black_76"]),
        "contract_multipliers": np.array([50.0, 50.0, 50.0]),
    }
    first = engine.compute_intraday_gex_matrix(**common)
    second = engine.compute_intraday_gex_matrix(**common)
    order = np.array([2, 0, 1])
    reordered = engine.compute_intraday_gex_matrix(
        spot_price=common["spot_price"],
        strikes=common["strikes"][order],
        days_to_expiry=common["days_to_expiry"][order],
        risk_free_rate=common["risk_free_rate"],
        implied_vols=common["implied_vols"][order],
        accumulated_call_vol=common["accumulated_call_vol"][order],
        accumulated_put_vol=common["accumulated_put_vol"][order],
        pricing_model=common["pricing_model"][order],
        contract_multipliers=common["contract_multipliers"][order],
    )
    doubled = engine.compute_intraday_gex_matrix(
        **{
            **common,
            "accumulated_call_vol": common["accumulated_call_vol"] * 2,
            "accumulated_put_vol": common["accumulated_put_vol"] * 2,
        }
    )
    return [
        {
            "name": "identical_input_repeat",
            "passed": first["net_gex"] == second["net_gex"],
        },
        {
            "name": "contract_row_order_invariance",
            "passed": bool(np.allclose(first["net_gex"], reordered["net_gex"], rtol=0, atol=0)),
        },
        {
            "name": "volume_linearity",
            "passed": bool(np.isclose(
                doubled["total_net_gex"],
                first["total_net_gex"] * 2,
                rtol=1e-14,
                atol=1e-8,
            )),
        },
    ]


def write_model_evidence_report(
    report: dict[str, Any], output_path: str | Path
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(model_evidence_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Model evidence output must end in .json or .md")
    return target


def model_evidence_to_markdown(report: dict[str, Any]) -> str:
    numerical = report["evidence"]["numerical_validity"]
    deterministic = report["evidence"]["deterministic_pipeline"]
    predictive = report["evidence"]["predictive_market_validity"]
    lines = [
        "# GEX Model Evidence",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Model version: `{report['model_contract']['model_version']}`",
        f"- Overall numerical gate: **{'passed' if report['result']['passed'] else 'failed'}**",
        f"- Evidence ceiling: {report['result']['evidence_ceiling']}",
        "",
        "## Numerical validity",
        "",
        f"Status: **{numerical['status']}** ({numerical['passed']}/{numerical['total']})",
        "",
        "| Case | Model | Expected | Actual | Passed |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for case in numerical["cases"]:
        expected = case.get("expected_gamma", case.get("expected_gex"))
        actual = case.get("actual_gamma", case.get("actual_gex"))
        lines.append(
            f"| {case['name']} | {case['pricing_model']} | {expected:.15g} | "
            f"{actual:.15g} | {case['passed']} |"
        )
    lines.extend([
        "",
        "## Deterministic pipeline",
        "",
        f"Status: **{deterministic['status']}**",
    ])
    lines.extend(
        f"- {check['name']}: {check['passed']}" for check in deterministic["checks"]
    )
    lines.extend([
        "",
        "## Predictive market validity",
        "",
        f"Status: **{predictive['status']}**",
        "",
        predictive["claim"],
    ])
    return "\n".join(lines) + "\n"

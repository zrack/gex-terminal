"""Model sensitivity reports for explainable GEX research."""

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from gex_terminal.engine import IntradayGexEngine
from gex_terminal.contracts import days_until_expiry


@dataclass(frozen=True)
class SensitivityScenario:
    name: str
    label: str
    multiplier_scale: float = 1.0
    days_to_expiry_scale: float = 1.0
    risk_free_rate_shift: float = 0.0
    iv_scale: float = 1.0
    volume_scale: float = 1.0


DEFAULT_SCENARIOS: tuple[SensitivityScenario, ...] = (
    SensitivityScenario("base", "Base"),
    SensitivityScenario("multiplier_half", "Multiplier 0.5x", multiplier_scale=0.5),
    SensitivityScenario("multiplier_double", "Multiplier 2.0x", multiplier_scale=2.0),
    SensitivityScenario("expiry_half", "Expiry 0.5x", days_to_expiry_scale=0.5),
    SensitivityScenario("expiry_double", "Expiry 2.0x", days_to_expiry_scale=2.0),
    SensitivityScenario("rate_down_100bp", "Rate -100bp", risk_free_rate_shift=-0.01),
    SensitivityScenario("rate_up_100bp", "Rate +100bp", risk_free_rate_shift=0.01),
    SensitivityScenario("iv_down_10pct", "IV -10%", iv_scale=0.9),
    SensitivityScenario("iv_up_10pct", "IV +10%", iv_scale=1.1),
    SensitivityScenario("volume_half", "Volume/OI 0.5x", volume_scale=0.5),
    SensitivityScenario("volume_150pct", "Volume/OI 1.5x", volume_scale=1.5),
)


def build_sensitivity_report(
    *,
    spot: float,
    chain_state: Mapping[float, Mapping[str, Any]] | None,
    days_to_expiry: float,
    risk_free_rate: float,
    contract_multiplier: int,
    scenarios: tuple[SensitivityScenario, ...] = DEFAULT_SCENARIOS,
    contract_rows: Iterable[Mapping[str, Any]] | None = None,
    base_matrix: Mapping[str, Any] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Compute shifts from either legacy strike buckets or v2 contract rows.

    Contract-aware rows preserve row-specific DTE, pricing model, carry, and
    multiplier. This prevents a Black-76 snapshot from silently receiving a
    scalar Black-Scholes sensitivity baseline.
    """
    loaded_contract_rows = [dict(row) for row in (contract_rows or ())]
    if not chain_state and not loaded_contract_rows:
        raise ValueError("Sensitivity report requires at least one option strike")

    if loaded_contract_rows:
        reference_time = as_of or datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        vectors = _contract_vectors(
            loaded_contract_rows,
            fallback_days=days_to_expiry,
            fallback_multiplier=contract_multiplier,
            as_of=reference_time,
        )
        calculation_mode = "contract_v2"
    else:
        vectors = _legacy_vectors(chain_state or {}, days_to_expiry, contract_multiplier)
        calculation_mode = "legacy_v1"

    rows = []
    base_metrics = None
    for scenario in scenarios:
        engine = IntradayGexEngine(multiplier=contract_multiplier)
        matrix = engine.compute_intraday_gex_matrix(
            spot_price=float(spot),
            strikes=vectors["strikes"],
            days_to_expiry=np.maximum(
                0.0001,
                vectors["days_to_expiry"] * scenario.days_to_expiry_scale,
            ),
            risk_free_rate=risk_free_rate + scenario.risk_free_rate_shift,
            implied_vols=np.maximum(0.0001, vectors["ivs"] * scenario.iv_scale),
            accumulated_call_vol=vectors["calls"] * scenario.volume_scale,
            accumulated_put_vol=vectors["puts"] * scenario.volume_scale,
            pricing_model=vectors["pricing_models"],
            carry_rate=vectors["carry_rates"],
            contract_multipliers=(
                vectors["multipliers"] * scenario.multiplier_scale
            ),
        )
        if scenario.name == "base" and base_matrix is not None:
            _assert_base_matrix_parity(matrix, base_matrix)
            metric_source = base_matrix
        else:
            metric_source = matrix
        metrics = {
            "scenario": scenario.name,
            "label": scenario.label,
            "total_net_gex": float(metric_source["total_net_gex"]),
            "gamma_wall": float(metric_source["gamma_wall_strike"]),
            "zero_gamma": float(metric_source["zero_gamma_strike"]),
            "call_wall": float(metric_source["call_wall_strike"]),
            "put_wall": float(metric_source["put_wall_strike"]),
        }
        if base_metrics is None:
            base_metrics = metrics
        metrics["total_net_gex_delta"] = metrics["total_net_gex"] - base_metrics["total_net_gex"]
        metrics["zero_gamma_delta"] = metrics["zero_gamma"] - base_metrics["zero_gamma"]
        metrics["gamma_wall_delta"] = metrics["gamma_wall"] - base_metrics["gamma_wall"]
        rows.append(metrics)

    return {
        "spot": float(spot),
        "inputs": {
            "days_to_expiry": float(days_to_expiry),
            "risk_free_rate": float(risk_free_rate),
            "contract_multiplier": int(contract_multiplier),
            "strike_count": len(set(vectors["strikes"].tolist())),
            "contract_count": len(vectors["strikes"]),
            "calculation_mode": calculation_mode,
            "pricing_models": sorted(set(vectors["pricing_models"].tolist())),
        },
        "scenarios": rows,
    }


def _legacy_vectors(
    chain_state: Mapping[float, Mapping[str, Any]],
    days_to_expiry: float,
    contract_multiplier: float,
) -> dict[str, np.ndarray]:
    strikes = np.array(sorted(chain_state.keys()), dtype=float)
    return {
        "strikes": strikes,
        "ivs": np.array(
            [float(chain_state[k].get("iv", 0.15)) for k in strikes], dtype=float
        ),
        "calls": np.array(
            [float(chain_state[k].get("C", 0)) for k in strikes], dtype=float
        ),
        "puts": np.array(
            [float(chain_state[k].get("P", 0)) for k in strikes], dtype=float
        ),
        "days_to_expiry": np.full(len(strikes), float(days_to_expiry), dtype=float),
        "pricing_models": np.full(len(strikes), "black_scholes", dtype=object),
        "carry_rates": np.zeros(len(strikes), dtype=float),
        "multipliers": np.full(len(strikes), float(contract_multiplier), dtype=float),
    }


def _contract_vectors(
    rows: list[dict[str, Any]],
    *,
    fallback_days: float,
    fallback_multiplier: float,
    as_of: datetime,
) -> dict[str, np.ndarray]:
    dtes = []
    calls = []
    puts = []
    for row in rows:
        explicit_dte = row.get("days_to_expiry")
        derived_dte = days_until_expiry(row.get("expiry_timestamp"), as_of)
        dte = (
            float(derived_dte)
            if derived_dte is not None
            else float(explicit_dte if explicit_dte not in (None, "") else fallback_days)
        )
        dtes.append(dte)
        volume = float(row.get("accumulated_volume", row.get("volume", 0)))
        option_type = str(row.get("option_type", "")).upper()[:1]
        if option_type not in {"C", "P"}:
            raise ValueError("contract_rows require option_type C or P")
        calls.append(volume if option_type == "C" else 0.0)
        puts.append(volume if option_type == "P" else 0.0)
    return {
        "strikes": np.array([row["strike"] for row in rows], dtype=float),
        "ivs": np.array([row.get("iv", 0.15) for row in rows], dtype=float),
        "calls": np.array(calls, dtype=float),
        "puts": np.array(puts, dtype=float),
        "days_to_expiry": np.array(dtes, dtype=float),
        "pricing_models": np.array(
            [row.get("pricing_model", "black_scholes") for row in rows],
            dtype=object,
        ),
        "carry_rates": np.array(
            [row.get("carry_rate", 0.0) for row in rows], dtype=float
        ),
        "multipliers": np.array(
            [row.get("contract_multiplier") or fallback_multiplier for row in rows],
            dtype=float,
        ),
    }


def _assert_base_matrix_parity(
    calculated: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    numeric_fields = (
        "total_net_gex",
        "gamma_wall_strike",
        "zero_gamma_strike",
        "call_wall_strike",
        "put_wall_strike",
    )
    mismatches = [
        field
        for field in numeric_fields
        if not np.isclose(
            float(calculated[field]),
            float(expected[field]),
            rtol=1e-12,
            atol=1e-8,
        )
    ]
    if mismatches:
        raise ValueError(
            "Sensitivity base scenario does not match the selected snapshot: "
            + ", ".join(mismatches)
        )


def sensitivity_to_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = (
        "scenario",
        "label",
        "total_net_gex",
        "total_net_gex_delta",
        "gamma_wall",
        "gamma_wall_delta",
        "zero_gamma",
        "zero_gamma_delta",
        "call_wall",
        "put_wall",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(report["scenarios"])
    return output.getvalue()


def sensitivity_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GEX Model Sensitivity",
        "",
        f"- Spot: `{report['spot']:,.2f}`",
        f"- Days to expiry: `{report['inputs']['days_to_expiry']:g}`",
        f"- Risk-free rate: `{report['inputs']['risk_free_rate']:.2%}`",
        f"- Contract multiplier: `{report['inputs']['contract_multiplier']}`",
        f"- Strike count: `{report['inputs']['strike_count']}`",
        "",
        "| Scenario | Net GEX | Δ Net GEX | Gamma Wall | Zero Gamma | Δ Zero |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["scenarios"]:
        lines.append(
            f"| {row['label']} | {_money(row['total_net_gex'])} | "
            f"{_money(row['total_net_gex_delta'])} | {row['gamma_wall']:,.1f} | "
            f"{row['zero_gamma']:,.1f} | {row['zero_gamma_delta']:+,.1f} |"
        )
    return "\n".join(lines) + "\n"


def write_sensitivity_report(report: dict[str, Any], output_path: str) -> Path:
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        target.write_text(sensitivity_to_csv(report), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(sensitivity_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Sensitivity report path must end in .json, .csv, or .md")
    return target


def _money(value: float) -> str:
    value = float(value)
    sign = "+" if value >= 0 else "-"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{sign}{abs_value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{sign}{abs_value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{sign}{abs_value / 1_000:.1f}K"
    return f"{sign}{abs_value:.0f}"

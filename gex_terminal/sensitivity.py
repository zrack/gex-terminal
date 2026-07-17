"""Model sensitivity reports for explainable GEX research."""

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from gex_terminal.engine import IntradayGexEngine


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
    chain_state: Mapping[float, Mapping[str, Any]],
    days_to_expiry: float,
    risk_free_rate: float,
    contract_multiplier: int,
    scenarios: tuple[SensitivityScenario, ...] = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    """Compute model-output deltas across common assumption shifts."""
    if not chain_state:
        raise ValueError("Sensitivity report requires at least one option strike")

    strikes = np.array(sorted(chain_state.keys()), dtype=float)
    ivs = np.array([float(chain_state[k].get("iv", 0.15)) for k in strikes], dtype=float)
    calls = np.array([float(chain_state[k].get("C", 0)) for k in strikes], dtype=float)
    puts = np.array([float(chain_state[k].get("P", 0)) for k in strikes], dtype=float)

    rows = []
    base_metrics = None
    for scenario in scenarios:
        engine = IntradayGexEngine(
            multiplier=max(1, round(contract_multiplier * scenario.multiplier_scale))
        )
        matrix = engine.compute_intraday_gex_matrix(
            spot_price=float(spot),
            strikes=strikes,
            days_to_expiry=max(0.0001, days_to_expiry * scenario.days_to_expiry_scale),
            risk_free_rate=risk_free_rate + scenario.risk_free_rate_shift,
            implied_vols=np.maximum(0.0001, ivs * scenario.iv_scale),
            accumulated_call_vol=calls * scenario.volume_scale,
            accumulated_put_vol=puts * scenario.volume_scale,
        )
        metrics = {
            "scenario": scenario.name,
            "label": scenario.label,
            "total_net_gex": float(matrix["total_net_gex"]),
            "gamma_wall": float(matrix["gamma_wall_strike"]),
            "zero_gamma": float(matrix["zero_gamma_strike"]),
            "call_wall": float(matrix["call_wall_strike"]),
            "put_wall": float(matrix["put_wall_strike"]),
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
            "strike_count": len(strikes),
        },
        "scenarios": rows,
    }


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

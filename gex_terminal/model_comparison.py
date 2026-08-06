"""Side-by-side comparison of default and aggressor-directionalized GEX models."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


COMPARISON_SCHEMA = "gex-terminal.model-comparison.v1"


def build_model_comparison_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Compare a snapshot's unchanged default proxy with its parallel model."""
    directional = snapshot.get("directionalized")
    if not isinstance(directional, Mapping):
        directional = {
            "model": "aggressor_directionalized_volume",
            "status": "not_computed",
            "directional_coverage": 0.0,
            "known_direction_volume": 0.0,
            "unknown_direction_volume": 0.0,
            "predictive_validity": "unmeasured",
        }

    raw_rows = {
        float(row["strike"]): float(row["net_gex"])
        for row in snapshot.get("strikes", ())
    }
    directional_rows = {
        float(strike): float(value)
        for strike, value in zip(
            directional.get("strikes", ()),
            directional.get("net_gex", ()),
        )
    }
    buy_rows = _strike_values(directional, "buy_aggressor_volume")
    sell_rows = _strike_values(directional, "sell_aggressor_volume")
    unknown_rows = _strike_values(directional, "unknown_aggressor_volume")
    common_strikes = sorted(set(raw_rows) & set(directional_rows))
    comparison_rows = [
        {
            "strike": strike,
            "raw_net_gex": raw_rows[strike],
            "directionalized_net_gex": directional_rows[strike],
            "net_gex_delta": directional_rows[strike] - raw_rows[strike],
            "buy_aggressor_volume": buy_rows.get(strike, 0.0),
            "sell_aggressor_volume": sell_rows.get(strike, 0.0),
            "unknown_aggressor_volume": unknown_rows.get(strike, 0.0),
        }
        for strike in common_strikes
    ]

    status = str(directional.get("status") or "not_computed")
    comparison_status = (
        "no_comparable_strikes"
        if status == "available" and not common_strikes
        else status
    )
    metrics: dict[str, Any] = {
        "comparable_strike_count": len(common_strikes),
        "directional_coverage": float(directional.get("directional_coverage", 0.0)),
        "known_direction_volume": float(directional.get("known_direction_volume", 0.0)),
        "unknown_direction_volume": float(directional.get("unknown_direction_volume", 0.0)),
    }
    if comparison_status == "available":
        raw = np.array([raw_rows[strike] for strike in common_strikes], dtype=float)
        alternative = np.array(
            [directional_rows[strike] for strike in common_strikes], dtype=float
        )
        both_nonzero = (np.sign(raw) != 0) & (np.sign(alternative) != 0)
        comparable_signs = int(np.sum(both_nonzero))
        metrics.update({
            "raw_total_net_gex": float(snapshot["metrics"]["total_net_gex"]),
            "directionalized_total_net_gex": float(directional["total_net_gex"]),
            "total_net_gex_delta": (
                float(directional["total_net_gex"])
                - float(snapshot["metrics"]["total_net_gex"])
            ),
            "raw_regime_sign": _sign_label(snapshot["metrics"]["total_net_gex"]),
            "directionalized_regime_sign": _sign_label(directional["total_net_gex"]),
            "regime_sign_agreement": (
                _sign_label(snapshot["metrics"]["total_net_gex"])
                == _sign_label(directional["total_net_gex"])
            ),
            "gamma_wall_distance": abs(
                float(snapshot["metrics"]["gamma_wall"])
                - float(directional["gamma_wall_strike"])
            ),
            "zero_gamma_distance": abs(
                float(snapshot["metrics"]["zero_gamma"])
                - float(directional["zero_gamma_strike"])
            ),
            "sign_comparable_strike_count": comparable_signs,
            "strike_sign_agreement": (
                float(np.mean(np.sign(raw[both_nonzero]) == np.sign(alternative[both_nonzero])))
                if comparable_signs
                else None
            ),
            "strike_rank_correlation": _rank_correlation(raw, alternative),
            "normalized_profile_l1_distance": _profile_distance(raw, alternative),
        })

    return {
        "schema": COMPARISON_SCHEMA,
        "timestamp": snapshot.get("timestamp"),
        "symbol": snapshot.get("symbol"),
        "spot": float(snapshot.get("spot", 0.0)),
        "default_model": {
            "name": "call_positive_put_negative",
            "position_sources": list(
                snapshot.get("model", {}).get("position_sources", ())
            ),
            "unchanged_default": True,
        },
        "alternate_model": {
            "name": directional.get("model", "aggressor_directionalized_volume"),
            "model_version": directional.get(
                "model_version", "gex-terminal.aggressor-directionalized.v1"
            ),
            "status": comparison_status,
            "direction_sources": list(directional.get("direction_sources", ())),
            "assumption": directional.get("directional_assumption"),
            "participant_classification": directional.get(
                "participant_classification", "unobserved"
            ),
            "opening_closing_classification": directional.get(
                "opening_closing_classification", "unobserved"
            ),
        },
        "metrics": metrics,
        "strikes": comparison_rows,
        "result": {
            "status": comparison_status,
            "predictive_validity": "unmeasured",
            "interpretation": (
                "model_disagreement_only; not evidence of forecasting value"
            ),
        },
    }


def model_comparison_to_csv(report: Mapping[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = (
        "record_type",
        "name",
        "value",
        "strike",
        "raw_net_gex",
        "directionalized_net_gex",
        "net_gex_delta",
        "buy_aggressor_volume",
        "sell_aggressor_volume",
        "unknown_aggressor_volume",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for name, value in report["metrics"].items():
        writer.writerow({"record_type": "metric", "name": name, "value": value})
    for row in report["strikes"]:
        writer.writerow({"record_type": "strike", **row})
    return output.getvalue()


def model_comparison_to_markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    alternate = report["alternate_model"]
    lines = [
        "# GEX Model Comparison",
        "",
        f"- Symbol: `{report.get('symbol', '--')}`",
        f"- Timestamp: `{report.get('timestamp', '--')}`",
        f"- Default model: `{report['default_model']['name']}` (unchanged)",
        f"- Alternate model: `{alternate['name']}`",
        f"- Alternate status: `{alternate['status']}`",
        f"- Direction coverage: `{float(metrics['directional_coverage']):.1%}`",
        f"- Participant classification: `{alternate['participant_classification']}`",
        "- Predictive validity: `unmeasured`",
    ]
    if alternate["status"] == "available":
        lines.extend([
            "",
            "## Comparison",
            "",
            f"- Raw net GEX: `{_money(metrics['raw_total_net_gex'])}`",
            f"- Directionalized net GEX: `{_money(metrics['directionalized_total_net_gex'])}`",
            f"- Regime-sign agreement: `{metrics['regime_sign_agreement']}`",
            f"- Gamma-wall distance: `{metrics['gamma_wall_distance']:,.1f}`",
            f"- Zero-gamma distance: `{metrics['zero_gamma_distance']:,.1f}`",
            f"- Strike-sign agreement: `{_optional_percent(metrics['strike_sign_agreement'])}`",
            f"- Strike-rank correlation: `{_optional_number(metrics['strike_rank_correlation'])}`",
            f"- Normalized-profile L1 distance: `{metrics['normalized_profile_l1_distance']:.4f}`",
            "",
            "## Strike Comparison",
            "",
            "| Strike | Raw Net GEX | Directionalized Net GEX | Delta | Buy Agg. | Sell Agg. | Unknown |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for row in report["strikes"]:
            lines.append(
                f"| {row['strike']:,.1f} | {_money(row['raw_net_gex'])} | "
                f"{_money(row['directionalized_net_gex'])} | {_money(row['net_gex_delta'])} | "
                f"{row['buy_aggressor_volume']:,.0f} | {row['sell_aggressor_volume']:,.0f} | "
                f"{row['unknown_aggressor_volume']:,.0f} |"
            )
    else:
        lines.extend([
            "",
            "The comparison is intentionally unscored because no usable trade-side "
            "coverage was present. The default model remains available and unchanged.",
        ])
    return "\n".join(lines) + "\n"


def write_model_comparison_report(
    report: Mapping[str, Any], output_path: str
) -> Path:
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix in {"", ".json"}:
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        target.write_text(model_comparison_to_csv(report), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(model_comparison_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Model comparison path must end in .json, .csv, or .md")
    return target


def _strike_values(model: Mapping[str, Any], field: str) -> dict[float, float]:
    return {
        float(strike): float(value)
        for strike, value in zip(model.get("strikes", ()), model.get(field, ()))
    }


def _rank_correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2:
        return None
    left_rank = _average_ranks(left)
    right_rank = _average_ranks(right)
    if np.std(left_rank) == 0 or np.std(right_rank) == 0:
        return None
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def _profile_distance(left: np.ndarray, right: np.ndarray) -> float:
    left_scale = float(np.sum(np.abs(left)))
    right_scale = float(np.sum(np.abs(right)))
    left_profile = left / left_scale if left_scale else np.zeros_like(left)
    right_profile = right / right_scale if right_scale else np.zeros_like(right)
    return float(np.sum(np.abs(left_profile - right_profile)))


def _sign_label(value: Any) -> str:
    numeric = float(value)
    if numeric > 0:
        return "positive"
    if numeric < 0:
        return "negative"
    return "neutral"


def _optional_percent(value: Any) -> str:
    return "--" if value is None else f"{float(value):.1%}"


def _optional_number(value: Any) -> str:
    return "--" if value is None else f"{float(value):.4f}"


def _money(value: Any) -> str:
    numeric = float(value)
    sign = "+" if numeric >= 0 else "-"
    absolute = abs(numeric)
    if absolute >= 1_000_000_000:
        return f"{sign}{absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}{absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}{absolute / 1_000:.1f}K"
    return f"{sign}{absolute:.0f}"

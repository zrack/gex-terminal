"""Visible qualifications for the existing European-exercise pricing formulas.

These fields describe assumptions; they neither change pricing nor certify that
an observed premium is economically explained by the model.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Iterable, Mapping


def build_pricing_assumptions(rows: Iterable[Mapping[str, Any]], risk_free_rate: float) -> dict:
    """Return JSON-safe model, exercise-style and configured-rate provenance."""
    rows = list(rows)
    models = sorted({str(row.get("pricing_model") or "black_scholes") for row in rows})
    if not models:
        models = ["black_scholes"]
    labels = {"black_76": "Black-76", "black_scholes": "Black-Scholes"}
    styles = Counter(row.get("exercise_style") if row.get("exercise_style") in {"american", "european"}
                     else "unknown" for row in rows)
    counts = {style: styles.get(style, 0) for style in ("american", "european", "unknown")}
    limitations = ["European-exercise formulas; early exercise is not modeled."]
    if counts["american"]:
        status = "approximation_unmeasured"
        qualification = "American exercise: approximation error unmeasured"
        limitations.append("American-style contracts use a European-exercise approximation; its error is unmeasured.")
    elif counts["unknown"] or not rows:
        status = "exercise_style_unknown"
        qualification = "exercise style unknown: model compatibility unqualified"
    else:
        status = "european_exercise_confirmed"
        qualification = "European exercise confirmed"
    if counts["unknown"] or not rows:
        limitations.append("Exercise style is missing for some contracts; compatibility with the pricing model is unqualified.")
    inversion_rates = set()
    for row in rows:
        provenance = row.get("iv_provenance")
        supplied = provenance.get("risk_free_rate") if isinstance(provenance, dict) else row.get("iv_inversion_risk_free_rate")
        try:
            supplied_rate = float(supplied)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(supplied_rate):
            inversion_rates.add(supplied_rate)
    inversion_rates = sorted(inversion_rates)
    rate = float(risk_free_rate)
    rate_note = f"Risk-free rate {rate:.2%} is configured, not observed market data; continuously compounded, flat across maturities."
    if any(value != rate for value in inversion_rates):
        limitations.append("Some captured IVs were inverted using a different configured rate; changing the current rate does not reinvert captured IVs.")
    return {
        "models": models, "model_labels": [labels.get(model, model) for model in models],
        "exercise_style_counts": counts, "status": status,
        "summary": f"{' / '.join(labels.get(model, model) for model in models)}: {qualification}.",
        "limitations": limitations,
        "risk_free_rate": rate, "risk_free_rate_source": "configured",
        "iv_inversion_risk_free_rates": inversion_rates, "rate_note": rate_note,
        "day_count": "ACT/365", "time_note": "Exact expiry timestamps use actual seconds / 365 days; otherwise contract DTE or configured fallback is used.",
        "early_exercise_modeled": False, "approximation_error": "unmeasured",
    }

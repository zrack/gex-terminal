"""Visible pricing qualifications and explicit unavailable-exposure coverage.

These fields describe assumptions; they neither change pricing nor certify that
an observed premium is economically explained by the model.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any, Iterable, Mapping


AMERICAN_FUTURES_MODEL = "american_futures_crr"
QUALIFIED_IV_SOURCES = {"american_futures_inverted", "prior_valid", "unavailable"}
IV_PROVENANCE_FIELDS = {
    "method", "status", "option_price", "option_price_source", "underlying_price",
    "underlying_price_source", "underlying_price_age_ms", "maximum_underlying_age_ms",
    "risk_free_rate", "time_to_expiry_years", "iterations", "absolute_price_error",
    "numerical_method", "tree_steps", "tree_pair_steps", "error_scope",
    "empirical_pricing_accuracy", "prior_iv_event_time", "prior_iv_source",
    "prior_iv_age_ms", "prior_iv", "failed_inversion_status",
    "lower_bound", "upper_bound", "maximum_prior_iv_age_ms", "prior_iv_pricing_model",
    "prior_iv_risk_free_rate",
    "underlying_event_time", "underlying_instrument_id",
    "futures_risk_neutral_drift", "early_exercise_modeled", "gamma_method",
}


def has_qualified_pricing(rows: Iterable[Mapping[str, Any]]) -> bool:
    """Identify new explicit pricing policy without changing legacy artifacts."""
    return any(row.get("pricing_model") == AMERICAN_FUTURES_MODEL
               or row.get("iv_source") in QUALIFIED_IV_SOURCES for row in rows)


def is_priced_contract(row: Mapping[str, Any]) -> bool:
    """An unavailable observation never receives a manufactured volatility."""
    if row.get("iv_source") == "unavailable":
        return False
    try:
        value = float(row.get("iv", .15))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(value) and value > 0


def pricing_coverage(rows: Iterable[Mapping[str, Any]]) -> dict:
    """Partition current selected quantities; these are not trade-event counts."""
    rows = list(rows)
    priced = [row for row in rows if is_priced_contract(row)]
    unpriced = [row for row in rows if not is_priced_contract(row)]
    retained = [row for row in priced if row.get("iv_source") == "prior_valid"]
    def quantity(items):
        return sum(int(row.get("accumulated_volume", row.get("volume", 0))) for row in items)
    reasons = Counter()
    for row in unpriced:
        provenance = row.get("iv_provenance")
        reason = provenance.get("status") if isinstance(provenance, dict) else None
        reasons[str(reason or "iv_unavailable")] += 1
    return {
        "status": "complete" if not unpriced else "partial" if priced else "unavailable",
        "selected_contract_count": len(rows), "selected_quantity": quantity(rows),
        "priced_contract_count": len(priced), "priced_quantity": quantity(priced),
        "unpriced_contract_count": len(unpriced), "unpriced_quantity": quantity(unpriced),
        "retained_iv_contract_count": len(retained), "retained_iv_quantity": quantity(retained),
        "unpriced_reasons": dict(sorted(reasons.items())),
        "quantity_semantics": "current selected contract quantities at their latest captured IV",
    }


def build_pricing_assumptions(rows: Iterable[Mapping[str, Any]], risk_free_rate: float) -> dict:
    """Return JSON-safe model, exercise-style and configured-rate provenance."""
    rows = list(rows)
    models = sorted({str(row.get("pricing_model") or "black_scholes") for row in rows})
    if not models:
        models = ["black_scholes"]
    labels = {"black_76": "Black-76", "black_scholes": "Black-Scholes",
              AMERICAN_FUTURES_MODEL: "American futures CRR"}
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
        if isinstance(provenance, dict):
            supplied = provenance.get("prior_iv_risk_free_rate") if row.get("iv_source") == "prior_valid" else provenance.get("risk_free_rate")
        else:
            supplied = row.get("iv_inversion_risk_free_rate")
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
    result = {
        "models": models, "model_labels": [labels.get(model, model) for model in models],
        "exercise_style_counts": counts, "status": status,
        "summary": f"{' / '.join(labels.get(model, model) for model in models)}: {qualification}.",
        "limitations": limitations,
        "risk_free_rate": rate, "risk_free_rate_source": "configured",
        "iv_inversion_risk_free_rates": inversion_rates, "rate_note": rate_note,
        "day_count": "ACT/365", "time_note": "Exact expiry timestamps use actual seconds / 365 days; otherwise contract DTE or configured fallback is used.",
        "early_exercise_modeled": False, "approximation_error": "unmeasured",
    }
    american_rows = [row for row in rows if row.get("pricing_model") == AMERICAN_FUTURES_MODEL]
    if american_rows:
        approximated = any(row.get("exercise_style") == "american"
                           and row.get("pricing_model") != AMERICAN_FUTURES_MODEL for row in rows)
        result["early_exercise_modeled"] = True
        result["all_american_exercise_modeled"] = not approximated
        result["status"] = ("approximation_unmeasured" if approximated else
                            "exercise_style_unknown" if counts["unknown"] else "american_exercise_modeled")
        result["summary"] = (f"{' / '.join(labels.get(model, model) for model in models)}: "
                             "American futures early exercise is modeled with a finite CRR lattice."
                             + (" Some American rows retain a European approximation." if approximated else ""))
        result["limitations"] = [
            "American futures values and gamma use a finite exercise lattice; numerical discretization remains.",
            "Futures are modeled as lognormal martingales with a configured flat discount rate; empirical pricing accuracy is unmeasured.",
        ] + [item for item in limitations if item != "European-exercise formulas; early exercise is not modeled."
             and (approximated or item != "American-style contracts use a European-exercise approximation; its error is unmeasured.")]
        if any(row.get("pricing_model") != AMERICAN_FUTURES_MODEL for row in rows):
            result["limitations"].append("Black-76 and Black-Scholes rows retain European-exercise formulas.")
        result["approximation_error"] = "unmeasured" if approximated else "numerical_discretization"
        result["numerical_method"] = "crr_even_odd_european_control_variate"
        result["tree_pair_steps"] = [512, 513]
        result["empirical_pricing_accuracy"] = "unmeasured"
    if has_qualified_pricing(rows):
        result["pricing_coverage"] = pricing_coverage(rows)
        if any(row.get("iv_source") == "prior_valid" for row in rows):
            result["limitations"].append("Some current IV observations are unresolved; a labeled earlier valid IV for the same contract is retained without using later observations.")
        if any(not is_priced_contract(row) for row in rows):
            result["limitations"].append("Unresolved IV remains unavailable: its raw quantity is retained but excluded from modeled GEX.")
    return result

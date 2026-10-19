"""Plain-language pricing coverage for the UI, without changing calculation artifacts.

Prices and quote ages below describe the captured inversion attempt. They are
never recomputed from a later checkpoint or a shifted research scenario.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from gex_terminal.pricing_assumptions import is_priced_contract, pricing_coverage


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _points(value: float) -> str:
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _label(value: Any) -> str:
    return " ".join(str(value).split())


def _percentage(priced: float, selected: float) -> str:
    if selected <= 0:
        return "n/a"
    result = f"{100 * priced / selected:.2f}%"
    # A rounded percentage must not turn a known coverage gap into completeness.
    return "<100%" if priced < selected and result == "100.00%" else result


def _reason(status: str) -> str:
    return {
        "outside_no_arbitrage_bounds": "The captured premium is outside the model's valid pricing bounds; no valid IV fits those inputs.",
        "missing_inversion_input": "The captured observation is missing an input required to calculate IV.",
        "missing_option_price": "No option premium is available for the captured IV calculation.",
        "missing_underlying_price": "No eligible futures price is available for the captured IV calculation.",
        "stale_underlying_price": "The captured futures quote is too old for the IV calculation.",
        "invalid_option_price": "The captured option premium is not valid for the IV calculation.",
        "at_intrinsic_boundary": "The captured premium is at the model's intrinsic boundary; no positive IV is established.",
        "below_solver_range": "The captured premium is below the supported IV solver range.",
        "above_solver_range": "The captured premium is above the supported IV solver range.",
        "iteration_limit": "The captured IV calculation did not converge within its iteration limit.",
        "max_iterations": "The captured IV calculation did not converge within its iteration limit.",
        "non_convergence": "The captured IV calculation did not converge.",
    }.get(status, "No valid IV is available for this captured observation.")


def _contract_detail(row: Mapping[str, Any]) -> str:
    provenance = row.get("iv_provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    status = str(provenance.get("failed_inversion_status") or provenance.get("status") or "iv_unavailable")
    identity = []
    if row.get("contract_symbol"):
        identity.append(_label(row["contract_symbol"]))
    elif row.get("symbol"):
        identity.append(_label(row["symbol"]))
    strike = _number(row.get("strike"))
    kind = {"C": "call", "P": "put"}.get(row.get("option_type"))
    if strike is not None:
        identity.append(f"{kind or 'strike'} {_points(strike)}")
    if row.get("expiry"):
        identity.append(f"expiry {_label(row['expiry'])}")
    if row.get("contract_id") is not None:
        identity.append(f"contract {_label(row['contract_id'])}")
    quantity = _number(row.get("accumulated_volume", row.get("quantity", row.get("volume"))))
    if quantity is not None:
        identity.append(f"quantity {quantity:,.0f}")
    price, lower, upper = (_number(provenance.get(key)) for key in ("option_price", "lower_bound", "upper_bound"))
    reason = _reason(status)
    if status == "outside_no_arbitrage_bounds" and price is not None:
        if lower is not None and price < lower:
            reason = (f"Captured premium {_points(price)} points is below the model minimum "
                      f"{_points(lower)} points (gap {_points(lower - price)} points). "
                      "No valid IV fits those captured inputs.")
        elif upper is not None and price > upper:
            reason = (f"Captured premium {_points(price)} points is above the model maximum "
                      f"{_points(upper)} points (gap {_points(price - upper)} points). "
                      "No valid IV fits those captured inputs.")
    inputs = []
    future = _number(provenance.get("underlying_price"))
    age = _number(provenance.get("underlying_price_age_ms"))
    if future is not None:
        inputs.append(f"underlying {_points(future)}")
    if age is not None and age >= 0:
        inputs.append(f"quote age {age / 1000:,.3f} seconds")
    if inputs:
        reason += " Captured " + "; ".join(inputs) + "."
    return (" · ".join(identity) or "Unpriced contract") + ": " + reason


def build_pricing_display(coverage: Mapping[str, Any] | None,
                          rows: Iterable[Mapping[str, Any]] = ()) -> dict:
    """Build presentation text; preserve all source rows and coverage values.

    All-priced v2 inputs may omit qualified-pricing metadata, so their active
    contract rows can supply display-only coverage. Legacy aggregate data has
    no contract denominator and must remain explicitly unreported.
    """
    rows = list(rows)
    if coverage is None and rows:
        coverage = pricing_coverage(rows)
    required = ("selected_contract_count", "priced_contract_count", "selected_quantity", "priced_quantity")
    values = [_number(coverage.get(key)) if isinstance(coverage, Mapping) else None for key in required]
    if any(value is None or value < 0 for value in values):
        return {"status": "unreported", "summary": "Pricing coverage: Not reported for this source.",
                "reason_summary": "Contract coverage requires selected contract records.", "details": []}
    selected, priced, quantity, priced_quantity = values
    if priced > selected or priced_quantity > quantity:
        return {"status": "unreported", "summary": "Pricing coverage: Not reported for this source.",
                "reason_summary": "Pricing coverage counts are inconsistent.", "details": []}
    status = ("empty" if selected == 0 else "unavailable" if priced == 0 else
              "partial" if priced < selected or priced_quantity < quantity else "complete")
    label = {"empty": "No selected contracts", "complete": "Complete", "partial": "Partial", "unavailable": "All unpriced"}[status]
    summary = (f"Pricing coverage: {label} · contracts {priced:,.0f}/{selected:,.0f} "
               f"({_percentage(priced, selected)}) · selected quantity {priced_quantity:,.0f}/{quantity:,.0f} "
               f"({_percentage(priced_quantity, quantity)})")
    retained = _number(coverage.get("retained_iv_contract_count")) or 0
    if retained:
        summary += f" · {retained:,.0f} contract(s) use an earlier valid IV"
    reason_summary = ""
    if status in {"partial", "unavailable"}:
        reasons = coverage.get("unpriced_reasons")
        reasons = reasons if isinstance(reasons, Mapping) else {}
        descriptions = list(dict.fromkeys(_reason(str(key)) for key in sorted(reasons)))
        reason_summary = " ".join(descriptions or [_reason("iv_unavailable")])
        reason_summary += " Raw quantities are retained; their exposure is excluded from modeled GEX."
    return {"status": status, "summary": summary, "reason_summary": reason_summary,
            "details": [_contract_detail(row) for row in rows
                        if row.get("reason") == "iv_unavailable" or not is_priced_contract(row)]}

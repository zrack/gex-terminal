"""Accepted-IV observation ages for an already selected, active contract cohort.

This is a disclosure, not a pricing filter. A 300-second reference window does
not expire unchanged accepted IV, change the failed-inversion retention policy,
or establish that observations form a synchronized option chain.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Iterable, Mapping

from gex_terminal.contracts import market_timestamp_order_key
from gex_terminal.pricing_assumptions import is_priced_contract


REFERENCE_WINDOW_SECONDS = 300
OBSERVED_IV_SOURCES = {"provider", "black_76_inverted", "american_futures_inverted"}
_NOT_OBSERVED_SOURCES = {"configured_default", "legacy_unspecified"}


def _time(value: Any) -> tuple | None:
    return market_timestamp_order_key(value)


def _text(value: tuple | None) -> str | None:
    return value[0].isoformat().replace("+00:00", "Z") if value else None


def _seconds(later: tuple, earlier: tuple) -> float:
    # Keep the nanosecond remainder for future-observation qualification and the
    # reference-window boundary; datetime itself retains only microseconds.
    return (later[0] - earlier[0]).total_seconds() + (later[1] - earlier[1]) / 1e9


def _quantity(row: Mapping[str, Any]) -> int:
    return int(row.get("accumulated_volume", row.get("volume", 0)))


def iv_freshness(rows: Iterable[Mapping[str, Any]], as_of: Any, *, capture_as_of: Any = None) -> dict:
    """Describe accepted-IV ages at a frozen capture or scenario model time.

    Callers select the active expiry and quantity-source cohort first. Provider
    or converged-IV event times identify accepted observations. A retained IV
    uses its original provenance time, never the failed current tick's time.
    Missing, naive, unqualified or future observation times remain unknown.
    No wall clock, pricing, IV replacement or cohort mutation is involved.
    """
    rows = list(rows)
    reference = _time(as_of)
    capture = _time(as_of if capture_as_of is None else capture_as_of)
    valid_reference = reference is not None and capture is not None and reference >= capture
    advance = _seconds(reference, capture) if valid_reference else None
    result = {
        "status": "empty", "as_of": _text(reference), "capture_as_of": _text(capture),
        "time_basis": ("scenario_model_time" if advance else "captured_cutoff") if valid_reference else "unknown",
        "model_time_advance_seconds": advance,
        "reference_window_seconds": REFERENCE_WINDOW_SECONDS,
        "reference_window_note": "300 seconds is an age reference window, not an IV validity or expiry rule. No new observations are made when scenario time advances.",
        "age_semantics": "Accepted-IV observation age for the active selected cohort; counts and quantities are separate from pricing coverage. An observation later within the stored capture cutoff's final microsecond has unknown age because the capture cutoff may have truncated nanoseconds; it is not classified as a confirmed future observation.",
        "max_age_seconds": None, "median_age_seconds": None, "max_retained_age_seconds": None,
    }
    for prefix in ("selected", "priced", "known_age", "recent", "older", "unknown",
                   "not_applicable", "unpriced", "retained_iv", "future_observation",
                   "capture_precision_ambiguity"):
        result[f"{prefix}_contract_count"] = 0
        result[f"{prefix}_quantity"] = 0
    ages, retained_ages = [], []

    def count(prefix: str, quantity: int) -> None:
        result[f"{prefix}_contract_count"] += 1
        result[f"{prefix}_quantity"] += quantity

    for row in rows:
        quantity = _quantity(row)
        count("selected", quantity)
        if not is_priced_contract(row):
            count("unpriced", quantity)
            continue
        count("priced", quantity)
        source = row.get("iv_source")
        if source == "prior_valid":
            count("retained_iv", quantity)
            provenance = row.get("iv_provenance")
            provenance = provenance if isinstance(provenance, Mapping) else {}
            observed = (_time(provenance.get("prior_iv_event_time"))
                        if provenance.get("prior_iv_source") in OBSERVED_IV_SOURCES else None)
        elif source in OBSERVED_IV_SOURCES:
            observed = _time(row.get("event_time"))
        elif source in _NOT_OBSERVED_SOURCES:
            count("not_applicable", quantity)
            continue
        else:
            observed = None
        if not valid_reference or observed is None:
            count("unknown", quantity)
            continue
        if observed > capture or observed > reference:
            count("unknown", quantity)
            # The checkpoint stores its cutoff as datetime microseconds, while
            # provider rows can retain nanoseconds. A positive remainder within
            # that final microsecond cannot prove a post-capture observation.
            # Keep the age unknown rather than round it to a fabricated zero.
            if capture[1] == 0 and observed[0] == capture[0]:
                count("capture_precision_ambiguity", quantity)
            else:
                count("future_observation", quantity)
            continue
        age = _seconds(reference, observed)
        ages.append(age)
        if source == "prior_valid":
            retained_ages.append(age)
        count("known_age", quantity)
        count("recent" if age <= REFERENCE_WINDOW_SECONDS else "older", quantity)
    if ages:
        result["max_age_seconds"] = max(ages)
        result["median_age_seconds"] = median(ages)
        result["status"] = "partial" if result["unknown_contract_count"] or result["not_applicable_contract_count"] else "measured"
    elif result["unknown_contract_count"]:
        result["status"] = "unknown"
    elif result["not_applicable_contract_count"]:
        result["status"] = "not_applicable"
    elif rows:
        result["status"] = "unavailable"
    if retained_ages:
        result["max_retained_age_seconds"] = max(retained_ages)
    return result

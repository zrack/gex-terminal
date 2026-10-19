"""Preserve unavailable numeric metrics across reports and exports."""

from typing import Any, Mapping


def optional_float(value: Any) -> float | None:
    """Convert an observed metric without replacing missing evidence with zero."""
    return None if value is None else float(value)


def metric_delta(
    before: Mapping[str, Any], after: Mapping[str, Any], field: str
) -> float | None:
    """A change is unavailable when either observation is unavailable."""
    previous = optional_float(before.get(field, 0.0))
    current = optional_float(after.get(field, 0.0))
    return None if previous is None or current is None else current - previous

"""Evidence-bounded evaluation of saved GEX levels against later price paths."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence


PRICE_ACTION_SCHEMA = "gex-terminal.price-action-validation.v1"


def build_price_action_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Score precomputed levels against strictly later saved prices."""
    observations = payload.get("observations")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("price-action input requires an observations array")
    minimum_coverage = _finite_float(
        payload.get("minimum_directional_coverage", 0.5),
        "minimum_directional_coverage",
    )
    if not 0 <= minimum_coverage <= 1:
        raise ValueError("minimum_directional_coverage must be between 0 and 1")
    rows = [
        _evaluate_observation(item, minimum_directional_coverage=minimum_coverage)
        for item in observations
    ]
    rows.sort(key=lambda row: row["timestamp"])
    split_labels = _chronological_splits(len(rows))
    for row, split in zip(rows, split_labels):
        row["split"] = split

    scored = [row for row in rows if row["status"] == "scored"]
    models = sorted({name for row in scored for name in row["models"]})
    summaries = {}
    for model in models:
        model_rows = [row["models"][model] for row in scored if model in row["models"]]
        summaries[model] = {
            "observations": len(model_rows),
            "mean_nearest_level_distance_pct": _optional_mean(
                row["nearest_level_distance_pct"] for row in model_rows
            ),
            "touch_rate": _optional_mean(float(row["any_level_touched"]) for row in model_rows),
            "cross_rate": _optional_mean(float(row["any_level_crossed"]) for row in model_rows),
        }
    coverage = [
        _finite_float(item.get("directional_coverage"), "directional_coverage")
        for item in observations
        if isinstance(item, Mapping) and item.get("directional_coverage") is not None
    ]
    return {
        "schema": PRICE_ACTION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": {
            "label": payload.get("label"),
            "source_kind": payload.get("source_kind", "unspecified"),
            "observations": len(rows),
            "scored_observations": len(scored),
            "chronological_split": {"train": 0.6, "calibration": 0.2, "test": 0.2},
        },
        "directional_coverage": {
            "mean": _optional_mean(coverage),
            "minimum_required": minimum_coverage,
        },
        "model_summaries": summaries,
        "observations": rows,
        "result": {
            "status": "descriptive_only" if scored else "insufficient_saved_price_action",
            "predictive_validity": "unmeasured",
            "promotion_allowed": False,
        },
        "evidence_ceiling": (
            "descriptive saved-price behavior only; no tuning on the test split, "
            "transaction-cost result, dealer-inventory label, or live profitability claim"
        ),
    }


def load_price_action_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("price-action input must be a JSON object")
    return build_price_action_report(payload)


def write_price_action_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("Price-action validation output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _evaluate_observation(
    item: Any, *, minimum_directional_coverage: float
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("each price-action observation must be an object")
    timestamp = str(item.get("timestamp") or "")
    _timezone_datetime(timestamp, "observation timestamp")
    spot = _positive_float(item.get("spot"), "spot")
    path = item.get("future_path")
    if not isinstance(path, Sequence) or isinstance(path, (str, bytes)) or not path:
        return {"timestamp": timestamp, "spot": spot, "status": "missing_future_path", "models": {}}
    path_rows = []
    for point in path:
        if not isinstance(point, Mapping):
            continue
        minutes = _finite_float(point.get("minutes"), "future_path minutes")
        if minutes <= 0:
            raise ValueError("future_path minutes must be finite and strictly positive")
        path_rows.append((minutes, _positive_float(point.get("price"), "future price")))
    path_rows.sort()
    prices = [price for _, price in path_rows]
    if not prices:
        return {"timestamp": timestamp, "spot": spot, "status": "missing_future_path", "models": {}}
    model_levels = item.get("models")
    if not isinstance(model_levels, Mapping):
        raise ValueError("each observation requires a models object")
    tolerance_pct = _finite_float(item.get("touch_tolerance_pct", 0.001), "touch_tolerance_pct")
    if tolerance_pct < 0:
        raise ValueError("touch_tolerance_pct must be nonnegative")
    results = {}
    unscored_models = {}
    directional_coverage = item.get("directional_coverage")
    if directional_coverage is not None:
        directional_coverage = _finite_float(directional_coverage, "directional_coverage")
        if not 0 <= directional_coverage <= 1:
            raise ValueError("directional_coverage must be between 0 and 1")
    for model, raw_levels in model_levels.items():
        if not isinstance(raw_levels, Mapping):
            continue
        levels = {
            str(name): float(value)
            for name, value in raw_levels.items()
            if value is not None and math.isfinite(float(value)) and float(value) > 0
        }
        if not levels:
            continue
        if "directional" in str(model).lower() and (
            directional_coverage is None
            or directional_coverage < minimum_directional_coverage
        ):
            unscored_models[str(model)] = "insufficient_directional_coverage"
            continue
        nearest_name, nearest_level = min(levels.items(), key=lambda pair: abs(pair[1] - spot))
        touched = {
            name: any(abs(price - level) / level <= tolerance_pct for price in prices)
            for name, level in levels.items()
        }
        crossed = {
            name: any((spot - level) * (price - level) <= 0 for price in prices)
            for name, level in levels.items()
        }
        results[str(model)] = {
            "nearest_level": nearest_name,
            "nearest_level_distance_pct": abs(nearest_level - spot) / spot,
            "any_level_touched": any(touched.values()),
            "any_level_crossed": any(crossed.values()),
            "level_touches": touched,
            "level_crosses": crossed,
            "terminal_return": prices[-1] / spot - 1.0,
            "maximum_favorable_move": max(prices) / spot - 1.0,
            "maximum_adverse_move": min(prices) / spot - 1.0,
        }
    return {
        "timestamp": timestamp,
        "spot": spot,
        "status": "scored" if results else "missing_levels",
        "directional_coverage": directional_coverage,
        "models": results,
        "unscored_models": unscored_models,
    }


def _chronological_splits(count: int) -> list[str]:
    labels = []
    for index in range(count):
        fraction = (index + 1) / max(count, 1)
        labels.append("train" if fraction <= 0.6 else "calibration" if fraction <= 0.8 else "test")
    return labels


def _positive_float(value: Any, label: str) -> float:
    number = _finite_float(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _finite_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _optional_mean(values) -> float | None:
    collected = list(values)
    return mean(collected) if collected else None


def _timezone_datetime(value: str, label: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed

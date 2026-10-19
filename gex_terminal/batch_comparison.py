"""Batch point-in-time comparison across sessions, days, expiries, and DTE layers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from gex_terminal.model_profiles import (
    config_from_model_profile,
    validate_model_profile,
)
from gex_terminal.position_model_comparison import load_position_model_comparison


BATCH_SPEC_SCHEMA = "gex-terminal.batch-position-comparison-spec.v1"
BATCH_REPORT_SCHEMA = "gex-terminal.batch-position-comparison.v1"


async def build_batch_comparison(spec_path: str | Path) -> dict[str, Any]:
    source = Path(spec_path).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema") != BATCH_SPEC_SCHEMA:
        raise ValueError(f"batch comparison schema must be {BATCH_SPEC_SCHEMA}")
    batch_id = str(payload.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("batch comparison requires batch_id")
    raw_profile = payload.get("model_profile")
    if not isinstance(raw_profile, Mapping):
        raise ValueError("batch comparison requires model_profile")
    profile = validate_model_profile(raw_profile)
    config = config_from_model_profile(profile)
    sessions = payload.get("sessions")
    if not isinstance(sessions, Sequence) or isinstance(sessions, (str, bytes)) or not sessions:
        raise ValueError("batch comparison requires a non-empty sessions array")
    seen_ids = set()
    rows = []
    for raw in sessions:
        if not isinstance(raw, Mapping):
            raise ValueError("each batch session must be an object")
        session_id = str(raw.get("session_id") or "").strip()
        if not session_id or session_id in seen_ids:
            raise ValueError("batch session IDs must be present and unique")
        seen_ids.add(session_id)
        reference = str(raw.get("input") or "").strip()
        if not reference:
            raise ValueError(f"batch session {session_id} requires input")
        input_path = Path(reference)
        if not input_path.is_absolute():
            input_path = (source.parent / input_path).resolve()
        report = await load_position_model_comparison(input_path, config=config)
        directional = report["models"]["directionalized_trade_volume"]
        directional_coverage = directional.get("directional_coverage")
        directional_scored = bool(
            directional.get("status") == "available"
            and directional_coverage is not None
            and float(directional_coverage) >= profile["minimum_directional_coverage"]
        )
        rows.append({
            "session_id": session_id,
            "input": reference,
            "day": _label(raw, "day"),
            "expiry": _label(raw, "expiry"),
            "dte_layer": _label(raw, "dte_layer"),
            "as_of": report["as_of"],
            "status": report["result"]["status"],
            "future_messages_rejected": report["vintage_control"]["future_messages_rejected"],
            "missing_event_time_rejected": report["vintage_control"]["missing_event_time_rejected"],
            "open_interest": report["models"]["open_interest"],
            "raw_trade_volume": report["models"]["raw_trade_volume"],
            "directionalized_trade_volume": (
                directional
                if directional_scored
                else {
                    "status": "insufficient_directional_coverage",
                    "directional_coverage": directional_coverage or 0.0,
                    "minimum_required": profile["minimum_directional_coverage"],
                }
            ),
            "differences": {
                **report["differences"],
                "raw_directional_total_net_gex_delta": (
                    report["differences"]["raw_directional_total_net_gex_delta"]
                    if directional_scored
                    else None
                ),
            },
            "predictive_validity": "unmeasured",
        })
    groups = {
        dimension: _group_rows(rows, dimension)
        for dimension in ("day", "expiry", "dte_layer")
    }
    return {
        "schema": BATCH_REPORT_SCHEMA,
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model_profile": profile,
        "sessions": rows,
        "groups": groups,
        "result": {
            "session_count": len(rows),
            "available_session_count": sum(row["status"] == "available" for row in rows),
            "position_sources_summed": False,
            "predictive_validity": "unmeasured",
        },
        "evidence_ceiling": (
            "descriptive point-in-time batch comparison only; group summaries do not establish "
            "dealer inventory, prediction, execution quality, or profitability"
        ),
    }


def write_batch_comparison(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("batch comparison output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _group_rows(rows: Sequence[Mapping[str, Any]], dimension: str) -> dict[str, Any]:
    labels = sorted({str(row[dimension]) for row in rows})
    return {label: _group_summary([row for row in rows if row[dimension] == label]) for label in labels}


def _group_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    oi_minus_raw = [
        float(row["differences"]["oi_minus_raw_total_net_gex"])
        for row in rows
        if row["differences"]["oi_minus_raw_total_net_gex"] is not None
    ]
    raw_directional = [
        float(row["differences"]["raw_directional_total_net_gex_delta"])
        for row in rows
        if row["differences"]["raw_directional_total_net_gex_delta"] is not None
    ]
    coverages = [
        float(row["directionalized_trade_volume"].get("directional_coverage", 0.0))
        for row in rows
    ]
    return {
        "sessions": len(rows),
        "available_sessions": sum(row["status"] == "available" for row in rows),
        "mean_oi_minus_raw_total_net_gex": mean(oi_minus_raw) if oi_minus_raw else None,
        "mean_raw_directional_total_net_gex_delta": mean(raw_directional) if raw_directional else None,
        "mean_directional_coverage": mean(coverages) if coverages else None,
        "predictive_validity": "unmeasured",
    }


def _label(row: Mapping[str, Any], field: str) -> str:
    value = str(row.get(field) or "unspecified").strip()
    return value or "unspecified"

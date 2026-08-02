"""Local historical session snapshot store."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SESSION_RECORD_SCHEMA = "gex-terminal.session-record.v1"
SESSION_STORE_REPORT_SCHEMA = "gex-terminal.session-store.v1"
DEFAULT_SESSION_STORE_DIR = "historical_sessions"


def save_session_snapshot(
    snapshot: dict[str, Any],
    store_dir: str | Path,
    *,
    source_name: str = "snapshot",
    label: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Save one computed snapshot as a local historical session record."""
    record = build_session_record(
        snapshot,
        source_name=source_name,
        label=label,
        generated_at=generated_at,
    )
    target = _record_path(store_dir, record["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def build_session_record(
    snapshot: dict[str, Any],
    *,
    source_name: str = "snapshot",
    label: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable historical session record from a snapshot."""
    timestamp = generated_at or datetime.now().isoformat(timespec="microseconds")
    metrics = snapshot["metrics"]
    record_label = label or source_name
    return {
        "schema": SESSION_RECORD_SCHEMA,
        "id": _record_id(timestamp, snapshot["symbol"], record_label),
        "generated_at": timestamp,
        "label": record_label,
        "source": {
            "name": source_name,
            "snapshot_timestamp": snapshot.get("timestamp"),
        },
        "inputs": {
            "symbol": snapshot["symbol"],
            "days_to_expiry": float(snapshot["days_to_expiry"]),
            "risk_free_rate": float(snapshot["risk_free_rate"]),
            "contract_multiplier": int(snapshot["contract_multiplier"]),
        },
        "summary": {
            "symbol": snapshot["symbol"],
            "spot": float(snapshot["spot"]),
            "session_change": float(snapshot.get("session_change", 0.0)),
            "total_net_gex": float(metrics["total_net_gex"]),
            "gamma_wall": float(metrics["gamma_wall"]),
            "zero_gamma": float(metrics["zero_gamma"]),
            "call_wall": float(metrics["call_wall"]),
            "put_wall": float(metrics["put_wall"]),
            "imbalance": float(metrics["imbalance"]),
            "strike_count": len(snapshot.get("strikes", ())),
        },
        "feed_quality": snapshot.get("feed_quality"),
        "snapshot": snapshot,
    }


def load_session_records(store_dir: str | Path) -> list[dict[str, Any]]:
    """Load historical session records in chronological order."""
    records_dir = Path(store_dir) / "sessions"
    if not records_dir.exists():
        return []
    records = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if record.get("schema") == SESSION_RECORD_SCHEMA:
            records.append(record)
    return sorted(records, key=lambda record: (record.get("generated_at", ""), record.get("id", "")))


def build_session_store_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build a shareable report from historical session records."""
    loaded = list(records)
    comparison = _compare_records(loaded[-2], loaded[-1]) if len(loaded) >= 2 else None
    return {
        "schema": SESSION_STORE_REPORT_SCHEMA,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": len(loaded),
        "records": loaded,
        "latest_comparison": comparison,
        "uses": [
            "Archive reproducible GEX snapshots after replay, demo, or delayed-data studies.",
            "Compare level drift after model assumption changes without committing generated data.",
            "Attach Markdown or CSV summaries to issues while keeping raw local output ignored by Git.",
        ],
    }


def format_session_save_summary(record: dict[str, Any]) -> str:
    summary = record["summary"]
    return "\n".join((
        f"Saved session record: {record['id']}",
        f"Label: {record['label']}",
        f"Spot: {summary['spot']:,.2f}  Net GEX: {_money(summary['total_net_gex'])}",
        f"Gamma wall: {summary['gamma_wall']:,.1f}  Zero gamma: {summary['zero_gamma']:,.1f}",
        f"Strikes: {summary['strike_count']}  Source: {record['source']['name']}",
    ))


def format_session_record_list(records: Iterable[dict[str, Any]]) -> str:
    loaded = list(records)
    if not loaded:
        return "No session records found. Run: gex-terminal session-store save --replay-session zero-gamma-flip"
    lines = [
        "Historical Session Records",
        "",
        "Index  ID                                      Label             Spot      Wall      Zero      Net GEX",
        "-----  --------------------------------------  ----------------  --------  --------  --------  --------",
    ]
    for index, record in enumerate(loaded, start=1):
        summary = record["summary"]
        lines.append(
            f"{index:<5}  {record['id']:<38}  "
            f"{record['label']:<16.16}  "
            f"{summary['spot']:>8,.2f}  "
            f"{summary['gamma_wall']:>8,.1f}  "
            f"{summary['zero_gamma']:>8,.1f}  "
            f"{_money(summary['total_net_gex']):>8}"
        )
    return "\n".join(lines)


def session_store_report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Historical Session Store",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Records: `{report['record_count']}`",
        "",
        "## Records",
        "",
        "| ID | Label | Source | Spot | Net GEX | Gamma Wall | Zero Gamma | Strikes |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not report["records"]:
        lines.append("| -- | -- | -- | -- | -- | -- | -- | -- |")
    for record in report["records"]:
        summary = record["summary"]
        lines.append(
            f"| `{record['id']}` | {record['label']} | {record['source']['name']} | "
            f"{summary['spot']:,.2f} | {_money(summary['total_net_gex'])} | "
            f"{summary['gamma_wall']:,.1f} | {summary['zero_gamma']:,.1f} | "
            f"{summary['strike_count']} |"
        )

    comparison = report.get("latest_comparison")
    if comparison:
        deltas = comparison["deltas"]
        lines.extend([
            "",
            "## Latest Comparison",
            "",
            f"- From: `{comparison['from']['id']}`",
            f"- To: `{comparison['to']['id']}`",
            f"- Net GEX delta: `{_money(deltas['total_net_gex'])}`",
            f"- Gamma wall delta: `{deltas['gamma_wall']:+,.1f}`",
            f"- Zero gamma delta: `{deltas['zero_gamma']:+,.1f}`",
            f"- Imbalance delta: `{deltas['imbalance']:+,.2f}`",
        ])

    lines.extend(["", "## Uses", ""])
    lines.extend(f"- {use}" for use in report["uses"])
    return "\n".join(lines) + "\n"


def session_store_report_to_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = (
        "record_type",
        "id",
        "label",
        "source",
        "generated_at",
        "spot",
        "session_change",
        "total_net_gex",
        "gamma_wall",
        "zero_gamma",
        "call_wall",
        "put_wall",
        "imbalance",
        "strike_count",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in report["records"]:
        summary = record["summary"]
        writer.writerow({
            "record_type": "record",
            "id": record["id"],
            "label": record["label"],
            "source": record["source"]["name"],
            "generated_at": record["generated_at"],
            "spot": summary["spot"],
            "session_change": summary["session_change"],
            "total_net_gex": summary["total_net_gex"],
            "gamma_wall": summary["gamma_wall"],
            "zero_gamma": summary["zero_gamma"],
            "call_wall": summary["call_wall"],
            "put_wall": summary["put_wall"],
            "imbalance": summary["imbalance"],
            "strike_count": summary["strike_count"],
        })
    comparison = report.get("latest_comparison")
    if comparison:
        deltas = comparison["deltas"]
        writer.writerow({
            "record_type": "comparison",
            "id": f"{comparison['from']['id']}->{comparison['to']['id']}",
            "total_net_gex": deltas["total_net_gex"],
            "gamma_wall": deltas["gamma_wall"],
            "zero_gamma": deltas["zero_gamma"],
            "call_wall": deltas["call_wall"],
            "put_wall": deltas["put_wall"],
            "imbalance": deltas["imbalance"],
        })
    return output.getvalue()


def write_session_store_report(report: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        target.write_text(session_store_report_to_csv(report), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(session_store_report_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Session store report path must end in .json, .csv, or .md")
    return target


def _compare_records(from_record: dict[str, Any], to_record: dict[str, Any]) -> dict[str, Any]:
    from_summary = from_record["summary"]
    to_summary = to_record["summary"]
    return {
        "from": _comparison_side(from_record),
        "to": _comparison_side(to_record),
        "deltas": {
            "spot": _delta(from_summary, to_summary, "spot"),
            "session_change": _delta(from_summary, to_summary, "session_change"),
            "total_net_gex": _delta(from_summary, to_summary, "total_net_gex"),
            "gamma_wall": _delta(from_summary, to_summary, "gamma_wall"),
            "zero_gamma": _delta(from_summary, to_summary, "zero_gamma"),
            "call_wall": _delta(from_summary, to_summary, "call_wall"),
            "put_wall": _delta(from_summary, to_summary, "put_wall"),
            "imbalance": _delta(from_summary, to_summary, "imbalance"),
        },
    }


def _comparison_side(record: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(record.get("id", "")),
        "generated_at": str(record.get("generated_at", "")),
        "label": str(record.get("label", "")),
        "source": str(record.get("source", {}).get("name", "")),
    }


def _delta(from_summary: dict[str, Any], to_summary: dict[str, Any], field: str) -> float:
    return float(to_summary.get(field, 0.0)) - float(from_summary.get(field, 0.0))


def _record_path(store_dir: str | Path, record_id: str) -> Path:
    return Path(store_dir) / "sessions" / f"{record_id}.json"


def _record_id(timestamp: str, symbol: str, label: str) -> str:
    safe_timestamp = (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("T", "_")
    )
    safe_label = "".join(char if char.isalnum() else "_" for char in label.lower()).strip("_")
    return f"{safe_timestamp}_{symbol.lower()}_{safe_label or 'session'}"


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

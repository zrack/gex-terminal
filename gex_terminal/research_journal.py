"""Local historical research journal for replayable GEX snapshots."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from gex_terminal.config import GexConfig
from gex_terminal.replay_catalog import ReplaySession, replay_session_for_name
from gex_terminal.replay_lab import analyze_replay_session


ENTRY_SCHEMA = "gex-terminal.research-journal-entry.v1"
REPORT_SCHEMA = "gex-terminal.research-journal.v1"
DEFAULT_JOURNAL_DIR = "research_journal"


async def add_journal_entry(
    config: GexConfig,
    journal_dir: str | Path,
    *,
    replay_session_name: str,
) -> dict[str, Any]:
    """Replay one bundled session and save it as a durable journal entry."""
    session = replay_session_for_name(replay_session_name)
    replay_config = _journal_config(config, session)
    report = await analyze_replay_session(session, replay_config)
    entry = build_journal_entry(report, config=replay_config)
    target = _entry_path(journal_dir, entry["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return entry


def build_journal_entry(
    replay_report: dict[str, Any],
    *,
    config: GexConfig,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable journal entry from one replay session report."""
    timestamp = generated_at or datetime.now().isoformat(timespec="microseconds")
    summary = dict(replay_report["summary"])
    entry_id = _entry_id(timestamp, summary["name"])
    return {
        "schema": ENTRY_SCHEMA,
        "id": entry_id,
        "generated_at": timestamp,
        "source": {
            "type": "replay_session",
            "name": summary["name"],
            "label": summary["label"],
            "path": summary["path"],
            "description": summary["description"],
        },
        "inputs": {
            "symbol": config.symbol,
            "days_to_expiry": float(config.days_to_expiry),
            "risk_free_rate": float(config.risk_free_rate),
            "contract_multiplier": int(config.contract_multiplier),
        },
        "summary": summary,
        "alerts": replay_report.get("alerts", []),
        "timeline": replay_report.get("timeline", []),
        "snapshot": replay_report.get("snapshot"),
    }


def load_journal_entries(journal_dir: str | Path) -> list[dict[str, Any]]:
    """Load journal entries from disk in chronological order."""
    entries_dir = Path(journal_dir) / "entries"
    if not entries_dir.exists():
        return []
    entries = []
    for path in sorted(entries_dir.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if entry.get("schema") == ENTRY_SCHEMA:
            entries.append(entry)
    return sorted(entries, key=lambda entry: (entry.get("generated_at", ""), entry.get("id", "")))


def build_journal_report(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build a report from saved journal entries."""
    loaded = list(entries)
    comparison = None
    if len(loaded) >= 2:
        comparison = compare_journal_entries(loaded, "previous", "latest")
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "entry_count": len(loaded),
        "entries": loaded,
        "latest_comparison": comparison,
        "uses": [
            "Track whether gamma wall and zero-gamma levels move between replayed sessions.",
            "Keep reproducible before/after snapshots when changing model assumptions.",
            "Share Markdown history in issues without exposing live credentials.",
        ],
    }


def compare_journal_entries(
    entries: Iterable[dict[str, Any]],
    from_ref: str = "previous",
    to_ref: str = "latest",
) -> dict[str, Any]:
    """Compare two journal entries selected by ref, id, id prefix, or index."""
    loaded = list(entries)
    if len(loaded) < 2:
        raise ValueError("Need at least two journal entries to compare.")
    from_entry = resolve_journal_entry(loaded, from_ref)
    to_entry = resolve_journal_entry(loaded, to_ref)
    from_summary = from_entry["summary"]
    to_summary = to_entry["summary"]
    deltas = {
        "spot": _delta(from_summary, to_summary, "spot"),
        "session_change": _delta(from_summary, to_summary, "session_change"),
        "total_net_gex": _delta(from_summary, to_summary, "total_net_gex"),
        "gamma_wall": _delta(from_summary, to_summary, "gamma_wall"),
        "zero_gamma": _delta(from_summary, to_summary, "zero_gamma"),
        "call_wall": _delta(from_summary, to_summary, "call_wall"),
        "put_wall": _delta(from_summary, to_summary, "put_wall"),
        "imbalance": _delta(from_summary, to_summary, "imbalance"),
        "alert_count": int(to_summary.get("alert_count", 0)) - int(from_summary.get("alert_count", 0)),
    }
    return {
        "from": _comparison_side(from_entry),
        "to": _comparison_side(to_entry),
        "deltas": deltas,
        "notes": _comparison_notes(deltas),
    }


def resolve_journal_entry(entries: Iterable[dict[str, Any]], ref: str) -> dict[str, Any]:
    """Resolve latest, previous, first, numeric index, exact id, or id prefix."""
    loaded = list(entries)
    if not loaded:
        raise ValueError("No journal entries found.")

    normalized = str(ref).strip().lower()
    if normalized in {"latest", "last"}:
        return loaded[-1]
    if normalized in {"previous", "prev"}:
        if len(loaded) < 2:
            raise ValueError("Need at least two journal entries for previous.")
        return loaded[-2]
    if normalized == "first":
        return loaded[0]
    if normalized.isdigit():
        index = int(normalized)
        if index < 1 or index > len(loaded):
            raise ValueError(f"Journal index {index} is out of range.")
        return loaded[index - 1]

    matches = [
        entry
        for entry in loaded
        if str(entry.get("id", "")).lower().startswith(normalized)
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError(f"Journal ref '{ref}' matches multiple entries.")
    raise ValueError(f"Unknown journal entry ref '{ref}'.")


def format_journal_add_summary(entry: dict[str, Any]) -> str:
    summary = entry["summary"]
    return "\n".join((
        f"Saved journal entry: {entry['id']}",
        f"Session: {summary['label']} ({summary['name']})",
        f"Spot: {summary['spot']:,.2f}  Net GEX: {_money(summary['total_net_gex'])}",
        f"Gamma wall: {summary['gamma_wall']:,.1f}  Zero gamma: {summary['zero_gamma']:,.1f}",
        f"Alerts: {summary['alert_count']}  Regime: {summary['regime_label']}",
    ))


def format_journal_list(entries: Iterable[dict[str, Any]]) -> str:
    loaded = list(entries)
    if not loaded:
        return "No journal entries found. Run: gex-terminal journal add --replay-session zero-gamma-flip"
    lines = [
        "Journal Entries",
        "",
        "Index  ID                                      Session                 Spot      Wall      Zero      Net GEX",
        "-----  --------------------------------------  ----------------------  --------  --------  --------  --------",
    ]
    for index, entry in enumerate(loaded, start=1):
        summary = entry["summary"]
        lines.append(
            f"{index:<5}  {entry['id']:<38}  "
            f"{summary['name']:<22}  "
            f"{summary['spot']:>8,.2f}  "
            f"{summary['gamma_wall']:>8,.1f}  "
            f"{summary['zero_gamma']:>8,.1f}  "
            f"{_money(summary['total_net_gex']):>8}"
        )
    return "\n".join(lines)


def format_journal_comparison(comparison: dict[str, Any]) -> str:
    from_side = comparison["from"]
    to_side = comparison["to"]
    deltas = comparison["deltas"]
    lines = [
        f"Journal Comparison: {from_side['id']} -> {to_side['id']}",
        f"Sessions: {from_side['session']} -> {to_side['session']}",
        f"Spot delta: {deltas['spot']:+,.2f}",
        f"Net GEX delta: {_money(deltas['total_net_gex'])}",
        f"Gamma wall delta: {deltas['gamma_wall']:+,.1f}",
        f"Zero gamma delta: {deltas['zero_gamma']:+,.1f}",
        f"Alert delta: {deltas['alert_count']:+d}",
    ]
    if comparison.get("notes"):
        lines.extend(["", "Notes:"])
        lines.extend(f"- {note}" for note in comparison["notes"])
    return "\n".join(lines)


def journal_report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Historical Research Journal",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Entries: `{report['entry_count']}`",
        "",
        "## Entries",
        "",
        "| ID | Session | Spot | Session Chg | Net GEX | Gamma Wall | Zero Gamma | Regime | Alerts |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    if not report["entries"]:
        lines.append("| -- | -- | -- | -- | -- | -- | -- | -- | -- |")
    for entry in report["entries"]:
        summary = entry["summary"]
        lines.append(
            f"| `{entry['id']}` | {summary['label']} | {summary['spot']:,.2f} | "
            f"{summary['session_change']:+,.2f} | {_money(summary['total_net_gex'])} | "
            f"{summary['gamma_wall']:,.1f} | {summary['zero_gamma']:,.1f} | "
            f"{summary['regime_label']} | {summary['alert_count']} |"
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
            f"- Spot delta: `{deltas['spot']:+,.2f}`",
            f"- Net GEX delta: `{_money(deltas['total_net_gex'])}`",
            f"- Gamma wall delta: `{deltas['gamma_wall']:+,.1f}`",
            f"- Zero gamma delta: `{deltas['zero_gamma']:+,.1f}`",
            f"- Alert delta: `{deltas['alert_count']:+d}`",
        ])
        if comparison.get("notes"):
            lines.extend(["", "### Notes", ""])
            lines.extend(f"- {note}" for note in comparison["notes"])

    lines.extend(["", "## Research Uses", ""])
    lines.extend(f"- {use}" for use in report["uses"])
    return "\n".join(lines) + "\n"


def journal_report_to_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = (
        "record_type",
        "id",
        "session",
        "label",
        "generated_at",
        "spot",
        "session_change",
        "total_net_gex",
        "gamma_wall",
        "zero_gamma",
        "call_wall",
        "put_wall",
        "imbalance",
        "regime",
        "alert_count",
        "notes",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for entry in report["entries"]:
        summary = entry["summary"]
        writer.writerow({
            "record_type": "entry",
            "id": entry["id"],
            "session": summary["name"],
            "label": summary["label"],
            "generated_at": entry["generated_at"],
            "spot": summary["spot"],
            "session_change": summary["session_change"],
            "total_net_gex": summary["total_net_gex"],
            "gamma_wall": summary["gamma_wall"],
            "zero_gamma": summary["zero_gamma"],
            "call_wall": summary["call_wall"],
            "put_wall": summary["put_wall"],
            "imbalance": summary["imbalance"],
            "regime": summary["regime_label"],
            "alert_count": summary["alert_count"],
        })
    comparison = report.get("latest_comparison")
    if comparison:
        deltas = comparison["deltas"]
        writer.writerow({
            "record_type": "comparison",
            "id": f"{comparison['from']['id']}->{comparison['to']['id']}",
            "spot": deltas["spot"],
            "session_change": deltas["session_change"],
            "total_net_gex": deltas["total_net_gex"],
            "gamma_wall": deltas["gamma_wall"],
            "zero_gamma": deltas["zero_gamma"],
            "call_wall": deltas["call_wall"],
            "put_wall": deltas["put_wall"],
            "imbalance": deltas["imbalance"],
            "alert_count": deltas["alert_count"],
            "notes": "; ".join(comparison.get("notes", [])),
        })
    return output.getvalue()


def write_journal_report(report: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        target.write_text(journal_report_to_csv(report), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(journal_report_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Journal report path must end in .json, .csv, or .md")
    return target


def _journal_config(config: GexConfig, session: ReplaySession) -> GexConfig:
    symbol = "ES"
    return replace(
        config,
        symbol=symbol,
        symbols=_symbols_with_target(config.symbols, symbol),
        data_mode="replay",
        data_provider="replay",
        contract_multiplier=50,
        replay_path=session.path,
        replay_delay_seconds=0.0,
    )


def _entry_path(journal_dir: str | Path, entry_id: str) -> Path:
    return Path(journal_dir) / "entries" / f"{entry_id}.json"


def _symbols_with_target(symbols: tuple[str, ...], target_symbol: str) -> tuple[str, ...]:
    cleaned = tuple(symbol for symbol in symbols if symbol != target_symbol)
    return (target_symbol, *cleaned)[:4]


def _entry_id(timestamp: str, session_name: str) -> str:
    safe_timestamp = (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("T", "_")
    )
    safe_session = session_name.replace("-", "_")
    return f"{safe_timestamp}_{safe_session}"


def _comparison_side(entry: dict[str, Any]) -> dict[str, str]:
    source = entry.get("source", {})
    return {
        "id": str(entry.get("id", "")),
        "generated_at": str(entry.get("generated_at", "")),
        "session": str(source.get("name", "")),
        "label": str(source.get("label", "")),
    }


def _delta(from_summary: dict[str, Any], to_summary: dict[str, Any], field: str) -> float:
    return float(to_summary.get(field, 0.0)) - float(from_summary.get(field, 0.0))


def _comparison_notes(deltas: dict[str, float | int]) -> list[str]:
    notes = []
    if deltas["gamma_wall"]:
        direction = "higher" if deltas["gamma_wall"] > 0 else "lower"
        notes.append(f"Gamma wall moved {direction} by {abs(float(deltas['gamma_wall'])):,.1f}.")
    if abs(float(deltas["zero_gamma"])) >= 1:
        direction = "higher" if deltas["zero_gamma"] > 0 else "lower"
        notes.append(f"Zero-gamma boundary moved {direction} by {abs(float(deltas['zero_gamma'])):,.1f}.")
    if deltas["total_net_gex"]:
        direction = "increased" if deltas["total_net_gex"] > 0 else "decreased"
        notes.append(f"Total net GEX {direction} by {_money_abs(deltas['total_net_gex'])}.")
    if deltas["alert_count"]:
        direction = "more" if deltas["alert_count"] > 0 else "fewer"
        notes.append(f"Latest entry has {abs(int(deltas['alert_count']))} {direction} replay alerts.")
    if not notes:
        notes.append("No major top-line level changes between the selected entries.")
    return notes


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


def _money_abs(value: float) -> str:
    value = abs(float(value))
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"

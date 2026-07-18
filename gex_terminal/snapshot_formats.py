"""Additional snapshot export formats for sharing and review."""

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict

from gex_terminal.snapshot import write_snapshot


def snapshot_to_csv(snapshot: Dict[str, Any]) -> str:
    """Render snapshot metrics, levels, expiries, and strikes as one CSV."""
    output = io.StringIO()
    fieldnames = (
        "record_type",
        "name",
        "label",
        "value",
        "strike",
        "call_volume",
        "put_volume",
        "gamma",
        "call_gex",
        "put_gex",
        "net_gex",
        "notes",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    writer.writerow({
        "record_type": "session",
        "name": "spot",
        "label": "Spot",
        "value": snapshot["spot"],
        "notes": f"symbol={snapshot['symbol']}",
    })
    writer.writerow({
        "record_type": "session",
        "name": "session_change",
        "label": "Session Change",
        "value": snapshot["session_change"],
    })
    for name, value in snapshot["metrics"].items():
        writer.writerow({
            "record_type": "metric",
            "name": name,
            "label": name.replace("_", " ").title(),
            "value": json.dumps(value) if isinstance(value, list) else value,
        })
    for expiry, value in snapshot.get("expiry_breakdown", {}).items():
        writer.writerow({
            "record_type": "expiry",
            "name": expiry,
            "label": expiry,
            "value": value,
        })
    feed_quality = snapshot.get("feed_quality")
    if isinstance(feed_quality, dict):
        writer.writerow({
            "record_type": "feed_quality",
            "name": "health",
            "label": "Feed Health",
            "value": feed_quality.get("health"),
            "notes": "; ".join(feed_quality.get("notes", ())),
        })
    for alert in snapshot.get("alerts", ()):
        writer.writerow({
            "record_type": "alert",
            "name": alert.get("type"),
            "label": alert.get("severity", "").title(),
            "value": alert.get("spot"),
            "notes": alert.get("message"),
        })
    for row in snapshot["strikes"]:
        writer.writerow({
            "record_type": "strike",
            "name": row["strike"],
            "label": f"{row['strike']:g}",
            "strike": row["strike"],
            "call_volume": row["call_volume"],
            "put_volume": row["put_volume"],
            "gamma": row["gamma"],
            "call_gex": row["call_gex"],
            "put_gex": row["put_gex"],
            "net_gex": row["net_gex"],
        })
    return output.getvalue()


def snapshot_to_markdown(snapshot: Dict[str, Any]) -> str:
    """Render a human-readable snapshot summary."""
    metrics = snapshot["metrics"]
    lines = [
        f"# {snapshot['symbol']} GEX Snapshot",
        "",
        f"- Timestamp: `{snapshot['timestamp']}`",
        f"- Spot: `{snapshot['spot']:,.2f}`",
        f"- Session change: `{snapshot['session_change']:+,.2f}`",
        f"- Total net GEX: `{_money(metrics['total_net_gex'])}`",
        f"- Gamma wall: `{metrics['gamma_wall']:,.1f}`",
        f"- Zero gamma: `{metrics['zero_gamma']:,.1f}`",
        f"- Call wall: `{metrics['call_wall']:,.1f}`",
        f"- Put wall: `{metrics['put_wall']:,.1f}`",
        f"- Concentration band: `{metrics['concentration_band'][0]:,.1f}` to `{metrics['concentration_band'][1]:,.1f}`",
        "",
        "## Major Strikes",
        "",
        "| Strike | Call Vol | Put Vol | Net GEX |",
        "| ---: | ---: | ---: | ---: |",
    ]
    rows = sorted(
        snapshot["strikes"],
        key=lambda row: abs(float(row["net_gex"])),
        reverse=True,
    )
    for row in rows[:8]:
        lines.append(
            f"| {row['strike']:,.1f} | {row['call_volume']:,} | "
            f"{row['put_volume']:,} | {_money(row['net_gex'])} |"
        )
    if snapshot.get("expiry_breakdown"):
        lines.extend(["", "## Expiry Breakdown", ""])
        for expiry, value in snapshot["expiry_breakdown"].items():
            lines.append(f"- `{expiry}`: `{_money(value)}`")
    if snapshot.get("feed_quality"):
        quality = snapshot["feed_quality"]
        lines.extend([
            "",
            "## Feed Quality",
            "",
            f"- Health: `{quality.get('health', '--')}`",
            f"- Status: `{quality.get('status', '--')}`",
            f"- Payloads: `{quality.get('message_count', 0)}` ok, "
            f"`{quality.get('dropped_count', 0)}` dropped, "
            f"`{quality.get('malformed_count', 0)}` malformed",
        ])
        notes = quality.get("notes") or ()
        if notes:
            lines.append(f"- Notes: `{'; '.join(notes)}`")
    if snapshot.get("alerts"):
        lines.extend([
            "",
            "## Replay Alerts",
            "",
            "| Severity | Type | Message |",
            "| --- | --- | --- |",
        ])
        for alert in snapshot["alerts"][:12]:
            lines.append(
                f"| {alert.get('severity', '--')} | {alert.get('type', '--')} | "
                f"{alert.get('message', '')} |"
            )
    return "\n".join(lines) + "\n"


def write_snapshot_export(snapshot: Dict[str, Any], output_path: str) -> Path:
    """Write snapshot data as JSON, CSV, or Markdown based on extension."""
    target = Path(output_path)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        return write_snapshot(snapshot, output_path)

    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".csv":
        target.write_text(snapshot_to_csv(snapshot), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(snapshot_to_markdown(snapshot), encoding="utf-8")
    else:
        raise ValueError("Snapshot export path must end in .json, .csv, or .md")
    return target


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

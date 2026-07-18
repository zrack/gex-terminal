"""Offline replay research-lab reports for bundled synthetic sessions."""

import csv
import io
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import dumps_normalized_message
from gex_terminal.regime import build_regime_map
from gex_terminal.replay_catalog import (
    ReplaySession,
    bundled_replay_sessions,
    replay_session_for_name,
)
from gex_terminal.snapshot import build_snapshot


MAJOR_EXPOSURE_DELTA_RATIO = 0.30
MAJOR_EXPOSURE_DELTA_FLOOR = 250_000_000.0


async def build_replay_lab_report(
    config: GexConfig,
    session_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Run replay sessions offline and assemble an explainable research report."""
    sessions = _selected_sessions(session_names)
    session_reports = [
        await analyze_replay_session(session, config)
        for session in sessions
    ]
    return {
        "schema": "gex-terminal.replay-lab.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": config.symbol,
        "sessions": session_reports,
        "comparisons": compare_replay_sessions(session_reports),
        "leaderboard": build_replay_leaderboard(session_reports),
        "inputs": {
            "days_to_expiry": float(config.days_to_expiry),
            "risk_free_rate": float(config.risk_free_rate),
            "contract_multiplier": int(config.contract_multiplier),
        },
    }


async def analyze_replay_session(
    session: ReplaySession,
    config: GexConfig,
) -> dict[str, Any]:
    """Replay one bundled fixture and collect snapshots, alerts, and quality notes."""
    replay_config = replace(
        config,
        data_mode="replay",
        replay_path=session.path,
        replay_delay_seconds=0.0,
    )
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=replay_config.contract_multiplier),
        target_underlying=replay_config.symbol,
        risk_free_rate=replay_config.risk_free_rate,
        data_mode="replay",
        stale_after_seconds=replay_config.stale_after_seconds,
    )
    adapter = ReplayAdapter(consumer, replay_config.replay_path, delay_seconds=0.0)
    alerts: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    phases: set[str] = set()
    quality_cases: set[str] = set()
    timestamps: list[str] = []
    previous_point: dict[str, Any] | None = None

    consumer.mark_connected()
    messages = list(adapter._load_messages())
    for index, message in enumerate(messages, start=1):
        _record_message_metadata(message, phases, timestamps)
        quality_case = str(message.get("quality_case", "")).strip()
        if quality_case and quality_case not in quality_cases:
            quality_cases.add(quality_case)
            alerts.append(_quality_alert(session.name, message, quality_case))

        await consumer.update_market_state(dumps_normalized_message(message))
        if consumer.current_spot == 0.0 or not consumer.chain_state:
            continue

        data = await consumer.process_latest_snapshot(
            days_to_expiry=replay_config.days_to_expiry
        )
        if "error" in data:
            continue
        point = _timeline_point(
            session_name=session.name,
            message_index=index,
            message=message,
            data=data,
            consumer=consumer,
        )
        _append_transition_alerts(
            alerts=alerts,
            session_name=session.name,
            previous=previous_point,
            current=point,
        )
        timeline.append(point)
        previous_point = point

    consumer.mark_disconnected()
    if not timeline:
        raise ValueError(f"Replay session {session.name} did not produce a snapshot")

    data = await consumer.process_latest_snapshot(days_to_expiry=replay_config.days_to_expiry)
    breakdown = await consumer.process_expiry_breakdown(
        days_to_expiry=replay_config.days_to_expiry
    )
    snapshot = build_snapshot(
        symbol=consumer.target_underlying,
        spot=consumer.current_spot,
        session_open=consumer.session_open,
        days_to_expiry=replay_config.days_to_expiry,
        contract_multiplier=replay_config.contract_multiplier,
        risk_free_rate=replay_config.risk_free_rate,
        data=data,
        chain_state=consumer.chain_state,
        expiry_breakdown=breakdown,
    )
    snapshot["replay_session"] = {
        "name": session.name,
        "label": session.label,
        "path": session.path,
        "description": session.description,
        "phases": sorted(phases),
        "first_timestamp": timestamps[0] if timestamps else "",
        "last_timestamp": timestamps[-1] if timestamps else "",
    }
    snapshot["alerts"] = alerts
    snapshot["feed_quality"] = consumer.feed_quality_snapshot()

    regime = build_regime_map(data, consumer.current_spot)
    summary = {
        "name": session.name,
        "label": session.label,
        "path": session.path,
        "description": session.description,
        "message_count": len(messages),
        "snapshot_count": len(timeline),
        "phase_count": len(phases),
        "phases": sorted(phases),
        "alert_count": len(alerts),
        "spot": float(snapshot["spot"]),
        "session_change": float(snapshot["session_change"]),
        "total_net_gex": float(snapshot["metrics"]["total_net_gex"]),
        "gamma_wall": float(snapshot["metrics"]["gamma_wall"]),
        "zero_gamma": float(snapshot["metrics"]["zero_gamma"]),
        "call_wall": float(snapshot["metrics"]["call_wall"]),
        "put_wall": float(snapshot["metrics"]["put_wall"]),
        "imbalance": float(snapshot["metrics"]["imbalance"]),
        "concentration_ratio": float(snapshot["metrics"]["concentration_ratio"]),
        "regime": regime["state"],
        "regime_label": regime["label"],
        "first_timestamp": timestamps[0] if timestamps else "",
        "last_timestamp": timestamps[-1] if timestamps else "",
    }
    return {
        "name": session.name,
        "label": session.label,
        "path": session.path,
        "description": session.description,
        "summary": summary,
        "alerts": alerts,
        "timeline": timeline,
        "snapshot": snapshot,
    }


def compare_replay_sessions(session_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare final saved snapshots in catalog order."""
    comparisons = []
    previous = None
    for report in session_reports:
        current = report["summary"]
        if previous is not None:
            comparisons.append({
                "from_session": previous["name"],
                "to_session": current["name"],
                "spot_delta": current["spot"] - previous["spot"],
                "net_gex_delta": current["total_net_gex"] - previous["total_net_gex"],
                "gamma_wall_delta": current["gamma_wall"] - previous["gamma_wall"],
                "zero_gamma_delta": current["zero_gamma"] - previous["zero_gamma"],
                "alert_count_delta": current["alert_count"] - previous["alert_count"],
            })
        previous = current
    return comparisons


def build_replay_leaderboard(session_reports: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [report["summary"] for report in session_reports]
    if not summaries:
        return {}
    return {
        "largest_absolute_net_gex": max(
            summaries,
            key=lambda item: abs(float(item["total_net_gex"])),
        )["name"],
        "most_alerts": max(summaries, key=lambda item: int(item["alert_count"]))["name"],
        "tightest_concentration": max(
            summaries,
            key=lambda item: float(item["concentration_ratio"]),
        )["name"],
        "largest_spot_move": max(
            summaries,
            key=lambda item: abs(float(item["session_change"])),
        )["name"],
    }


def replay_lab_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Replay Research Lab",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Symbol: `{report['symbol']}`",
        f"- Sessions analyzed: `{len(report['sessions'])}`",
        f"- Days to expiry: `{report['inputs']['days_to_expiry']:g}`",
        f"- Contract multiplier: `{report['inputs']['contract_multiplier']}`",
        "",
        "## Lab Dashboard",
        "",
        "| Session | Spot | Session Chg | Net GEX | Gamma Wall | Zero Gamma | Regime | Alerts |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for session in report["sessions"]:
        summary = session["summary"]
        lines.append(
            f"| {summary['label']} | {summary['spot']:,.2f} | "
            f"{summary['session_change']:+,.2f} | {_money(summary['total_net_gex'])} | "
            f"{summary['gamma_wall']:,.1f} | {summary['zero_gamma']:,.1f} | "
            f"{summary['regime_label']} | {summary['alert_count']} |"
        )

    leaderboard = report.get("leaderboard", {})
    if leaderboard:
        lines.extend([
            "",
            "## Leaderboard",
            "",
            f"- Largest absolute net GEX: `{leaderboard['largest_absolute_net_gex']}`",
            f"- Most alerts: `{leaderboard['most_alerts']}`",
            f"- Tightest concentration: `{leaderboard['tightest_concentration']}`",
            f"- Largest spot move: `{leaderboard['largest_spot_move']}`",
        ])

    if report.get("comparisons"):
        lines.extend([
            "",
            "## Session Comparison",
            "",
            "| From | To | Spot Δ | Net GEX Δ | Wall Δ | Zero Δ | Alert Δ |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for row in report["comparisons"]:
            lines.append(
                f"| {row['from_session']} | {row['to_session']} | "
                f"{row['spot_delta']:+,.2f} | {_money(row['net_gex_delta'])} | "
                f"{row['gamma_wall_delta']:+,.1f} | {row['zero_gamma_delta']:+,.1f} | "
                f"{row['alert_count_delta']:+d} |"
            )

    lines.extend(["", "## Alerts", ""])
    for session in report["sessions"]:
        alerts = session["alerts"]
        lines.append(f"### {session['label']}")
        if not alerts:
            lines.append("")
            lines.append("No replay alerts fired.")
            lines.append("")
            continue
        lines.extend([
            "",
            "| Severity | Type | Phase | Message |",
            "| --- | --- | --- | --- |",
        ])
        for alert in alerts[:12]:
            lines.append(
                f"| {alert['severity']} | {alert['type']} | "
                f"{alert.get('phase') or '--'} | {alert['message']} |"
            )
        lines.append("")

    lines.extend([
        "## Contributor Uses",
        "",
        "- Add or tune replay fixtures and compare the resulting session cards.",
        "- Use alerts as regression targets for wall shifts, zero-gamma crosses, and exposure changes.",
        "- Share the Markdown report in issues without exposing live credentials or provider payloads.",
        "- Use the JSON report as a saved snapshot baseline for future replay changes.",
    ])
    return "\n".join(lines) + "\n"


def replay_lab_to_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = (
        "record_type",
        "session",
        "label",
        "name",
        "severity",
        "value",
        "spot",
        "session_change",
        "total_net_gex",
        "gamma_wall",
        "zero_gamma",
        "message",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for session in report["sessions"]:
        summary = session["summary"]
        writer.writerow({
            "record_type": "session",
            "session": summary["name"],
            "label": summary["label"],
            "spot": summary["spot"],
            "session_change": summary["session_change"],
            "total_net_gex": summary["total_net_gex"],
            "gamma_wall": summary["gamma_wall"],
            "zero_gamma": summary["zero_gamma"],
            "value": summary["alert_count"],
        })
        for alert in session["alerts"]:
            writer.writerow({
                "record_type": "alert",
                "session": alert["session"],
                "name": alert["type"],
                "severity": alert["severity"],
                "spot": alert.get("spot"),
                "gamma_wall": alert.get("gamma_wall"),
                "zero_gamma": alert.get("zero_gamma"),
                "message": alert["message"],
            })
    for row in report.get("comparisons", []):
        writer.writerow({
            "record_type": "comparison",
            "session": row["to_session"],
            "name": row["from_session"],
            "spot": row["spot_delta"],
            "total_net_gex": row["net_gex_delta"],
            "gamma_wall": row["gamma_wall_delta"],
            "zero_gamma": row["zero_gamma_delta"],
            "value": row["alert_count_delta"],
        })
    return output.getvalue()


def write_replay_lab_report(report: dict[str, Any], output_path: str) -> Path:
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        target.write_text(replay_lab_to_csv(report), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(replay_lab_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Replay lab report path must end in .json, .csv, or .md")
    return target


def _selected_sessions(session_names: Iterable[str] | None) -> tuple[ReplaySession, ...]:
    if session_names is None:
        return bundled_replay_sessions()
    return tuple(replay_session_for_name(name) for name in session_names)


def _record_message_metadata(
    message: dict[str, Any],
    phases: set[str],
    timestamps: list[str],
) -> None:
    phase = str(message.get("session_phase", "")).strip()
    if phase:
        phases.add(phase)
    timestamp = str(message.get("timestamp", "")).strip()
    if timestamp:
        timestamps.append(timestamp)


def _timeline_point(
    *,
    session_name: str,
    message_index: int,
    message: dict[str, Any],
    data: dict[str, Any],
    consumer: StatefulGexConsumer,
) -> dict[str, Any]:
    call_total = sum(float(value) for value in data["call_gex"])
    put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
    imbalance = call_total / put_total_abs if put_total_abs else 0.0
    regime = build_regime_map(data, consumer.current_spot)
    return {
        "session": session_name,
        "message_index": message_index,
        "timestamp": message.get("timestamp", ""),
        "phase": message.get("session_phase", ""),
        "spot": float(consumer.current_spot),
        "total_net_gex": float(data["total_net_gex"]),
        "gamma_wall": float(data["gamma_wall_strike"]),
        "zero_gamma": float(data["zero_gamma_strike"]),
        "call_wall": float(data["call_wall_strike"]),
        "put_wall": float(data["put_wall_strike"]),
        "imbalance": float(imbalance),
        "regime": regime["state"],
        "regime_label": regime["label"],
    }


def _append_transition_alerts(
    *,
    alerts: list[dict[str, Any]],
    session_name: str,
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> None:
    if previous is None:
        alerts.append(_alert(
            session=session_name,
            alert_type="session_started",
            severity="info",
            point=current,
            message=(
                f"Replay initialized at spot {current['spot']:,.2f}, "
                f"wall {current['gamma_wall']:,.1f}, zero {current['zero_gamma']:,.1f}."
            ),
        ))
        return

    if current["gamma_wall"] != previous["gamma_wall"]:
        alerts.append(_alert(
            session=session_name,
            alert_type="gamma_wall_shift",
            severity="medium",
            point=current,
            message=(
                f"Gamma wall shifted {previous['gamma_wall']:,.1f} -> "
                f"{current['gamma_wall']:,.1f}."
            ),
        ))

    if _crossed_zero_gamma(previous, current):
        alerts.append(_alert(
            session=session_name,
            alert_type="zero_gamma_cross",
            severity="high",
            point=current,
            message=(
                f"Spot crossed the zero-gamma boundary near "
                f"{current['zero_gamma']:,.1f}."
            ),
        ))

    if _regime_flipped(previous, current):
        alerts.append(_alert(
            session=session_name,
            alert_type="regime_flip",
            severity="high",
            point=current,
            message=(
                f"Net GEX sign flipped from {_money(previous['total_net_gex'])} "
                f"to {_money(current['total_net_gex'])}."
            ),
        ))

    delta = current["total_net_gex"] - previous["total_net_gex"]
    threshold = max(
        MAJOR_EXPOSURE_DELTA_FLOOR,
        abs(previous["total_net_gex"]) * MAJOR_EXPOSURE_DELTA_RATIO,
    )
    if abs(delta) >= threshold:
        alerts.append(_alert(
            session=session_name,
            alert_type="major_exposure_change",
            severity="medium",
            point=current,
            message=f"Total net GEX changed by {_money(delta)}.",
        ))

    if _crossed_imbalance_threshold(previous["imbalance"], current["imbalance"]):
        alerts.append(_alert(
            session=session_name,
            alert_type="imbalance_threshold",
            severity="low",
            point=current,
            message=f"Call/put imbalance moved to {current['imbalance']:.2f}x.",
        ))


def _quality_alert(session_name: str, message: dict[str, Any], quality_case: str) -> dict[str, Any]:
    labels = {
        "off_symbol_drop": "Off-symbol tick detected for provider-health testing.",
        "partial_chain": "Partial chain coverage detected in replay fixture.",
        "latency_probe": "Latency probe event detected in replay fixture.",
        "stale_tick": "Stale tick simulation detected in replay fixture.",
        "dropped_message": "Dropped-message simulation detected in replay fixture.",
    }
    return {
        "session": session_name,
        "type": "data_quality",
        "severity": "low",
        "timestamp": message.get("timestamp", ""),
        "phase": message.get("session_phase", ""),
        "spot": message.get("price"),
        "gamma_wall": None,
        "zero_gamma": None,
        "message": labels.get(quality_case, f"Quality scenario detected: {quality_case}."),
    }


def _alert(
    *,
    session: str,
    alert_type: str,
    severity: str,
    point: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return {
        "session": session,
        "type": alert_type,
        "severity": severity,
        "timestamp": point.get("timestamp", ""),
        "phase": point.get("phase", ""),
        "spot": float(point["spot"]),
        "gamma_wall": float(point["gamma_wall"]),
        "zero_gamma": float(point["zero_gamma"]),
        "message": message,
    }


def _crossed_zero_gamma(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_distance = previous["spot"] - previous["zero_gamma"]
    current_distance = current["spot"] - current["zero_gamma"]
    if previous_distance == 0 or current_distance == 0:
        return True
    return previous_distance * current_distance < 0


def _regime_flipped(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return previous["total_net_gex"] * current["total_net_gex"] < 0


def _crossed_imbalance_threshold(previous: float, current: float) -> bool:
    thresholds = (0.75, 1.0, 1.25, 1.5, 2.0)
    return any(
        (previous < threshold <= current) or (previous > threshold >= current)
        for threshold in thresholds
    )


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

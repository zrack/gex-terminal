"""Offline demo-pack generation for GitHub-ready project previews."""

from __future__ import annotations

import html
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import dumps_normalized_message
from gex_terminal.overlays import write_tradingview_overlay
from gex_terminal.provider_fixture_lab import (
    build_provider_fixture_lab_report,
    write_provider_fixture_lab_report,
)
from gex_terminal.replay_catalog import ReplaySession, replay_session_for_name
from gex_terminal.replay_lab import build_replay_lab_report, write_replay_lab_report
from gex_terminal.screenshot import export_app_screenshot_svg
from gex_terminal.snapshot import build_snapshot
from gex_terminal.snapshot_formats import write_snapshot_export
from gex_terminal.tui import GexTerminalApp


DEMO_LAB_SCHEMA = "gex-terminal.demo-lab.v1"
DEFAULT_DEMO_SESSION = "zero-gamma-flip"


async def build_demo_lab(
    config: GexConfig,
    output_dir: str | Path,
    *,
    replay_session_name: str = DEFAULT_DEMO_SESSION,
    screenshot_width: int = 180,
    screenshot_height: int = 54,
) -> dict[str, Any]:
    """Generate a shareable offline demo pack from bundled replay data."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    session = replay_session_for_name(replay_session_name)
    lab_config = _demo_lab_config(config, session)
    snapshot, consumer, data = await compute_replay_snapshot(lab_config)
    snapshot["feed_quality"] = consumer.feed_quality_snapshot()
    snapshot["demo_lab"] = {
        "replay_session": session.name,
        "replay_path": session.source_ref,
        "description": session.description,
    }

    replay_report = await build_replay_lab_report(
        lab_config,
        session_names=(session.name,),
    )
    provider_report = await build_provider_fixture_lab_report(lab_config)

    artifacts: list[dict[str, str]] = []
    artifacts.append(_write_artifact(
        target,
        target / "gex-terminal-color.svg",
        "visual",
        "Color replay preview generated from the snapshot metrics.",
        demo_lab_preview_svg(snapshot, session, replay_report, provider_report),
    ))
    artifacts.append(_artifact(
        target,
        await write_terminal_screenshot(
            lab_config,
            target / "terminal-screenshot.svg",
            width=screenshot_width,
            height=screenshot_height,
        ),
        "visual",
        "Actual Textual terminal SVG capture from the replay session.",
    ))
    artifacts.append(_artifact(
        target,
        write_snapshot_export(snapshot, str(target / "snapshot.json")),
        "snapshot",
        "Full machine-readable GEX snapshot.",
    ))
    artifacts.append(_artifact(
        target,
        write_snapshot_export(snapshot, str(target / "snapshot.md")),
        "snapshot",
        "Human-readable GEX snapshot summary.",
    ))
    artifacts.append(_artifact(
        target,
        write_tradingview_overlay(snapshot, str(target / "tradingview-overlay.json")),
        "overlay",
        "TradingView-style levels and band export.",
    ))
    artifacts.append(_artifact(
        target,
        write_tradingview_overlay(snapshot, str(target / "tradingview-overlay.csv")),
        "overlay",
        "Spreadsheet-friendly chart-overlay levels.",
    ))
    artifacts.append(_artifact(
        target,
        write_replay_lab_report(replay_report, str(target / "replay_lab.md")),
        "replay-lab",
        "Replay lab report for the selected demo session.",
    ))
    artifacts.append(_artifact(
        target,
        write_replay_lab_report(replay_report, str(target / "replay_lab.json")),
        "replay-lab",
        "Replay lab JSON baseline for the selected demo session.",
    ))
    artifacts.append(_artifact(
        target,
        write_provider_fixture_lab_report(provider_report, str(target / "provider_fixture_lab.md")),
        "provider-fixture-lab",
        "Provider fixture scorecard for bundled provider-shaped samples.",
    ))
    artifacts.append(_artifact(
        target,
        write_provider_fixture_lab_report(provider_report, str(target / "provider_fixture_lab.json")),
        "provider-fixture-lab",
        "Provider fixture JSON baseline for bundled provider-shaped samples.",
    ))

    readme_path = target / "README.md"
    manifest_path = target / "manifest.json"
    artifacts = [
        _artifact(
            target,
            readme_path,
            "index",
            "Demo-pack overview and artifact guide.",
        ),
        _artifact(
            target,
            manifest_path,
            "manifest",
            "Machine-readable artifact index and top-line metrics.",
        ),
        *artifacts,
    ]
    manifest = _demo_lab_manifest(
        target=target,
        session=session,
        config=lab_config,
        snapshot=snapshot,
        replay_report=replay_report,
        provider_report=provider_report,
        artifacts=artifacts,
    )
    readme_path.write_text(demo_lab_readme(manifest), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


async def compute_replay_snapshot(
    config: GexConfig,
) -> tuple[dict[str, Any], StatefulGexConsumer, dict[str, Any]]:
    """Replay a bundled session into one final snapshot without live credentials."""
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode="replay",
        stale_after_seconds=config.stale_after_seconds,
        expiry_filter=config.expiry_filter,
    )
    adapter = ReplayAdapter(consumer, config.replay_path, delay_seconds=0.0)
    consumer.mark_connected()
    messages = list(adapter._load_messages())
    for message in messages:
        await consumer.update_market_state(dumps_normalized_message(message))
    consumer.mark_subscribed(len(consumer.chain_state))

    data = await consumer.process_latest_snapshot(
        days_to_expiry=config.days_to_expiry,
        expiry_filter=config.expiry_filter,
    )
    if "error" in data:
        raise ValueError(f"Replay session did not produce a snapshot: {data['error']}")
    breakdown = await consumer.process_expiry_breakdown(days_to_expiry=config.days_to_expiry)
    snapshot = build_snapshot(
        symbol=consumer.target_underlying,
        spot=consumer.current_spot,
        session_open=consumer.session_open,
        days_to_expiry=config.days_to_expiry,
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        data=data,
        chain_state=consumer.chain_state,
        expiry_breakdown=breakdown,
    )
    return snapshot, consumer, data


async def write_terminal_screenshot(
    config: GexConfig,
    output_path: str | Path,
    *,
    width: int,
    height: int,
) -> Path:
    """Render the actual Textual app after replaying a demo session."""
    _, consumer, _ = await compute_replay_snapshot(config)
    app = GexTerminalApp(consumer=consumer, config=config)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause(0.2)
        await app.refresh_terminal_data()
        await pilot.pause(0.2)
        svg = export_app_screenshot_svg(app, title="GEX Terminal Demo Lab")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(svg, encoding="utf-8")
    return target


def demo_lab_preview_svg(
    snapshot: dict[str, Any],
    session: ReplaySession,
    replay_report: dict[str, Any],
    provider_report: dict[str, Any],
) -> str:
    """Render a color preview SVG from real offline snapshot values."""
    metrics = snapshot["metrics"]
    quality = snapshot.get("feed_quality", {})
    replay_summary = replay_report["sessions"][0]["summary"]
    provider_scorecard = provider_report["scorecard"]
    rows = _preview_rows(snapshot)
    max_abs_net = max((abs(float(row["net_gex"])) for row in rows), default=1.0)
    total_net = float(metrics["total_net_gex"])
    net_color = "#4ade80" if total_net >= 0 else "#fb7185"
    health = str(quality.get("health", "unknown"))

    row_blocks = []
    start_y = 374
    for index, row in enumerate(rows):
        y = start_y + index * 42
        net_gex = float(row["net_gex"])
        bar_width = int(150 * (abs(net_gex) / max_abs_net)) if max_abs_net else 0
        bar_color = "#4ade80" if net_gex >= 0 else "#fb7185"
        row_fill = "#111820" if index % 2 == 0 else "#0d141c"
        row_blocks.append(f"""
  <rect x="78" y="{y - 25}" width="748" height="34" rx="5" fill="{row_fill}" stroke="#1e293b"/>
  <text x="98" y="{y}" class="mono table">{_fmt_strike(row['strike'])}</text>
  <text x="238" y="{y}" class="mono table muted">{int(row['call_volume']):,}</text>
  <text x="368" y="{y}" class="mono table muted">{int(row['put_volume']):,}</text>
  <text x="500" y="{y}" class="mono table" fill="{bar_color}">{_money(net_gex)}</text>
  <rect x="646" y="{y - 17}" width="{bar_width}" height="12" rx="3" fill="{bar_color}" opacity="0.75"/>
""")

    return f"""<svg width="1400" height="860" viewBox="0 0 1400 860" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">gex-terminal offline demo lab preview</title>
  <desc id="desc">Color preview generated from the {html.escape(session.label)} replay session.</desc>
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#06111a"/>
      <stop offset="0.55" stop-color="#0b141d"/>
      <stop offset="1" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="lane" x1="0" x2="1">
      <stop offset="0" stop-color="#fb7185"/>
      <stop offset="0.45" stop-color="#fbbf24"/>
      <stop offset="0.62" stop-color="#38bdf8"/>
      <stop offset="1" stop-color="#4ade80"/>
    </linearGradient>
    <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <style>
      .mono {{ font-family: "Fira Code", "SFMono-Regular", Consolas, monospace; }}
      .small {{ fill: #94a3b8; font-size: 18px; }}
      .label {{ fill: #64748b; font-size: 17px; font-weight: 700; }}
      .value {{ fill: #f8fafc; font-size: 30px; font-weight: 800; }}
      .panel-title {{ fill: #e2e8f0; font-size: 20px; font-weight: 800; }}
      .table {{ fill: #dbeafe; font-size: 18px; }}
      .muted {{ fill: #94a3b8; }}
    </style>
  </defs>

  <rect width="1400" height="860" fill="url(#bg)"/>
  <rect x="44" y="36" width="1312" height="776" rx="16" fill="#080d13" stroke="#263445" stroke-width="2"/>
  <rect x="44" y="36" width="1312" height="54" rx="16" fill="#101827"/>
  <circle cx="76" cy="64" r="8" fill="#fb7185"/>
  <circle cx="104" cy="64" r="8" fill="#fbbf24"/>
  <circle cx="132" cy="64" r="8" fill="#4ade80"/>
  <text x="166" y="71" class="mono small">gex-terminal // demo-lab // {html.escape(session.name)}</text>

  <text x="78" y="132" class="mono label">OFFLINE REPLAY</text>
  <text x="78" y="174" class="mono" fill="#f8fafc" font-size="38" font-weight="900">Intraday GEX Research Terminal</text>
  <text x="78" y="210" class="mono small">{html.escape(session.description)}</text>

{_metric_card(78, 244, "SPOT", _fmt_strike(snapshot["spot"], 2), "#38bdf8")}
{_metric_card(286, 244, "NET GEX", _money(total_net), net_color)}
{_metric_card(494, 244, "GAMMA WALL", _fmt_strike(metrics["gamma_wall"]), "#fbbf24")}
{_metric_card(702, 244, "ZERO GAMMA", _fmt_strike(metrics["zero_gamma"], 1), "#38bdf8")}
{_metric_card(910, 244, "PROVIDER CASES", f"{provider_scorecard['passed']}/{provider_scorecard['total']}", "#4ade80")}
{_metric_card(1118, 244, "FEED", health.upper(), _health_color(health))}

  <text x="78" y="334" class="mono panel-title">Strike Gamma Exposure Matrix</text>
  <text x="98" y="361" class="mono label">STRIKE</text>
  <text x="238" y="361" class="mono label">CALL VOL</text>
  <text x="368" y="361" class="mono label">PUT VOL</text>
  <text x="500" y="361" class="mono label">NET GEX</text>
  <text x="646" y="361" class="mono label">EXPOSURE</text>
{''.join(row_blocks)}

  <rect x="874" y="336" width="434" height="184" rx="10" fill="#0d141c" stroke="#263445"/>
  <text x="902" y="374" class="mono panel-title">GEX Proxy Regime Map</text>
  <rect x="902" y="402" width="348" height="26" rx="7" fill="url(#lane)" opacity="0.88"/>
  <line x1="1044" y1="391" x2="1044" y2="443" stroke="#38bdf8" stroke-width="4"/>
  <line x1="1176" y1="391" x2="1176" y2="443" stroke="#fbbf24" stroke-width="4" stroke-dasharray="7 6"/>
  <circle cx="1128" cy="415" r="7" fill="#f8fafc" filter="url(#glow)"/>
  <text x="902" y="470" class="mono small">Replay alerts: {int(replay_summary['alert_count'])}  |  Regime: {html.escape(replay_summary['regime_label'])}</text>
  <text x="902" y="500" class="mono small">Session change: {_signed(snapshot['session_change'], 2)}  |  Imbalance: {float(metrics['imbalance']):.2f}x</text>

  <rect x="874" y="548" width="434" height="180" rx="10" fill="#0d141c" stroke="#263445"/>
  <text x="902" y="586" class="mono panel-title">Demo Pack Outputs</text>
  <text x="902" y="624" class="mono small">color SVG preview</text>
  <text x="902" y="654" class="mono small">Textual terminal capture</text>
  <text x="902" y="684" class="mono small">snapshot JSON/Markdown</text>
  <text x="902" y="714" class="mono small">Replay Lab + Provider Fixture Lab</text>

  <text x="78" y="764" class="mono small">Local-first, credential-safe, replayable market-structure research for contributors.</text>
</svg>
"""


def demo_lab_readme(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "# gex-terminal Demo Lab",
        "",
        "This folder was generated from offline replay and fixture data. It is safe",
        "to share because it does not include live credentials or private provider",
        "payloads.",
        "",
        f"- Generated: `{manifest['generated_at']}`",
        f"- Replay session: `{manifest['replay_session']['name']}`",
        f"- Spot: `{summary['spot']:,.2f}`",
        f"- Gamma wall: `{summary['gamma_wall']:,.1f}`",
        f"- Zero gamma: `{summary['zero_gamma']:,.1f}`",
        f"- Net GEX: `{_money(summary['total_net_gex'])}`",
        f"- Provider fixture cases: `{manifest['provider_fixture_lab']['passed']}/{manifest['provider_fixture_lab']['total']}` passed",
        "",
        "## Artifacts",
        "",
        "| File | Type | Purpose |",
        "| --- | --- | --- |",
    ]
    for artifact in manifest["artifacts"]:
        lines.append(
            f"| [{artifact['path']}]({artifact['path']}) | "
            f"{artifact['kind']} | {artifact['description']} |"
        )
    lines.extend([
        "",
        "## Recreate",
        "",
        "```bash",
        f"gex-terminal demo-lab {manifest['output_dir']} --replay-session {manifest['replay_session']['name']}",
        "```",
    ])
    return "\n".join(lines) + "\n"


def _demo_lab_manifest(
    *,
    target: Path,
    session: ReplaySession,
    config: GexConfig,
    snapshot: dict[str, Any],
    replay_report: dict[str, Any],
    provider_report: dict[str, Any],
    artifacts: list[dict[str, str]],
) -> dict[str, Any]:
    metrics = snapshot["metrics"]
    replay_summary = replay_report["sessions"][0]["summary"]
    provider_scorecard = provider_report["scorecard"]
    return {
        "schema": DEMO_LAB_SCHEMA,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": _portable_output_dir(target),
        "replay_session": {
            "name": session.name,
            "label": session.label,
            "path": session.source_ref,
            "description": session.description,
        },
        "summary": {
            "symbol": snapshot["symbol"],
            "spot": float(snapshot["spot"]),
            "session_change": float(snapshot["session_change"]),
            "total_net_gex": float(metrics["total_net_gex"]),
            "gamma_wall": float(metrics["gamma_wall"]),
            "zero_gamma": float(metrics["zero_gamma"]),
            "call_wall": float(metrics["call_wall"]),
            "put_wall": float(metrics["put_wall"]),
            "imbalance": float(metrics["imbalance"]),
            "feed_health": snapshot.get("feed_quality", {}).get("health", "unknown"),
        },
        "inputs": {
            "days_to_expiry": float(config.days_to_expiry),
            "risk_free_rate": float(config.risk_free_rate),
            "contract_multiplier": int(config.contract_multiplier),
        },
        "replay_lab": {
            "schema": replay_report["schema"],
            "alert_count": int(replay_summary["alert_count"]),
            "regime": replay_summary["regime"],
            "regime_label": replay_summary["regime_label"],
        },
        "provider_fixture_lab": provider_scorecard,
        "artifacts": artifacts,
    }


def _demo_lab_config(config: GexConfig, session: ReplaySession) -> GexConfig:
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


def _write_artifact(
    root: Path,
    path: Path,
    kind: str,
    description: str,
    contents: str,
) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return _artifact(root, path, kind, description)


def _artifact(root: Path, path: Path, kind: str, description: str) -> dict[str, str]:
    return {
        "path": _relative_path(root, path),
        "kind": kind,
        "description": description,
    }


def _relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _portable_output_dir(path: Path) -> str:
    if path.is_absolute():
        return path.name
    return str(path)


def _preview_rows(snapshot: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    rows = sorted(
        snapshot["strikes"],
        key=lambda row: abs(float(row["net_gex"])),
        reverse=True,
    )
    return rows[:limit]


def _metric_card(x: int, y: int, label: str, value: str, color: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="180" height="66" rx="8" fill="#0d141c" stroke="#263445"/>
  <text x="{x + 16}" y="{y + 24}" class="mono label">{html.escape(label)}</text>
  <text x="{x + 16}" y="{y + 52}" class="mono value" fill="{color}">{html.escape(value)}</text>
"""


def _health_color(health: str) -> str:
    return {
        "healthy": "#4ade80",
        "simulated": "#38bdf8",
        "degraded": "#fbbf24",
        "stale": "#fbbf24",
        "entitlement": "#fb7185",
        "down": "#fb7185",
        "failed": "#fb7185",
    }.get(health, "#94a3b8")


def _symbols_with_target(symbols: tuple[str, ...], target_symbol: str) -> tuple[str, ...]:
    cleaned = tuple(symbol for symbol in symbols if symbol != target_symbol)
    return (target_symbol, *cleaned)[:4]


def _fmt_strike(value: float, decimals: int = 0) -> str:
    return f"{float(value):,.{decimals}f}"


def _signed(value: float, decimals: int = 1) -> str:
    return f"{float(value):+,.{decimals}f}"


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

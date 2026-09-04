"""Offline demo-pack generation for GitHub-ready project previews."""

from __future__ import annotations

import html
import json
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.demo_lab_receipt import (
    DEMO_LAB_SCHEMA,
    EVIDENCE_CEILING,
    PORTABLE_SOURCE_PATH,
    REVIEW_RECEIPT_PATH,
    REVIEW_RECEIPT_SCHEMA,
    inspect_portable_replay,
    load_portable_replay,
    stable_json_sha256,
    verify_demo_lab_pack,
    write_demo_lab_review_receipt,
)
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import dumps_normalized_message
from gex_terminal.model_comparison import (
    build_model_comparison_report,
    write_model_comparison_report,
)
from gex_terminal.model_profiles import (
    MODEL_PROFILE_VERSION,
    config_from_model_profile,
    default_model_profile,
)
from gex_terminal.overlays import write_tradingview_overlay
from gex_terminal.position_model_comparison import (
    build_position_model_comparison,
    write_position_model_comparison,
)
from gex_terminal.provider_fixture_lab import (
    build_provider_fixture_lab_report,
    write_provider_fixture_lab_report,
)
from gex_terminal.replay_catalog import (
    ReplaySession,
    config_for_replay_session,
    replay_session_for_name,
)
from gex_terminal.replay_lab import build_replay_lab_report, write_replay_lab_report
from gex_terminal.screenshot import export_app_screenshot_svg
from gex_terminal.snapshot import build_snapshot
from gex_terminal.snapshot_formats import write_snapshot_export
from gex_terminal.tui import GexTerminalApp


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
    session = replay_session_for_name(replay_session_name)
    return await _build_demo_lab_for_session(
        config,
        output_dir,
        session=session,
        screenshot_width=screenshot_width,
        screenshot_height=screenshot_height,
    )


async def _build_demo_lab_for_session(
    config: GexConfig,
    output_dir: str | Path,
    *,
    session: ReplaySession,
    screenshot_width: int,
    screenshot_height: int,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build one pack from a catalog or verified copied replay session."""
    target = Path(output_dir)
    if target.exists() and not target.is_dir():
        raise ValueError("Demo Lab output path must be a directory")
    if target.exists() and any(target.iterdir()):
        raise ValueError("Demo Lab output directory must be empty")
    target.mkdir(parents=True, exist_ok=True)

    lab_config = _demo_lab_config(config, session)
    messages = load_portable_replay(session.path)
    source_observations = inspect_portable_replay(messages, session=session)
    generated_at = generated_at or source_observations["last_event_time"] or (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    snapshot, consumer, _ = await compute_replay_snapshot(
        lab_config,
        messages=messages,
    )
    snapshot["feed_quality"] = consumer.feed_quality_snapshot()
    snapshot["demo_lab"] = {
        "replay_session": session.name,
        "replay_path": session.source_ref,
        "description": session.description,
        "source_reference": PORTABLE_SOURCE_PATH,
        "evidence_ceiling": EVIDENCE_CEILING,
    }
    snapshot["limitations"] = _research_limitations()

    replay_report = await build_replay_lab_report(
        lab_config,
        sessions=(session,),
    )
    replay_report["generated_at"] = generated_at
    provider_config = replace(
        lab_config,
        symbol="ES",
        symbols=("ES", *(symbol for symbol in lab_config.symbols if symbol != "ES"))[:4],
        contract_multiplier=50,
    )
    provider_report = await build_provider_fixture_lab_report(provider_config)
    provider_report["generated_at"] = generated_at
    model_comparison = build_model_comparison_report(snapshot)
    position_comparison = await build_position_model_comparison(
        {
            "as_of": source_observations["last_event_time"] or generated_at,
            "messages": messages,
        },
        config=lab_config,
    )
    position_comparison["generated_at"] = generated_at

    artifacts: list[dict[str, str]] = []
    portable_source = target / PORTABLE_SOURCE_PATH
    portable_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(session.path, portable_source)
    artifacts.append(_artifact(
        target,
        portable_source,
        "authorized-synthetic-source",
        "Portable normalized replay input bound by the review receipt.",
    ))
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
    artifacts.append(_artifact(
        target,
        write_model_comparison_report(
            model_comparison,
            str(target / "model-comparison.json"),
        ),
        "model-comparison",
        "Raw versus directionalized trade-volume comparison with explicit limits.",
    ))
    artifacts.append(_artifact(
        target,
        write_model_comparison_report(
            model_comparison,
            str(target / "model-comparison.md"),
        ),
        "model-comparison",
        "Human-readable raw versus directionalized comparison.",
    ))
    artifacts.append(_artifact(
        target,
        write_model_comparison_report(
            model_comparison,
            str(target / "model-comparison.csv"),
        ),
        "model-comparison",
        "Spreadsheet-friendly raw versus directionalized comparison.",
    ))
    artifacts.append(_artifact(
        target,
        write_position_model_comparison(
            position_comparison,
            target / "position-model-comparison.json",
        ),
        "position-model-comparison",
        "Separated OI, raw-volume, and directionalized proxy comparison.",
    ))
    artifacts.append(_artifact(
        target,
        write_position_model_comparison(
            position_comparison,
            target / "position-model-comparison.md",
        ),
        "position-model-comparison",
        "Human-readable separated position-model comparison and evidence limits.",
    ))
    artifacts.append(_artifact(
        target,
        write_position_model_comparison(
            position_comparison,
            target / "position-model-comparison.csv",
        ),
        "position-model-comparison",
        "Spreadsheet-friendly separated position-model comparison.",
    ))

    readme_path = target / "README.md"
    manifest_path = target / "manifest.json"
    receipt_path = target / REVIEW_RECEIPT_PATH
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
        _artifact(
            target,
            receipt_path,
            "review-receipt",
            "Integrity, model, runtime, quality, and evidence-ceiling receipt.",
        ),
        *artifacts,
    ]
    manifest = _demo_lab_manifest(
        session=session,
        config=lab_config,
        snapshot=snapshot,
        replay_report=replay_report,
        provider_report=provider_report,
        model_comparison=model_comparison,
        position_comparison=position_comparison,
        source_observations=source_observations,
        artifacts=artifacts,
        generated_at=generated_at,
    )
    readme_path.write_text(demo_lab_readme(manifest), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_demo_lab_review_receipt(
        target,
        generated_at=generated_at,
        session=session,
        config=lab_config,
        messages=messages,
        manifest=manifest,
        quality=_stable_quality_summary(snapshot, provider_report),
    )
    return manifest


def verify_demo_lab(directory: str | Path) -> dict[str, Any]:
    """Verify a portable pack through the versioned CLI artifact contract."""
    return verify_demo_lab_pack(directory)


async def reproduce_demo_lab(
    directory: str | Path,
    output_dir: str | Path,
    *,
    screenshot_width: int = 180,
    screenshot_height: int = 54,
) -> dict[str, Any]:
    """Rebuild a verified pack using only its copied input and bound profile."""
    source_root = Path(directory).resolve()
    target = Path(output_dir).resolve()
    try:
        target.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ValueError("Demo Lab reproduction output must be outside the source pack")

    original_verification = verify_demo_lab_pack(source_root)
    receipt = original_verification["receipt"]
    source = receipt["source"]
    model = receipt["model"]
    catalog_session = replay_session_for_name(source["session_name"])
    copied_session = replace(
        catalog_session,
        path=str(source_root / source["reference"]),
    )
    config = config_from_model_profile(model["profile"])
    manifest = await _build_demo_lab_for_session(
        config,
        target,
        session=copied_session,
        screenshot_width=screenshot_width,
        screenshot_height=screenshot_height,
        generated_at=receipt["generated_at"],
    )
    reproduced_verification = verify_demo_lab_pack(target)
    reproduced_receipt = reproduced_verification["receipt"]
    for field in ("sha256", "symbol", "contract_multiplier"):
        if reproduced_receipt["source"][field] != source[field]:
            raise ValueError(f"Demo Lab reproduction source mismatch: {field}")
    if reproduced_receipt["model"]["profile_sha256"] != model["profile_sha256"]:
        raise ValueError("Demo Lab reproduction model profile did not match")
    if reproduced_receipt["content"] != receipt["content"]:
        changed = sorted(
            reference
            for reference in set(reproduced_receipt["content"]) | set(receipt["content"])
            if reproduced_receipt["content"].get(reference)
            != receipt["content"].get(reference)
        )
        raise ValueError(
            "Demo Lab reproduction decision content mismatch: " + ", ".join(changed)
        )
    return {
        "manifest": manifest,
        "verification": reproduced_verification,
        "reproduction": {
            "matched": True,
            "source_content_sha256": source["sha256"],
            "model_profile_sha256": model["profile_sha256"],
            "predictive_validity": "unmeasured",
        },
    }


async def compute_replay_snapshot(
    config: GexConfig,
    *,
    messages: Iterable[Mapping[str, Any]] | None = None,
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
    consumer.mark_connected()
    loaded_messages = (
        list(messages)
        if messages is not None
        else list(ReplayAdapter(consumer, config.replay_path, delay_seconds=0.0)._load_messages())
    )
    for message in loaded_messages:
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
        timestamp=(
            consumer.market_time.isoformat().replace("+00:00", "Z")
            if consumer.market_time is not None
            else None
        ),
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
    comparison = manifest["position_model_comparison"]
    exact_time_note = (
        "Exact schema-v2 event, received, and expiry times plus contract "
        "multiplier metadata are preserved in `inputs/replay.jsonl`."
        if manifest["source"]["normalized_schema_versions"] == [2]
        and manifest["source"]["missing_event_time_count"] == 0
        and manifest["source"]["missing_received_time_count"] == 0
        and manifest["source"]["missing_expiry_time_count"] == 0
        else (
            "The copied input preserves its declared normalized schema and any "
            "event, received, expiry, or multiplier metadata supplied by that fixture."
        )
    )
    lines = [
        "# gex-terminal Demo Lab",
        "",
        "This self-contained folder was generated from an authorized synthetic",
        "replay. It contains no live credentials or private provider payloads.",
        "",
        f"- Generated: `{manifest['generated_at']}`",
        f"- Replay session: `{manifest['replay_session']['name']}`",
        f"- Instrument: `{summary['symbol']}` (multiplier `{manifest['inputs']['contract_multiplier']}`)",
        f"- Source cutoff: `{manifest['source']['as_of']}`",
        "- Predictive validity: `unmeasured`",
        "- Live provider certified: `false`",
        "",
        "## Today",
        "",
        "Review the final synthetic market-structure snapshot:",
        "",
        f"- Spot: `{summary['spot']:,.2f}`",
        f"- Gamma wall: `{summary['gamma_wall']:,.1f}`",
        f"- Zero gamma: `{summary['zero_gamma']:,.1f}`",
        f"- Net GEX: `{_money(summary['total_net_gex'])}`",
        f"- Provider fixture cases: `{manifest['provider_fixture_lab']['passed']}/{manifest['provider_fixture_lab']['total']}` passed",
        "",
        "## Explain",
        "",
        "The snapshot uses the raw trade-volume proxy selected by the existing",
        f"consumer contract. {exact_time_note} The receipt binds the model profile",
        "and application/runtime versions used to produce the result.",
        "",
        "## Compare",
        "",
        "Open interest, raw trade volume, and directionalized trade volume are",
        "separate proxy views. They are never combined into one exposure number.",
        "",
        "| Model | Status | Total Net GEX | Gamma Wall | Direction Coverage |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for name in (
        "open_interest",
        "raw_trade_volume",
        "directionalized_trade_volume",
    ):
        model = comparison["models"][name]
        lines.append(
            f"| `{name}` | `{model.get('status', 'unavailable')}` | "
            f"{_optional_money(model.get('total_net_gex'))} | "
            f"{_optional_number(model.get('gamma_wall'))} | "
            f"{_optional_percent(model.get('directional_coverage'))} |"
        )
    lines.extend([
        "",
        "## Replay",
        "",
        "Run the copied input directly from this folder:",
        "",
        "```bash",
        f"gex-terminal --replay {PORTABLE_SOURCE_PATH} --symbol {summary['symbol']} --multiplier {manifest['inputs']['contract_multiplier']} --export replayed-snapshot.json",
        "```",
        "",
        "Reproduce the complete pack into a new directory using only this copy:",
        "",
        "```bash",
        "gex-terminal demo-lab reproduce . ../reproduced-demo-lab",
        "```",
        "",
        "## Review",
        "",
        "Verify source, model, runtime, decision content, and every declared artifact:",
        "",
        "```bash",
        "gex-terminal demo-lab verify .",
        "```",
        "",
        "The review receipt intentionally omits named ephemeral elapsed-time and",
        "latency fields from semantic identity, while raw artifact hashes still bind",
        "the files in this exact pack. Generation time remains bound.",
        "",
        "## Limits",
        "",
        "- Position models may not be summed.",
        "- Participant identity and opening/closing state are unobserved.",
        "- OI publication timing is only the event time supplied by this fixture.",
        "- Predictive validity is unmeasured and live-provider certification is false.",
        f"- Evidence ceiling: {manifest['evidence_ceiling']}",
        "- The CLI and versioned artifacts are the contract; Python helpers are experimental.",
        "",
        "## Artifacts",
        "",
        "| File | Type | Purpose |",
        "| --- | --- | --- |",
    ])
    for artifact in manifest["artifacts"]:
        lines.append(
            f"| [{artifact['path']}]({artifact['path']}) | "
            f"{artifact['kind']} | {artifact['description']} |"
        )
    lines.extend([
        "",
        "To generate a fresh catalog-backed copy instead of reproducing this exact",
        "receipt, run:",
        "",
        "```bash",
        f"gex-terminal demo-lab NEW_DIRECTORY --replay-session {manifest['replay_session']['name']}",
        "```",
    ])
    return "\n".join(lines) + "\n"


def _demo_lab_manifest(
    *,
    session: ReplaySession,
    config: GexConfig,
    snapshot: dict[str, Any],
    replay_report: dict[str, Any],
    provider_report: dict[str, Any],
    model_comparison: dict[str, Any],
    position_comparison: dict[str, Any],
    source_observations: dict[str, Any],
    artifacts: list[dict[str, str]],
    generated_at: str,
) -> dict[str, Any]:
    metrics = snapshot["metrics"]
    replay_summary = replay_report["sessions"][0]["summary"]
    provider_scorecard = provider_report["scorecard"]
    profile = default_model_profile(config)
    return {
        "schema": DEMO_LAB_SCHEMA,
        "generated_at": generated_at,
        "output_dir": ".",
        "replay_session": {
            "name": session.name,
            "label": session.label,
            "path": session.source_ref,
            "description": session.description,
            "symbol": session.symbol,
            "contract_multiplier": session.contract_multiplier,
        },
        "source": {
            "reference": PORTABLE_SOURCE_PATH,
            "catalog_reference": session.source_ref,
            "source_kind": session.source_kind,
            "rights_status": session.rights_status,
            "redistributable": session.redistributable,
            "synthetic": session.source_kind == "synthetic_fixture",
            "live_data": False,
            "normalized_schema_versions": source_observations[
                "normalized_schema_versions"
            ],
            "event_count": source_observations["event_count"],
            "as_of": source_observations["last_event_time"],
            "missing_event_time_count": source_observations[
                "missing_event_time_count"
            ],
            "missing_received_time_count": source_observations[
                "missing_received_time_count"
            ],
            "missing_expiry_time_count": source_observations[
                "missing_expiry_time_count"
            ],
            "position_sources": source_observations["position_sources"],
            "direction_sources": source_observations["direction_sources"],
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
            "model_version": MODEL_PROFILE_VERSION,
            "model_profile_sha256": stable_json_sha256(profile),
        },
        "replay_lab": {
            "schema": replay_report["schema"],
            "alert_count": int(replay_summary["alert_count"]),
            "regime": replay_summary["regime"],
            "regime_label": replay_summary["regime_label"],
        },
        "model_comparison": {
            "schema": model_comparison["schema"],
            "status": model_comparison["result"]["status"],
            "directional_coverage": model_comparison["metrics"][
                "directional_coverage"
            ],
            "predictive_validity": "unmeasured",
        },
        "position_model_comparison": {
            "schema": position_comparison["schema"],
            "status": position_comparison["result"]["status"],
            "models": position_comparison["models"],
            "models_may_not_be_summed": True,
            "predictive_validity": "unmeasured",
        },
        "provider_fixture_lab": provider_scorecard,
        "review_receipt": {
            "schema": REVIEW_RECEIPT_SCHEMA,
            "path": REVIEW_RECEIPT_PATH,
        },
        "limitations": _research_limitations(),
        "evidence_ceiling": EVIDENCE_CEILING,
        "python_interface": "experimental",
        "artifacts": artifacts,
    }


def _research_limitations() -> dict[str, Any]:
    return {
        "position_models_may_not_be_summed": True,
        "participant_classification": "unobserved",
        "opening_closing_classification": "unobserved",
        "oi_publication_lag": "represented_only_by_supplied_event_time",
        "predictive_validity": "unmeasured",
        "live_provider_certified": False,
        "authenticity": "unkeyed_hashes_only",
    }


def _stable_quality_summary(
    snapshot: Mapping[str, Any],
    provider_report: Mapping[str, Any],
) -> dict[str, Any]:
    feed = snapshot.get("feed_quality", {})
    stable_feed_fields = (
        "status",
        "data_mode",
        "connection_state",
        "health",
        "message_count",
        "malformed_count",
        "dropped_count",
        "entitlement_error_count",
        "frame_count",
        "parse_error_count",
        "reconnect_count",
        "subscribed_symbol_count",
        "subscription_status",
        "stale_after_seconds",
        "stale",
        "notes",
        "duplicate_message_count",
        "cumulative_reset_count",
        "fallback_iv_tick_count",
    )
    return {
        "replay": {
            key: feed[key]
            for key in stable_feed_fields
            if key in feed
        },
        "provider_fixture_lab": dict(provider_report["scorecard"]),
        "ephemeral_runtime_fields_bound": False,
    }


def _demo_lab_config(config: GexConfig, session: ReplaySession) -> GexConfig:
    replay_config = config_for_replay_session(config, session)
    return replace(
        replay_config,
        replay_delay_seconds=0.0,
        replay_clock="none",
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
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("Demo Lab artifacts must stay inside the output directory") from exc


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


def _optional_money(value: Any) -> str:
    return "--" if value is None else _money(float(value))


def _optional_number(value: Any) -> str:
    return "--" if value is None else f"{float(value):,.1f}"


def _optional_percent(value: Any) -> str:
    return "--" if value is None else f"{float(value):.1%}"

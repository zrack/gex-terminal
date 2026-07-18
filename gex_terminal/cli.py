import asyncio
import argparse
import contextlib
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from gex_terminal.adapters.registry import (
    adapter_info,
    available_provider_names,
    build_market_data_adapter,
    effective_provider,
)
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.fixture_validator import (
    format_fixture_validation_report,
    validate_fixture,
)
from gex_terminal.market_data_adapter import AdapterConfigurationError
from gex_terminal.offline_quality import apply_quality_scenario, quality_scenario_names
from gex_terminal.overlays import write_tradingview_overlay
from gex_terminal.replay_catalog import (
    bundled_replay_sessions,
    replay_session_for_name,
    replay_session_names,
)
from gex_terminal.replay_lab import build_replay_lab_report, write_replay_lab_report
from gex_terminal.sensitivity import build_sensitivity_report, write_sensitivity_report
from gex_terminal.snapshot import build_snapshot
from gex_terminal.snapshot_formats import write_snapshot_export
from gex_terminal.tui import GexTerminalApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    args = parse_args()

    if args.command == "validate-fixture":
        validate_fixture_command(args.command_path)
        return

    if args.command == "list-replays":
        print_replay_sessions()
        return

    if args.command == "replay-lab":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await export_replay_lab(
            config=config,
            output_path=args.command_path or "replay_lab.md",
            session_names=(args.replay_session,) if args.replay_session else None,
        )
        return

    config = apply_cli_overrides(GexConfig.from_env(), args)
    validate_data_mode(config.data_mode)

    if args.providers:
        print_provider_summary()
        return

    validate_provider(config)

    if args.screenshot:
        await export_demo_screenshot(
            config=config,
            output_path=args.screenshot,
            width=args.screenshot_width,
            height=args.screenshot_height,
            quality_scenario=args.quality_scenario,
        )
        return

    if args.export:
        await export_snapshot(
            config=config,
            output_path=args.export,
            quality_scenario=args.quality_scenario,
        )
        return

    if args.tradingview_overlay:
        await export_tradingview_overlay(
            config=config,
            output_path=args.tradingview_overlay,
            quality_scenario=args.quality_scenario,
        )
        return

    if args.sensitivity:
        await export_sensitivity(
            config=config,
            output_path=args.sensitivity,
            quality_scenario=args.quality_scenario,
        )
        return

    math_engine = IntradayGexEngine(multiplier=config.contract_multiplier)
    
    state_consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode=config.data_mode,
        stale_after_seconds=config.stale_after_seconds,
    )
    
    stream_task = None
    calc_task = None
    
    if config.data_mode == "demo":
        await seed_demo_session(state_consumer)
        if args.quality_scenario:
            await apply_quality_scenario(state_consumer, args.quality_scenario)
    else:
        try:
            data_adapter = build_market_data_adapter(state_consumer, config)
        except (AdapterConfigurationError, ModuleNotFoundError, ValueError) as exc:
            raise SystemExit(
                "\n".join((
                    f"{effective_provider(config)} provider is not ready: {exc}",
                    "Install dependencies with: pip install -e .",
                    "Or start demo mode with: gex-terminal --demo",
                ))
            ) from exc

        stream_task = asyncio.create_task(data_adapter.stream_market_data())
        if config.data_mode == "live":
            calc_task = asyncio.create_task(
                state_consumer.continuous_calculation_loop(
                    interval_seconds=config.refresh_interval_seconds * 2,
                    days_to_expiry=config.days_to_expiry,
                )
            )
    
    app = GexTerminalApp(consumer=state_consumer, config=config)
    try:
        await app.run_async()
    finally:
        for task in (stream_task, calc_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task


async def seed_demo_session(consumer: StatefulGexConsumer) -> None:
    consumer.current_spot = 5943.25
    consumer.session_open = 5904.50
    seed_rows: Iterable[tuple[int, int, int, float]] = (
        (5875, 2104, 8992, 0.18),
        (5900, 4781, 7406, 0.16),
        (5915, 5229, 5312, 0.15),
        (5925, 7925, 4812, 0.14),
        (5950, 13480, 3044, 0.13),
        (5975, 9441, 2105, 0.13),
        (6000, 10872, 1624, 0.14),
        (6025, 5128, 938, 0.15),
        (6050, 2775, 611, 0.16),
    )

    for strike, call_volume, put_volume, iv in seed_rows:
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick",
            "strike": strike,
            "option_type": "C",
            "volume": call_volume,
            "iv": iv,
        }))
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick",
            "strike": strike,
            "option_type": "P",
            "volume": put_volume,
            "iv": iv,
        }))


async def export_demo_screenshot(
    config: GexConfig,
    output_path: str,
    width: int,
    height: int,
    quality_scenario: str | None = None,
) -> None:
    render_mode = "replay" if config.data_mode == "replay" else "demo"
    render_config = GexConfig(
        symbol=config.symbol,
        symbols=config.symbols,
        data_mode=render_mode,
        data_provider=config.data_provider,
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        days_to_expiry=config.days_to_expiry,
        refresh_interval_seconds=config.refresh_interval_seconds,
        stale_after_seconds=config.stale_after_seconds,
        replay_path=config.replay_path,
        replay_delay_seconds=0.0,
        tradovate_environment=config.tradovate_environment,
    )
    math_engine = IntradayGexEngine(multiplier=render_config.contract_multiplier)
    consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=render_config.symbol,
        risk_free_rate=render_config.risk_free_rate,
        data_mode=render_config.data_mode,
        stale_after_seconds=render_config.stale_after_seconds,
    )
    if render_config.data_mode == "replay":
        adapter = build_market_data_adapter(consumer, render_config)
        await adapter.stream_market_data()
    else:
        await seed_demo_session(consumer)

    if quality_scenario:
        await apply_quality_scenario(consumer, quality_scenario)

    app = GexTerminalApp(consumer=consumer, config=render_config)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause(0.2)
        await app.refresh_terminal_data()
        await pilot.pause(0.2)
        title = "GEX Terminal Replay Lab" if render_mode == "replay" else "GEX Terminal Actual"
        svg = app.export_screenshot(title=title)

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(svg, encoding="utf-8")
    print(f"Saved screenshot to {target}")


async def export_replay_lab(
    config: GexConfig,
    output_path: str,
    session_names: Iterable[str] | None = None,
) -> None:
    """Run the offline replay research lab and write .json, .csv, or .md."""
    report = await build_replay_lab_report(config, session_names=session_names)
    try:
        target = write_replay_lab_report(report, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Saved replay lab report to {target}")


async def export_snapshot(
    config: GexConfig,
    output_path: str,
    quality_scenario: str | None = None,
) -> None:
    """Compute one snapshot and write it to JSON, CSV, or Markdown."""
    snapshot, _, _ = await compute_snapshot(config, quality_scenario=quality_scenario)
    try:
        target = write_snapshot_export(snapshot, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Saved snapshot to {target}")


async def export_tradingview_overlay(
    config: GexConfig,
    output_path: str,
    quality_scenario: str | None = None,
) -> None:
    """Compute one snapshot and write chart-overlay levels to JSON or CSV."""
    snapshot, _, _ = await compute_snapshot(config, quality_scenario=quality_scenario)
    try:
        target = write_tradingview_overlay(snapshot, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Saved TradingView overlay to {target}")


async def export_sensitivity(
    config: GexConfig,
    output_path: str,
    quality_scenario: str | None = None,
) -> None:
    """Compute model-sensitivity scenarios and write JSON, CSV, or Markdown."""
    _, consumer, _ = await compute_snapshot(config, quality_scenario=quality_scenario)
    report = build_sensitivity_report(
        spot=consumer.current_spot,
        chain_state=consumer.chain_state,
        days_to_expiry=config.days_to_expiry,
        risk_free_rate=config.risk_free_rate,
        contract_multiplier=config.contract_multiplier,
    )
    try:
        target = write_sensitivity_report(report, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Saved sensitivity report to {target}")


async def compute_demo_snapshot(config: GexConfig) -> dict:
    snapshot, _, _ = await compute_snapshot(config)
    return snapshot


async def compute_snapshot(
    config: GexConfig,
    quality_scenario: str | None = None,
) -> tuple[dict, StatefulGexConsumer, dict]:
    math_engine = IntradayGexEngine(multiplier=config.contract_multiplier)
    consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode=config.data_mode,
        stale_after_seconds=config.stale_after_seconds,
    )

    if config.data_mode == "replay":
        replay_config = replace(config, replay_delay_seconds=0.0)
        adapter = build_market_data_adapter(consumer, replay_config)
        await adapter.stream_market_data()
    elif config.data_mode == "demo":
        await seed_demo_session(consumer)
    else:
        raise SystemExit("Non-interactive exports currently support demo or replay mode only.")

    if quality_scenario:
        await apply_quality_scenario(consumer, quality_scenario)

    data = await consumer.process_latest_snapshot(days_to_expiry=config.days_to_expiry)
    if "error" in data:
        raise SystemExit(f"Cannot export snapshot: {data['error']}")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Intraday GEX imbalance terminal",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("validate-fixture", "list-replays", "replay-lab"),
        help="Optional utility command.",
    )
    parser.add_argument(
        "command_path",
        nargs="?",
        help="Path argument for utility commands such as validate-fixture or replay-lab.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--demo",
        action="store_true",
        help="Start with seeded demo data instead of live market data.",
    )
    mode_group.add_argument(
        "--mode",
        choices=("demo", "replay", "live"),
        help="Runtime data mode. Overrides GEX_DATA_MODE.",
    )
    parser.add_argument(
        "--symbol",
        help="Target underlying symbol, for example ES or NQ. Overrides GEX_SYMBOL.",
    )
    parser.add_argument(
        "--provider",
        choices=available_provider_names(),
        help="Market-data provider for live mode. Overrides GEX_DATA_PROVIDER.",
    )
    parser.add_argument(
        "--providers",
        action="store_true",
        help="List available market-data providers and exit.",
    )
    parser.add_argument(
        "--multiplier",
        type=int,
        help="Contract multiplier. Overrides GEX_CONTRACT_MULTIPLIER.",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        help="UI refresh interval in seconds. Overrides GEX_REFRESH_INTERVAL_SECONDS.",
    )
    parser.add_argument(
        "--replay",
        metavar="PATH",
        help="Replay normalized JSONL market data from PATH. Sets mode to replay.",
    )
    parser.add_argument(
        "--replay-session",
        choices=replay_session_names(),
        help="Replay one bundled synthetic research session by name.",
    )
    parser.add_argument(
        "--quality-scenario",
        choices=quality_scenario_names(),
        help="Apply an offline provider-health simulation to demo/export workflows.",
    )
    parser.add_argument(
        "--replay-delay",
        type=float,
        help="Delay between replay messages in seconds. Overrides GEX_REPLAY_DELAY_SECONDS.",
    )
    parser.add_argument(
        "--screenshot",
        metavar="PATH",
        help="Export a real Textual SVG screenshot using seeded demo data, then exit.",
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        help="Compute one GEX snapshot and write .json, .csv, or .md, then exit.",
    )
    parser.add_argument(
        "--tradingview-overlay",
        metavar="PATH",
        help="Compute one GEX snapshot and write TradingView overlay levels to .json or .csv.",
    )
    parser.add_argument(
        "--sensitivity",
        metavar="PATH",
        help="Compute a model-sensitivity report and write .json, .csv, or .md, then exit.",
    )
    parser.add_argument(
        "--screenshot-width",
        type=int,
        default=180,
        help="Terminal columns for --screenshot export. Default: 180.",
    )
    parser.add_argument(
        "--screenshot-height",
        type=int,
        default=54,
        help="Terminal rows for --screenshot export. Default: 54.",
    )
    return parser.parse_args()


def apply_cli_overrides(config: GexConfig, args: argparse.Namespace) -> GexConfig:
    updates = {}

    if args.demo:
        updates["data_mode"] = "demo"
    elif args.mode:
        updates["data_mode"] = args.mode

    if args.symbol:
        symbol = args.symbol.upper()
        updates["symbol"] = symbol
        updates["symbols"] = _symbols_with_target(config.symbols, symbol)

    if args.provider:
        updates["data_provider"] = args.provider

    if args.multiplier is not None:
        updates["contract_multiplier"] = args.multiplier

    if args.refresh is not None:
        updates["refresh_interval_seconds"] = args.refresh

    if args.replay:
        updates["data_mode"] = "replay"
        updates["replay_path"] = args.replay

    if args.replay_session:
        session = replay_session_for_name(args.replay_session)
        updates["data_mode"] = "replay"
        updates["replay_path"] = session.path

    if args.replay_delay is not None:
        updates["replay_delay_seconds"] = args.replay_delay

    return replace(config, **updates) if updates else config


def _symbols_with_target(symbols: tuple[str, ...], target_symbol: str) -> tuple[str, ...]:
    cleaned = tuple(symbol for symbol in symbols if symbol != target_symbol)
    return (target_symbol, *cleaned)[:4]


def validate_data_mode(data_mode: str) -> None:
    supported_modes = {"demo", "replay", "live"}
    if data_mode not in supported_modes:
        raise SystemExit(
            f"Unsupported GEX_DATA_MODE '{data_mode}'. Expected one of: demo, replay, live"
        )


def validate_provider(config: GexConfig) -> None:
    if effective_provider(config) not in available_provider_names():
        raise SystemExit(
            f"Unsupported GEX_DATA_PROVIDER '{config.data_provider}'. "
            f"Expected one of: {', '.join(available_provider_names())}"
        )


def print_provider_summary() -> None:
    for provider in available_provider_names():
        info = adapter_info(provider)
        print(f"{info.name:10} {info.status:9} {info.label} - {info.notes}")


def print_replay_sessions() -> None:
    for session in bundled_replay_sessions():
        print(f"{session.name:24} {session.path:48} {session.description}")


def validate_fixture_command(path: str | None) -> None:
    if not path:
        raise SystemExit("Usage: gex-terminal validate-fixture PATH")
    report = validate_fixture(path)
    print(format_fixture_validation_report(report))
    if not report.ok:
        raise SystemExit(1)


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()

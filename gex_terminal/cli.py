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
from gex_terminal.market_data_adapter import AdapterConfigurationError
from gex_terminal.tui import GexTerminalApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    args = parse_args()
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
) -> None:
    demo_config = GexConfig(
        symbol=config.symbol,
        symbols=config.symbols,
        data_mode="demo",
        data_provider=config.data_provider,
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        days_to_expiry=config.days_to_expiry,
        refresh_interval_seconds=config.refresh_interval_seconds,
        stale_after_seconds=config.stale_after_seconds,
        replay_path=config.replay_path,
        replay_delay_seconds=config.replay_delay_seconds,
        tradovate_environment=config.tradovate_environment,
    )
    math_engine = IntradayGexEngine(multiplier=demo_config.contract_multiplier)
    consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=demo_config.symbol,
        risk_free_rate=demo_config.risk_free_rate,
        data_mode=demo_config.data_mode,
        stale_after_seconds=demo_config.stale_after_seconds,
    )
    await seed_demo_session(consumer)

    app = GexTerminalApp(consumer=consumer, config=demo_config)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause(0.2)
        await app.refresh_terminal_data()
        await pilot.pause(0.2)
        svg = app.export_screenshot(title="GEX Terminal Actual")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(svg, encoding="utf-8")
    print(f"Saved screenshot to {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Intraday GEX imbalance terminal",
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


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()

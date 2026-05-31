import asyncio
import argparse
import contextlib
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from gex_config import GexConfig
from gex_engine import IntradayGexEngine
from gex_consumer import StatefulGexConsumer
from gex_terminal import GexTerminalApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    args = parse_args()
    config = apply_cli_overrides(GexConfig.from_env(), args)

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
            from tradovate_adapter import TradovateAdapter
        except ModuleNotFoundError as exc:
            missing_package = exc.name or "live market-data dependency"
            raise SystemExit(
                "\n".join((
                    f"Live mode requires the missing package: {missing_package}",
                    "Install live dependencies with: pip install -r requirements.txt",
                    "Or start demo mode with: python3 main.py --demo",
                ))
            ) from exc

        data_adapter = TradovateAdapter(
            state_consumer,
            target_underlying=config.symbol,
            environment=config.tradovate_environment,
        )
        stream_task = asyncio.create_task(data_adapter.stream_market_data())
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
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        days_to_expiry=config.days_to_expiry,
        refresh_interval_seconds=config.refresh_interval_seconds,
        stale_after_seconds=config.stale_after_seconds,
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
        choices=("demo", "live"),
        help="Runtime data mode. Overrides GEX_DATA_MODE.",
    )
    parser.add_argument(
        "--symbol",
        help="Target underlying symbol, for example ES or NQ. Overrides GEX_SYMBOL.",
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

    if args.multiplier is not None:
        updates["contract_multiplier"] = args.multiplier

    if args.refresh is not None:
        updates["refresh_interval_seconds"] = args.refresh

    return replace(config, **updates) if updates else config


def _symbols_with_target(symbols: tuple[str, ...], target_symbol: str) -> tuple[str, ...]:
    cleaned = tuple(symbol for symbol in symbols if symbol != target_symbol)
    return (target_symbol, *cleaned)[:4]


if __name__ == "__main__":
    asyncio.run(main())

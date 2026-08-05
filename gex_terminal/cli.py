import asyncio
import argparse
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from gex_terminal import __version__

from gex_terminal.adapters.registry import (
    adapter_info,
    available_provider_names,
    build_market_data_adapter,
    effective_provider,
)
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.demo_lab import (
    DEFAULT_DEMO_SESSION,
    build_demo_lab,
)
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.fixture_validator import (
    format_fixture_validation_report,
    validate_fixture,
)
from gex_terminal.market_data_adapter import AdapterConfigurationError
from gex_terminal.model_evidence import (
    build_model_evidence_report,
    write_model_evidence_report,
)
from gex_terminal.offline_quality import apply_quality_scenario, quality_scenario_names
from gex_terminal.overlays import write_tradingview_overlay
from gex_terminal.provider_injector import (
    INJECTION_FORMATS,
    inject_provider_fixture,
    provider_injection_summary,
)
from gex_terminal.provider_fixture_lab import (
    build_provider_fixture_lab_report,
    provider_fixture_case_for_name,
    write_provider_fixture_lab_report,
)
from gex_terminal.replay_catalog import (
    bundled_replay_sessions,
    replay_session_for_name,
    replay_session_names,
)
from gex_terminal.replay_lab import build_replay_lab_report, write_replay_lab_report
from gex_terminal.research_journal import (
    DEFAULT_JOURNAL_DIR,
    add_journal_entry,
    build_journal_report,
    compare_journal_entries,
    format_journal_add_summary,
    format_journal_comparison,
    format_journal_list,
    load_journal_entries,
    write_journal_report,
)
from gex_terminal.screenshot import export_app_screenshot_svg
from gex_terminal.session_store import (
    DEFAULT_SESSION_STORE_DIR,
    build_session_store_report,
    format_captured_session_list,
    format_session_record_list,
    format_session_save_summary,
    load_captured_sessions,
    load_session_records,
    save_session_snapshot,
    write_session_store_report,
)
from gex_terminal.sensitivity import build_sensitivity_report, write_sensitivity_report
from gex_terminal.session_capture import (
    CapturedSessionWriter,
    RecordingConsumerProxy,
    default_capture_path,
)
from gex_terminal.snapshot import build_snapshot
from gex_terminal.snapshot_formats import write_snapshot_export
from gex_terminal.tui import GexTerminalApp
from gex_terminal.tradovate_certification import (
    build_tradovate_certification_report,
    write_tradovate_certification_report,
)

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

    if args.command == "demo-lab":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await export_demo_lab(config, args)
        return

    if args.command == "journal":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await journal_command(config, args)
        return

    if args.command == "session-store":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await session_store_command(config, args)
        return

    if args.command == "fixture-lab":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await export_provider_fixture_lab(
            config=config,
            output_path=args.command_path or "provider_fixture_lab.md",
        )
        return

    if args.command == "inject-provider":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await inject_provider_command(config, args)
        return

    if args.command == "tradovate-certify":
        config = apply_cli_overrides(GexConfig.from_env(), args)
        await tradovate_certification_command(config, args)
        return

    if args.command == "model-evidence":
        model_evidence_command(args.command_path or "model_evidence.json")
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
            screenshot_view=args.screenshot_view,
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
        expiry_filter=config.expiry_filter,
    )
    
    stream_task = None
    calc_task = None
    capture_writer = None
    adapter_consumer = state_consumer

    if (args.record_session or args.capture_path) and config.data_mode != "demo":
        capture_target = Path(args.capture_path) if args.capture_path else default_capture_path(
            DEFAULT_SESSION_STORE_DIR,
            symbol=config.symbol,
            provider=effective_provider(config),
        )
        capture_writer = CapturedSessionWriter(
            capture_target,
            source={
                "mode": config.data_mode,
                "provider": effective_provider(config),
                "environment": (
                    config.tradovate_environment
                    if effective_provider(config) == "tradovate"
                    else None
                ),
                "symbol": config.symbol,
            },
            model_inputs={
                "days_to_expiry": config.days_to_expiry,
                "risk_free_rate": config.risk_free_rate,
                "contract_multiplier": config.contract_multiplier,
                "expiry_filter": config.expiry_filter,
            },
            label=args.capture_label,
        )
        await capture_writer.start()
        adapter_consumer = RecordingConsumerProxy(state_consumer, capture_writer)
    elif args.record_session or args.capture_path:
        raise SystemExit("Session capture requires replay or live mode, not seeded demo mode.")
    
    if config.data_mode == "demo":
        await seed_demo_session(state_consumer)
        if args.quality_scenario:
            await apply_quality_scenario(state_consumer, args.quality_scenario)
    else:
        try:
            data_adapter = build_market_data_adapter(adapter_consumer, config)
        except (AdapterConfigurationError, ModuleNotFoundError, ValueError) as exc:
            if capture_writer:
                await capture_writer.abort(f"adapter configuration failed: {type(exc).__name__}")
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
    
    app = GexTerminalApp(
        consumer=state_consumer,
        config=config,
        allow_replay_switching=capture_writer is None,
    )
    app_failed = False
    try:
        await app.run_async()
    except BaseException:
        app_failed = True
        raise
    finally:
        task_errors = await _shutdown_runtime_tasks(
            stream_task,
            calc_task,
            capture_writer,
            state_consumer,
            run_failed=app_failed,
        )
        if task_errors and not app_failed:
            raise task_errors[0]


async def _shutdown_runtime_tasks(
    stream_task: asyncio.Task | None,
    calc_task: asyncio.Task | None,
    capture_writer: CapturedSessionWriter | None,
    state_consumer: StatefulGexConsumer,
    *,
    run_failed: bool,
) -> list[Exception]:
    """Settle background tasks before completing or aborting a capture."""
    task_errors: list[Exception] = []
    for task in (stream_task, calc_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                task_errors.append(exc)

    if capture_writer:
        if run_failed or task_errors:
            partial = await capture_writer.abort("runtime ended with an exception")
            print(f"Retained incomplete session capture at {partial}")
        else:
            target = await capture_writer.finalize(
                feed_quality=state_consumer.feed_quality_snapshot()
            )
            print(f"Saved captured session to {target}")
    return task_errors


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
    screenshot_view: str = "terminal",
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
        expiry_filter=config.expiry_filter,
        replay_clock="none",
    )
    math_engine = IntradayGexEngine(multiplier=render_config.contract_multiplier)
    consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=render_config.symbol,
        risk_free_rate=render_config.risk_free_rate,
        data_mode=render_config.data_mode,
        stale_after_seconds=render_config.stale_after_seconds,
        expiry_filter=render_config.expiry_filter,
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
        if screenshot_view == "replay-browser":
            await app.action_cycle_replay_session()
        await pilot.pause(0.2)
        if screenshot_view == "replay-browser":
            title = "GEX Terminal Replay Browser"
        else:
            title = "GEX Terminal Replay Lab" if render_mode == "replay" else "GEX Terminal Actual"
        svg = export_app_screenshot_svg(app, title=title)

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


async def export_provider_fixture_lab(config: GexConfig, output_path: str) -> None:
    """Run bundled provider-shaped fixtures and write .json, .csv, or .md."""
    report = await build_provider_fixture_lab_report(config)
    try:
        target = write_provider_fixture_lab_report(report, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    scorecard = report["scorecard"]
    print(
        "Saved provider fixture lab report to "
        f"{target} ({scorecard['passed']}/{scorecard['total']} passed, "
        f"{scorecard['degraded']} degraded)"
    )
    if scorecard["failed"]:
        raise SystemExit(1)


async def export_demo_lab(config: GexConfig, args: argparse.Namespace) -> None:
    """Generate the offline demo pack for GitHub and contributor onboarding."""
    output_dir = args.command_path or "demo_lab"
    session_name = args.replay_session or DEFAULT_DEMO_SESSION
    try:
        manifest = await build_demo_lab(
            config,
            output_dir,
            replay_session_name=session_name,
            screenshot_width=args.screenshot_width,
            screenshot_height=args.screenshot_height,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Saved demo lab pack to {output_dir} "
        f"({len(manifest['artifacts'])} artifacts, replay {manifest['replay_session']['name']})"
    )


async def journal_command(config: GexConfig, args: argparse.Namespace) -> None:
    """Handle local historical research journal commands."""
    action = args.command_path or "list"
    journal_dir = args.journal_dir
    if action == "add":
        try:
            entry = await add_journal_entry(
                config,
                journal_dir,
                replay_session_name=(
                    None
                    if args.captured_session
                    else args.replay_session or DEFAULT_DEMO_SESSION
                ),
                captured_session_path=args.captured_session,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(format_journal_add_summary(entry))
        return

    entries = load_journal_entries(journal_dir)
    if action == "list":
        print(format_journal_list(entries))
        return

    if action == "compare":
        from_ref = args.command_args[0] if len(args.command_args) >= 1 else "previous"
        to_ref = args.command_args[1] if len(args.command_args) >= 2 else "latest"
        try:
            comparison = compare_journal_entries(entries, from_ref, to_ref)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(format_journal_comparison(comparison))
        return

    if action == "report":
        output_path = args.command_args[0] if args.command_args else Path(journal_dir) / "journal.md"
        report = build_journal_report(entries)
        try:
            target = write_journal_report(report, output_path)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Saved journal report to {target}")
        return

    raise SystemExit(
        "Usage: gex-terminal journal {add,list,compare,report} "
        "[OUTPUT_OR_ENTRY_REF] [--journal-dir PATH]"
    )


async def session_store_command(config: GexConfig, args: argparse.Namespace) -> None:
    """Handle local historical session snapshot-store commands."""
    action = args.command_path or "list"
    store_dir = args.session_store_dir

    if action == "save":
        snapshot, consumer, _ = await compute_snapshot(config)
        snapshot["feed_quality"] = consumer.feed_quality_snapshot()
        record = save_session_snapshot(
            snapshot,
            store_dir,
            source_name=_session_store_source_name(config, args),
            label=args.session_label,
        )
        print(format_session_save_summary(record))
        return

    if action == "captures":
        print(format_captured_session_list(load_captured_sessions(store_dir)))
        return

    records = load_session_records(store_dir)
    if action == "list":
        print(format_session_record_list(records))
        return

    if action == "report":
        output_path = args.command_args[0] if args.command_args else Path(store_dir) / "session_store.md"
        report = build_session_store_report(records)
        try:
            target = write_session_store_report(report, output_path)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Saved session store report to {target}")
        return

    raise SystemExit(
        "Usage: gex-terminal session-store {save,list,report,captures} "
        "[OUTPUT] [--session-store-dir PATH] [--session-label TEXT]"
    )


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
    _, consumer, base_matrix = await compute_snapshot(
        config, quality_scenario=quality_scenario
    )
    contract_rows = await consumer.selected_contract_rows(
        expiry_filter=config.expiry_filter,
        as_of=consumer.market_time,
    )
    report = build_sensitivity_report(
        spot=consumer.current_spot,
        chain_state=consumer.chain_state,
        days_to_expiry=config.days_to_expiry,
        risk_free_rate=config.risk_free_rate,
        contract_multiplier=config.contract_multiplier,
        contract_rows=contract_rows,
        base_matrix=base_matrix,
        as_of=consumer.market_time,
    )
    try:
        target = write_sensitivity_report(report, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Saved sensitivity report to {target}")


async def inject_provider_command(config: GexConfig, args: argparse.Namespace) -> None:
    """Inject raw provider sample data without opening a live market-data connection."""
    if not args.command_path:
        raise SystemExit(
            "Usage: gex-terminal inject-provider PATH|bundled:NAME [--provider NAME]"
        )

    fixture_path = args.command_path
    metadata_path = args.metadata
    underlying_path = args.underlying_fixture
    fixture_format = args.fixture_format
    provider = args.provider or config.data_provider
    if args.command_path.startswith("bundled:"):
        try:
            case = provider_fixture_case_for_name(
                args.command_path.removeprefix("bundled:")
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        fixture_path = str(case.fixture_path)
        metadata_path = args.metadata or (
            str(case.metadata_path) if case.metadata_path else None
        )
        underlying_path = args.underlying_fixture or (
            str(case.underlying_path) if case.underlying_path else None
        )
        fixture_format = (
            args.fixture_format
            if args.fixture_format != "auto"
            else case.fixture_format
        )
        provider = args.provider or case.provider
        if not args.symbol:
            config = replace(
                config,
                symbol=case.symbol,
                symbols=_symbols_with_target(config.symbols, case.symbol),
            )
    elif not args.provider and (
        fixture_format == "cboe-option-quotes"
        or Path(fixture_path).suffix.lower() == ".csv"
    ):
        provider = "cboe"
    try:
        snapshot = await inject_provider_fixture(
            provider=provider,
            fixture_path=fixture_path,
            config=config,
            fixture_format=fixture_format,
            metadata_path=metadata_path,
            underlying_path=underlying_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(provider_injection_summary(snapshot))
    if args.export:
        try:
            target = write_snapshot_export(snapshot, args.export)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Saved injected provider snapshot to {target}")


async def tradovate_certification_command(
    config: GexConfig, args: argparse.Namespace
) -> None:
    """Run the explicit, read-only Tradovate live-network certification gate."""
    output_path = args.command_path or "tradovate_certification.json"
    try:
        report = await build_tradovate_certification_report(
            symbol=config.symbol,
            environment=config.tradovate_environment,
            contract_multiplier=config.contract_multiplier,
            duration_seconds=args.certification_duration,
            max_option_contracts=args.max_option_contracts,
            ack_live_network=args.ack_live_network,
        )
        target = write_tradovate_certification_report(report, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    result = report["result"]
    print(
        f"Saved redacted Tradovate certification to {target} "
        f"(transport={result['transport_certified']}, "
        f"quantitative_gex={result['quantitative_gex_certified']})"
    )
    if not result["transport_certified"]:
        raise SystemExit(2)


def model_evidence_command(output_path: str) -> None:
    """Write bounded numerical evidence and fail closed on a regression."""
    report = build_model_evidence_report()
    try:
        target = write_model_evidence_report(report, output_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Saved model evidence to {target} "
        f"(numerical_gate={'passed' if report['result']['passed'] else 'failed'}, "
        "predictive_validity=unmeasured)"
    )
    if not report["result"]["passed"]:
        raise SystemExit(1)


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
        expiry_filter=config.expiry_filter,
    )

    if config.data_mode == "replay":
        # Noninteractive exports and saved snapshots should never wait through
        # a capture's wall-clock gaps. Interactive replay retains timing.
        replay_config = replace(
            config,
            replay_delay_seconds=0.0,
            replay_clock="none",
        )
        adapter = build_market_data_adapter(consumer, replay_config)
        await adapter.stream_market_data()
    elif config.data_mode == "demo":
        await seed_demo_session(consumer)
    else:
        raise SystemExit("Non-interactive exports currently support demo or replay mode only.")

    if quality_scenario:
        await apply_quality_scenario(consumer, quality_scenario)

    data = await consumer.process_latest_snapshot(
        days_to_expiry=config.days_to_expiry,
        expiry_filter=config.expiry_filter,
    )
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
        timestamp=(
            consumer.market_time.isoformat().replace("+00:00", "Z")
            if consumer.market_time is not None
            else None
        ),
    )
    return snapshot, consumer, data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Intraday GEX imbalance terminal",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"gex-terminal {__version__}",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "validate-fixture",
            "list-replays",
            "replay-lab",
            "demo-lab",
            "journal",
            "session-store",
            "fixture-lab",
            "inject-provider",
            "tradovate-certify",
            "model-evidence",
        ),
        help="Optional utility command.",
    )
    parser.add_argument(
        "command_path",
        nargs="?",
        help=(
            "Path argument for utility commands such as validate-fixture, replay-lab, "
            "demo-lab, journal, session-store, fixture-lab, or inject-provider."
        ),
    )
    parser.add_argument(
        "command_args",
        nargs="*",
        help="Additional positional arguments for commands such as journal compare/report.",
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
        "--expiry-filter",
        help="Option expiry selection: all, 0dte, or an exact expiry label.",
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
        "--captured-session",
        metavar="PATH",
        help="Replay an integrity-checked captured-session JSONL file.",
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
        "--fixture-format",
        choices=INJECTION_FORMATS,
        default="auto",
        help="Raw fixture format for inject-provider. Default: auto.",
    )
    parser.add_argument(
        "--metadata",
        metavar="PATH",
        help="Provider metadata fixture for inject-provider, such as contract definitions.",
    )
    parser.add_argument(
        "--underlying-fixture",
        metavar="PATH",
        help="Underlying quote fixture for inject-provider formats that separate option and underlying data.",
    )
    parser.add_argument(
        "--replay-delay",
        type=float,
        help="Delay between replay messages in seconds. Overrides GEX_REPLAY_DELAY_SECONDS.",
    )
    parser.add_argument(
        "--replay-clock",
        choices=("auto", "fixed", "event", "none"),
        help="Replay timing clock. Captures default to event time; legacy JSONL to fixed delay.",
    )
    parser.add_argument(
        "--replay-speed",
        type=float,
        help="Event-time replay speed multiplier. Overrides GEX_REPLAY_SPEED.",
    )
    parser.add_argument(
        "--replay-max-gap",
        type=float,
        help="Optional maximum source-time gap before replay-speed scaling.",
    )
    parser.add_argument(
        "--strict-event-time",
        action="store_true",
        help="Fail replay on missing or regressing event timestamps.",
    )
    parser.add_argument(
        "--record-session",
        action="store_true",
        help="Capture normalized replay/live messages to an integrity-checked session file.",
    )
    parser.add_argument(
        "--capture-path",
        metavar="PATH",
        help="Output path for --record-session; specifying it also enables capture.",
    )
    parser.add_argument(
        "--capture-label",
        help="Optional human label stored in the captured-session header.",
    )
    parser.add_argument(
        "--screenshot",
        metavar="PATH",
        help="Export a color-themed Textual SVG screenshot using demo or replay data, then exit.",
    )
    parser.add_argument(
        "--screenshot-view",
        choices=("terminal", "replay-browser"),
        default="terminal",
        help="Terminal view to capture with --screenshot. Default: terminal.",
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
        "--journal-dir",
        default=DEFAULT_JOURNAL_DIR,
        help=f"Local research journal directory. Default: {DEFAULT_JOURNAL_DIR}.",
    )
    parser.add_argument(
        "--session-store-dir",
        default=DEFAULT_SESSION_STORE_DIR,
        help=f"Local historical session store directory. Default: {DEFAULT_SESSION_STORE_DIR}.",
    )
    parser.add_argument(
        "--session-label",
        help="Human label for session-store save records.",
    )
    parser.add_argument(
        "--ack-live-network",
        action="store_true",
        help="Acknowledge credentialed, read-only network access for tradovate-certify.",
    )
    parser.add_argument(
        "--certification-duration",
        type=float,
        default=10.0,
        help="Seconds to observe the Tradovate market-data stream. Default: 10.",
    )
    parser.add_argument(
        "--max-option-contracts",
        type=int,
        default=12,
        help="Maximum option subscriptions during Tradovate certification. Default: 12.",
    )
    parser.add_argument(
        "--tradovate-environment",
        choices=("demo", "live"),
        help="Tradovate environment for live mode or certification. Overrides TRADOVATE_ENV.",
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

    if args.expiry_filter:
        updates["expiry_filter"] = args.expiry_filter

    if args.tradovate_environment:
        updates["tradovate_environment"] = args.tradovate_environment

    if args.refresh is not None:
        updates["refresh_interval_seconds"] = args.refresh

    if args.replay:
        updates["data_mode"] = "replay"
        updates["replay_path"] = args.replay

    if args.captured_session:
        updates["data_mode"] = "replay"
        updates["replay_path"] = args.captured_session

    if args.replay_session:
        session = replay_session_for_name(args.replay_session)
        updates["data_mode"] = "replay"
        updates["replay_path"] = session.path

    if args.replay_delay is not None:
        updates["replay_delay_seconds"] = args.replay_delay

    if args.replay_clock:
        updates["replay_clock"] = args.replay_clock

    if args.replay_speed is not None:
        updates["replay_speed"] = args.replay_speed

    if args.replay_max_gap is not None:
        updates["replay_max_gap_seconds"] = args.replay_max_gap

    if args.strict_event_time:
        updates["strict_event_time"] = True

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


def _session_store_source_name(config: GexConfig, args: argparse.Namespace) -> str:
    if args.replay_session:
        return args.replay_session
    if config.data_mode == "replay":
        return Path(config.replay_path).stem
    return config.data_mode


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()

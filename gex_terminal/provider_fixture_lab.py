"""Offline provider fixture workbench reports."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from gex_terminal.config import GexConfig
from gex_terminal.provider_injector import inject_provider_fixture


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ProviderFixtureCase:
    """A bundled provider-shaped fixture that should produce a GEX snapshot."""

    name: str
    label: str
    provider: str
    symbol: str
    fixture_path: Path
    description: str
    fixture_format: str = "auto"
    metadata_path: Path | None = None
    underlying_path: Path | None = None


PROVIDER_FIXTURE_CASES: tuple[ProviderFixtureCase, ...] = (
    ProviderFixtureCase(
        name="tradovate-live-sample",
        label="Tradovate Live Frames",
        provider="tradovate",
        symbol="ES",
        fixture_path=Path("tests/fixtures/tradovate_live_sample.jsonl"),
        description=(
            "Sanitized WebSocket-style quote frames with one intentionally "
            "malformed quote for feed-health testing."
        ),
    ),
    ProviderFixtureCase(
        name="tradovate-md-quotes",
        label="Tradovate Metadata Join",
        provider="tradovate",
        symbol="ES",
        fixture_path=Path("tests/fixtures/tradovate_md_quotes.json"),
        metadata_path=Path("tests/fixtures/tradovate_contract_discovery.json"),
        description="Quote payload joined to sanitized contract-discovery metadata.",
    ),
    ProviderFixtureCase(
        name="databento-glbx",
        label="Databento GLBX Fixture",
        provider="databento",
        symbol="ES",
        fixture_path=Path("tests/fixtures/databento_trade_records.json"),
        metadata_path=Path("tests/fixtures/databento_definition_records.json"),
        underlying_path=Path("tests/fixtures/databento_underlying_mbp1_record.json"),
        description=(
            "Synthetic GLBX.MDP3 definitions, option trades, and underlying "
            "mbp-1 quote sample."
        ),
    ),
    ProviderFixtureCase(
        name="yfinance-etf-options",
        label="yfinance ETF Options",
        provider="yfinance",
        symbol="SPY",
        fixture_path=Path("tests/fixtures/yfinance_option_chain_records.json"),
        description="Delayed equity/ETF option-chain sample for SPY-style research.",
    ),
    ProviderFixtureCase(
        name="cboe-option-quotes-csv",
        label="Cboe Option Quotes CSV",
        provider="cboe",
        symbol="SPY",
        fixture_path=Path("tests/fixtures/cboe_option_quotes_sample.csv"),
        fixture_format="cboe-option-quotes",
        description="Cboe-style option quote CSV sample using common column names.",
    ),
)


def bundled_provider_fixture_cases() -> tuple[ProviderFixtureCase, ...]:
    """Return the built-in provider fixture cases in report order."""
    return PROVIDER_FIXTURE_CASES


async def build_provider_fixture_lab_report(
    config: GexConfig,
    cases: Iterable[ProviderFixtureCase] | None = None,
) -> dict[str, Any]:
    """Run bundled provider-shaped fixtures and build a shareable report."""
    selected_cases = tuple(cases) if cases is not None else bundled_provider_fixture_cases()
    results = [
        await analyze_provider_fixture_case(case, config)
        for case in selected_cases
    ]
    return {
        "schema": "gex-terminal.provider-fixture-lab.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cases": results,
        "scorecard": build_provider_fixture_scorecard(results),
        "inputs": {
            "days_to_expiry": float(config.days_to_expiry),
            "risk_free_rate": float(config.risk_free_rate),
            "contract_multiplier": int(config.contract_multiplier),
        },
        "recommendations": build_provider_fixture_recommendations(results),
    }


async def analyze_provider_fixture_case(
    case: ProviderFixtureCase,
    config: GexConfig,
) -> dict[str, Any]:
    """Inject one provider-shaped fixture and summarize the computed snapshot."""
    fixture_path = _resolve_path(case.fixture_path)
    metadata_path = _resolve_path(case.metadata_path) if case.metadata_path else None
    underlying_path = _resolve_path(case.underlying_path) if case.underlying_path else None
    case_config = replace(
        config,
        symbol=case.symbol,
        symbols=_symbols_with_target(config.symbols, case.symbol),
        data_mode="live",
        data_provider=case.provider,
        replay_delay_seconds=0.0,
    )
    try:
        snapshot = await inject_provider_fixture(
            provider=case.provider,
            fixture_path=fixture_path,
            config=case_config,
            fixture_format=case.fixture_format,
            metadata_path=metadata_path,
            underlying_path=underlying_path,
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        return {
            "name": case.name,
            "label": case.label,
            "provider": case.provider,
            "symbol": case.symbol,
            "description": case.description,
            "summary": _failed_summary(case, exc),
            "snapshot": None,
            "command": provider_fixture_case_command(case),
        }

    snapshot = _snapshot_with_portable_paths(
        snapshot,
        fixture_path=fixture_path,
        metadata_path=metadata_path,
        underlying_path=underlying_path,
    )
    return {
        "name": case.name,
        "label": case.label,
        "provider": case.provider,
        "symbol": case.symbol,
        "description": case.description,
        "summary": summarize_provider_fixture_snapshot(case, snapshot),
        "snapshot": snapshot,
        "command": provider_fixture_case_command(case),
    }


def summarize_provider_fixture_snapshot(
    case: ProviderFixtureCase,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Return stable top-line fields for dashboards and CSV exports."""
    injection = snapshot.get("provider_injection", {})
    quality = snapshot.get("feed_quality", {})
    metrics = snapshot.get("metrics", {})
    return {
        "ok": True,
        "name": case.name,
        "label": case.label,
        "provider": case.provider,
        "symbol": snapshot.get("symbol", case.symbol),
        "fixture": injection.get("fixture") or _portable_path(case.fixture_path),
        "fixture_format": injection.get("fixture_format") or case.fixture_format,
        "metadata": injection.get("metadata"),
        "underlying_fixture": injection.get("underlying_fixture"),
        "status": quality.get("status", "unknown"),
        "health": quality.get("health", "unknown"),
        "notes": list(quality.get("notes") or ()),
        "spot": float(snapshot.get("spot", 0.0)),
        "total_net_gex": float(metrics.get("total_net_gex", 0.0)),
        "gamma_wall": float(metrics.get("gamma_wall", 0.0)),
        "zero_gamma": float(metrics.get("zero_gamma", 0.0)),
        "call_wall": float(metrics.get("call_wall", 0.0)),
        "put_wall": float(metrics.get("put_wall", 0.0)),
        "normalized_messages": int(injection.get("normalized_messages", 0) or 0),
        "message_count": int(quality.get("message_count", 0) or 0),
        "frame_count": int(quality.get("frame_count", 0) or 0),
        "parse_error_count": int(quality.get("parse_error_count", 0) or 0),
        "malformed_count": int(quality.get("malformed_count", 0) or 0),
        "dropped_count": int(quality.get("dropped_count", 0) or 0),
        "subscription_status": quality.get("subscription_status", "unknown"),
        "subscribed_symbol_count": int(quality.get("subscribed_symbol_count", 0) or 0),
        "error": "",
    }


def build_provider_fixture_scorecard(
    results: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate fixture outcomes into a compact scorecard."""
    rows = [result["summary"] for result in results]
    passed = sum(1 for row in rows if row["ok"])
    failed = len(rows) - passed
    degraded = sum(
        1
        for row in rows
        if row["ok"] and row["health"] not in {"healthy", "simulated"}
    )
    return {
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "healthy": passed - degraded,
        "degraded": degraded,
        "normalized_messages": sum(int(row.get("normalized_messages", 0)) for row in rows),
        "provider_frames": sum(int(row.get("frame_count", 0)) for row in rows),
        "parse_errors": sum(int(row.get("parse_error_count", 0)) for row in rows),
        "dropped_messages": sum(int(row.get("dropped_count", 0)) for row in rows),
    }


def build_provider_fixture_recommendations(
    results: Iterable[dict[str, Any]],
) -> list[str]:
    """Offer next steps based on report outcomes."""
    rows = [result["summary"] for result in results]
    failed = [row for row in rows if not row["ok"]]
    degraded = [row for row in rows if row["ok"] and row["health"] not in {"healthy", "simulated"}]
    recommendations = [
        "Attach the Markdown report to provider-adapter issues or pull requests.",
        "Use the JSON report as a baseline when changing adapter normalization.",
        "Add new sanitized provider samples as fixture cases before wiring live credentials.",
    ]
    if failed:
        recommendations.insert(
            0,
            f"Fix failed fixture cases first: {', '.join(row['name'] for row in failed)}.",
        )
    if degraded:
        recommendations.insert(
            0,
            f"Review degraded health counters in: {', '.join(row['name'] for row in degraded)}.",
        )
    return recommendations


def provider_fixture_lab_to_markdown(report: dict[str, Any]) -> str:
    scorecard = report["scorecard"]
    inputs = report["inputs"]
    lines = [
        "# Offline Provider Fixture Workbench",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Cases run: `{scorecard['total']}`",
        f"- Passed: `{scorecard['passed']}`",
        f"- Degraded: `{scorecard['degraded']}`",
        f"- Failed: `{scorecard['failed']}`",
        f"- Days to expiry: `{inputs['days_to_expiry']:g}`",
        f"- Contract multiplier: `{inputs['contract_multiplier']}`",
        "",
        "## Provider Scorecard",
        "",
        (
            "| Case | Provider | Format | Symbol | Health | Messages | Frames | "
            "Parse Err | Dropped | Gamma Wall | Zero Gamma |"
        ),
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in report["cases"]:
        summary = result["summary"]
        lines.append(
            f"| {summary['label']} | {summary['provider']} | "
            f"{summary['fixture_format']} | {summary['symbol']} | "
            f"{summary['health']} | {summary['normalized_messages']} | "
            f"{summary['frame_count']} | {summary['parse_error_count']} | "
            f"{summary['dropped_count']} | {_number(summary['gamma_wall'])} | "
            f"{_number(summary['zero_gamma'])} |"
        )

    lines.extend(["", "## Case Notes", ""])
    for result in report["cases"]:
        summary = result["summary"]
        lines.extend([
            f"### {result['label']}",
            "",
            f"- Fixture: `{summary['fixture']}`",
            f"- Description: {result['description']}",
            f"- Command: `{result['command']}`",
        ])
        if summary["ok"]:
            lines.extend([
                (
                    f"- Result: `{summary['health']}` health, "
                    f"`{summary['normalized_messages']}` normalized messages, "
                    f"`{summary['frame_count']}` provider frames."
                ),
                (
                    f"- Levels: gamma wall `{_number(summary['gamma_wall'])}`, "
                    f"zero gamma `{_number(summary['zero_gamma'])}`, "
                    f"net GEX `{_money(summary['total_net_gex'])}`."
                ),
            ])
            if summary["notes"]:
                lines.append(f"- Notes: `{'; '.join(summary['notes'])}`")
        else:
            lines.append(f"- Error: `{summary['error']}`")
        lines.append("")

    lines.extend([
        "## Contributor Uses",
        "",
        "- Confirm that adapter changes still produce computable snapshots offline.",
        "- Share one report when proposing a new provider fixture or parser change.",
        "- Compare provider health counters before opening a live-data debugging issue.",
        "- Keep fixture samples sanitized so reports are safe to post publicly.",
    ])
    if report.get("recommendations"):
        lines.extend(["", "## Recommended Next Checks", ""])
        for recommendation in report["recommendations"]:
            lines.append(f"- {recommendation}")
    return "\n".join(lines) + "\n"


def provider_fixture_lab_to_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    fieldnames = (
        "case",
        "label",
        "provider",
        "symbol",
        "fixture_format",
        "fixture",
        "ok",
        "health",
        "status",
        "spot",
        "total_net_gex",
        "gamma_wall",
        "zero_gamma",
        "normalized_messages",
        "message_count",
        "frame_count",
        "parse_error_count",
        "malformed_count",
        "dropped_count",
        "subscription_status",
        "subscribed_symbol_count",
        "error",
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for result in report["cases"]:
        summary = result["summary"]
        writer.writerow({
            "case": summary["name"],
            "label": summary["label"],
            "provider": summary["provider"],
            "symbol": summary["symbol"],
            "fixture_format": summary["fixture_format"],
            "fixture": summary["fixture"],
            "ok": summary["ok"],
            "health": summary["health"],
            "status": summary["status"],
            "spot": summary["spot"],
            "total_net_gex": summary["total_net_gex"],
            "gamma_wall": summary["gamma_wall"],
            "zero_gamma": summary["zero_gamma"],
            "normalized_messages": summary["normalized_messages"],
            "message_count": summary["message_count"],
            "frame_count": summary["frame_count"],
            "parse_error_count": summary["parse_error_count"],
            "malformed_count": summary["malformed_count"],
            "dropped_count": summary["dropped_count"],
            "subscription_status": summary["subscription_status"],
            "subscribed_symbol_count": summary["subscribed_symbol_count"],
            "error": summary["error"],
        })
    return output.getvalue()


def write_provider_fixture_lab_report(report: dict[str, Any], output_path: str) -> Path:
    """Write a provider fixture lab report as JSON, CSV, or Markdown."""
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()
    if suffix == ".json" or suffix == "":
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        target.write_text(provider_fixture_lab_to_csv(report), encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        target.write_text(provider_fixture_lab_to_markdown(report), encoding="utf-8")
    else:
        raise ValueError("Provider fixture lab report path must end in .json, .csv, or .md")
    return target


def provider_fixture_case_command(case: ProviderFixtureCase) -> str:
    parts = [
        "gex-terminal",
        "inject-provider",
        _portable_path(case.fixture_path),
    ]
    if case.provider != "cboe":
        parts.extend(["--provider", case.provider])
    if case.fixture_format != "auto":
        parts.extend(["--fixture-format", case.fixture_format])
    parts.extend(["--symbol", case.symbol])
    if case.metadata_path:
        parts.extend(["--metadata", _portable_path(case.metadata_path)])
    if case.underlying_path:
        parts.extend(["--underlying-fixture", _portable_path(case.underlying_path)])
    return " ".join(parts)


def _failed_summary(case: ProviderFixtureCase, exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "name": case.name,
        "label": case.label,
        "provider": case.provider,
        "symbol": case.symbol,
        "fixture": _portable_path(case.fixture_path),
        "fixture_format": case.fixture_format,
        "metadata": _portable_path(case.metadata_path) if case.metadata_path else None,
        "underlying_fixture": (
            _portable_path(case.underlying_path) if case.underlying_path else None
        ),
        "status": "failed",
        "health": "failed",
        "notes": [],
        "spot": 0.0,
        "total_net_gex": 0.0,
        "gamma_wall": 0.0,
        "zero_gamma": 0.0,
        "call_wall": 0.0,
        "put_wall": 0.0,
        "normalized_messages": 0,
        "message_count": 0,
        "frame_count": 0,
        "parse_error_count": 0,
        "malformed_count": 0,
        "dropped_count": 0,
        "subscription_status": "failed",
        "subscribed_symbol_count": 0,
        "error": str(exc),
    }


def _snapshot_with_portable_paths(
    snapshot: dict[str, Any],
    *,
    fixture_path: Path,
    metadata_path: Path | None,
    underlying_path: Path | None,
) -> dict[str, Any]:
    portable = dict(snapshot)
    injection = dict(portable.get("provider_injection", {}))
    injection["fixture"] = _portable_path(fixture_path)
    injection["metadata"] = _portable_path(metadata_path) if metadata_path else None
    injection["underlying_fixture"] = (
        _portable_path(underlying_path) if underlying_path else None
    )
    portable["provider_injection"] = injection
    return portable


def _resolve_path(path: Path | None) -> Path:
    if path is None:
        raise ValueError("Path is required")
    if path.is_absolute() or path.exists():
        return path
    return PROJECT_ROOT / path


def _portable_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return str(candidate.relative_to(PROJECT_ROOT))
    except ValueError:
        pass
    try:
        return str(candidate.relative_to(Path.cwd()))
    except ValueError:
        return str(candidate)


def _symbols_with_target(symbols: tuple[str, ...], target_symbol: str) -> tuple[str, ...]:
    cleaned = tuple(symbol for symbol in symbols if symbol != target_symbol)
    return (target_symbol, *cleaned)[:4]


def _number(value: float) -> str:
    return f"{float(value):,.1f}"


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

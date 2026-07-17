"""Validation helpers for normalized JSONL replay and provider fixtures."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gex_terminal.market_data_adapter import validate_normalized_message


@dataclass
class FixtureValidationIssue:
    line_number: int
    message: str


@dataclass
class FixtureValidationReport:
    path: Path
    total_lines: int = 0
    message_count: int = 0
    underlying_ticks: int = 0
    option_ticks: int = 0
    symbols: set[str] = field(default_factory=set)
    strikes: set[float] = field(default_factory=set)
    expiries: set[str] = field(default_factory=set)
    phases: set[str] = field(default_factory=set)
    issues: list[FixtureValidationIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "ok": self.ok,
            "total_lines": self.total_lines,
            "message_count": self.message_count,
            "underlying_ticks": self.underlying_ticks,
            "option_ticks": self.option_ticks,
            "symbols": sorted(self.symbols),
            "strike_count": len(self.strikes),
            "strikes": sorted(self.strikes),
            "expiries": sorted(self.expiries),
            "phases": sorted(self.phases),
            "warnings": list(self.warnings),
            "issues": [
                {"line": issue.line_number, "message": issue.message}
                for issue in self.issues
            ],
        }


def validate_fixture(path: str | Path) -> FixtureValidationReport:
    target = Path(path)
    report = FixtureValidationReport(path=target)
    if not target.exists():
        report.issues.append(FixtureValidationIssue(0, f"File not found: {target}"))
        return report

    with target.open(encoding="utf-8") as fixture_file:
        for line_number, line in enumerate(fixture_file, start=1):
            report.total_lines += 1
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError as exc:
                report.issues.append(
                    FixtureValidationIssue(line_number, f"Invalid JSON: {exc.msg}")
                )
                continue

            try:
                validate_normalized_message(message)
                _validate_numeric_fields(message)
            except ValueError as exc:
                report.issues.append(FixtureValidationIssue(line_number, str(exc)))
                continue

            _record_message(report, message)

    _add_report_warnings(report)
    return report


def format_fixture_validation_report(report: FixtureValidationReport) -> str:
    status = "OK" if report.ok else "FAILED"
    lines = [
        f"Fixture validation {status}: {report.path}",
        f"messages: {report.message_count} "
        f"({report.underlying_ticks} underlying, {report.option_ticks} options)",
        f"symbols: {', '.join(sorted(report.symbols)) or '--'}",
        f"strikes: {len(report.strikes)}",
        f"expiries: {', '.join(sorted(report.expiries)) or '--'}",
        f"phases: {', '.join(sorted(report.phases)) or '--'}",
    ]
    if report.warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.issues:
        lines.append("issues:")
        lines.extend(
            f"- line {issue.line_number}: {issue.message}" for issue in report.issues
        )
    return "\n".join(lines)


def _record_message(report: FixtureValidationReport, message: dict[str, Any]) -> None:
    report.message_count += 1
    if message.get("type") == "underlying_tick":
        report.underlying_ticks += 1
        report.symbols.add(str(message["symbol"]).upper())
    elif message.get("type") == "options_volume_tick":
        report.option_ticks += 1
        report.strikes.add(float(message["strike"]))
        expiry = message.get("expiry")
        if expiry not in (None, ""):
            report.expiries.add(str(expiry))

    phase = message.get("session_phase")
    if phase not in (None, ""):
        report.phases.add(str(phase))


def _validate_numeric_fields(message: dict[str, Any]) -> None:
    if message.get("type") == "underlying_tick":
        if float(message["price"]) <= 0:
            raise ValueError("underlying_tick price must be positive")
        return

    if float(message["strike"]) <= 0:
        raise ValueError("options_volume_tick strike must be positive")
    if int(message["volume"]) < 0:
        raise ValueError("options_volume_tick volume must be non-negative")
    if "iv" in message and float(message["iv"]) <= 0:
        raise ValueError("options_volume_tick iv must be positive when provided")


def _add_report_warnings(report: FixtureValidationReport) -> None:
    if report.ok and report.message_count == 0:
        report.warnings.append("fixture contains no normalized messages")
    if report.ok and report.underlying_ticks == 0:
        report.warnings.append("fixture contains option ticks but no underlying price")
    if report.ok and report.option_ticks == 0:
        report.warnings.append("fixture contains no option volume ticks")
    if len(report.symbols) > 1:
        report.warnings.append("fixture contains multiple underlying symbols")
    if report.option_ticks and len(report.strikes) < 3:
        report.warnings.append("fixture has fewer than three option strikes")

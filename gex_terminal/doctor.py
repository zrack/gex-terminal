"""Offline, privacy-safe installation and runtime preflight diagnostics."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.resources
import importlib.util
import json
import os
import re
import site
import stat
import sys
import tempfile
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from gex_terminal import __version__
from gex_terminal.config import ConfigValidationError, GexConfig
from gex_terminal.provider_readiness import PROVIDER_READINESS_STATES


DOCTOR_SCHEMA = "gex-terminal.doctor.v1"
EXIT_OK = 0
EXIT_RUNTIME_FAILURE = 1
EXIT_CONFIGURATION_FAILURE = 2
MINIMUM_PYTHON = (3, 11)

REQUIRED_RUNTIME_MODULES: tuple[tuple[str, str], ...] = (
    ("aiohttp", "aiohttp"),
    ("numpy", "numpy"),
    ("python-dotenv", "dotenv"),
    ("textual", "textual"),
    ("websockets", "websockets"),
)

OPTIONAL_PROVIDER_SDKS: Mapping[str, tuple[str, str]] = {
    "databento": ("databento", "databento"),
    "ibkr": ("ib_insync", "ibkr"),
    "yfinance": ("yfinance", "yfinance"),
}

REQUIRED_BUNDLED_RESOURCES: tuple[str, ...] = (
    "gex_terminal.tcss",
    "data/replays/demo_replay.jsonl",
    "data/replays/es_call_wall_breakout.jsonl",
    "data/replays/es_chop_day.jsonl",
    "data/replays/es_expiration_compression.jsonl",
    "data/replays/es_gap_fade.jsonl",
    "data/replays/es_quality_stress.jsonl",
    "data/replays/es_synthetic_full_session.jsonl",
    "data/replays/es_trend_day.jsonl",
    "data/replays/es_volatility_spike.jsonl",
    "data/replays/es_zero_gamma_flip.jsonl",
    "data/provider_fixtures/batch_position_comparison_example.json",
    "data/provider_fixtures/capture_policy_example.json",
    "data/provider_fixtures/cboe_option_quotes_sample.csv",
    "data/provider_fixtures/corpus_item_metadata_example.json",
    "data/provider_fixtures/databento_definition_records.json",
    "data/provider_fixtures/databento_mixed_offline_records.jsonl",
    "data/provider_fixtures/databento_normalized_expected.jsonl",
    "data/provider_fixtures/databento_statistics_records.json",
    "data/provider_fixtures/databento_trade_records.json",
    "data/provider_fixtures/databento_underlying_mbp1_record.json",
    "data/provider_fixtures/experiment_spec_example.json",
    "data/provider_fixtures/model_profile_example.json",
    "data/provider_fixtures/position_model_comparison_example.json",
    "data/provider_fixtures/price_action_validation_example.json",
    "data/provider_fixtures/tradovate_contract_discovery.json",
    "data/provider_fixtures/tradovate_live_sample.jsonl",
    "data/provider_fixtures/tradovate_md_quotes.json",
    "data/provider_fixtures/yfinance_option_chain_records.json",
)

_SAFE_CONFIG_FIELDS = {field.name for field in fields(GexConfig)} | {
    "GEX_CONTRACT_MULTIPLIER",
    "GEX_DAYS_TO_EXPIRY",
    "GEX_REFRESH_INTERVAL_SECONDS",
    "GEX_REPLAY_DELAY_SECONDS",
    "GEX_REPLAY_MAX_GAP_SECONDS",
    "GEX_REPLAY_SPEED",
    "GEX_RISK_FREE_RATE",
    "GEX_STALE_AFTER_SECONDS",
    "GEX_STRICT_EVENT_TIME",
}
_SAFE_CONFIG_CONSTRAINTS = {
    "an integer",
    "finite",
    "finite or blank",
    "greater than 0",
    "greater than or equal to 0",
    "numeric",
    "numeric or blank",
    "true or false",
    "true or false (accepted: 1/0, true/false, yes/no, on/off)",
}
_SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+!-]{0,63}\Z")
PUBLIC_VERSION = (
    __version__ if _SAFE_VERSION.fullmatch(str(__version__)) else "unknown"
)


def build_doctor_report(
    config: GexConfig | None = None,
    *,
    config_error: ConfigValidationError | None = None,
    find_spec: Callable[[str], object | None] | None = None,
    distribution_version: Callable[[str], str] | None = None,
    resource_exists: Callable[[str], bool] | None = None,
    storage_probe: Callable[[], Mapping[str, bool]] | None = None,
    hidden_pth_probe: Callable[[], Mapping[str, Any]] | None = None,
    provider_catalog: Callable[[], Mapping[str, str]] | None = None,
    replay_readable: Callable[[str], bool] | None = None,
    logging_validator: Callable[[], bool] | None = None,
    python_version: tuple[int, int, int] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return one safe, JSON-serializable offline preflight report."""
    spec_lookup = find_spec or importlib.util.find_spec
    version_lookup = distribution_version or importlib.metadata.version
    resource_lookup = resource_exists or bundled_resource_exists
    storage_lookup = storage_probe or probe_temporary_storage
    hidden_lookup = hidden_pth_probe or probe_hidden_editable_pth
    catalog_lookup = provider_catalog or load_provider_catalog
    replay_lookup = replay_readable or configured_replay_is_readable
    logging_lookup = logging_validator or logging_configuration_valid
    runtime_version = python_version or tuple(sys.version_info[:3])

    checks: list[dict[str, Any]] = []
    failure_codes: list[int] = []

    def add_check(
        check_id: str,
        category: str,
        status: str,
        summary: str,
        *,
        action: str | None = None,
        details: Mapping[str, Any] | None = None,
        failure_code: int | None = None,
    ) -> None:
        check: dict[str, Any] = {
            "id": check_id,
            "category": category,
            "status": status,
            "summary": summary,
        }
        if action:
            check["action"] = action
        if details:
            check["details"] = dict(details)
        checks.append(check)
        if status == "fail":
            failure_codes.append(failure_code or EXIT_RUNTIME_FAILURE)

    supported_python = runtime_version >= MINIMUM_PYTHON
    add_check(
        "runtime.python",
        "runtime",
        "pass" if supported_python else "fail",
        (
            "Python version satisfies the supported runtime."
            if supported_python
            else "Python version is older than the supported runtime."
        ),
        action=(
            None
            if supported_python
            else f"Use Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer."
        ),
        details={
            "detected": ".".join(str(part) for part in runtime_version),
            "minimum": ".".join(str(part) for part in MINIMUM_PYTHON),
        },
        failure_code=EXIT_RUNTIME_FAILURE,
    )

    installed_version: str | None
    metadata_failed = False
    try:
        raw_installed_version = version_lookup("gex-terminal")
        installed_version = safe_public_version(raw_installed_version)
        if installed_version is None:
            metadata_failed = True
    except importlib.metadata.PackageNotFoundError:
        installed_version = None
    except Exception:
        installed_version = None
        metadata_failed = True

    if metadata_failed:
        add_check(
            "package.metadata",
            "package",
            "fail",
            "Installed distribution metadata could not be read.",
            action="Reinstall gex-terminal in the active Python environment.",
            details={"application_version": PUBLIC_VERSION},
            failure_code=EXIT_RUNTIME_FAILURE,
        )
    elif installed_version is None:
        add_check(
            "package.metadata",
            "package",
            "warning",
            "Distribution metadata is absent; source-module execution may still work.",
            action="Install gex-terminal to enable its console launcher.",
            details={"application_version": PUBLIC_VERSION},
        )
    else:
        versions_match = installed_version == PUBLIC_VERSION
        add_check(
            "package.metadata",
            "package",
            "pass" if versions_match else "fail",
            (
                "Package and distribution versions agree."
                if versions_match
                else "Package and distribution versions disagree."
            ),
            action=(
                None
                if versions_match
                else "Reinstall gex-terminal in the active Python environment."
            ),
            details={
                "application_version": PUBLIC_VERSION,
                "distribution_version": installed_version,
            },
            failure_code=EXIT_RUNTIME_FAILURE,
        )

    missing_required = [
        display_name
        for display_name, module_name in REQUIRED_RUNTIME_MODULES
        if not module_spec_present(module_name, find_spec=spec_lookup)
    ]
    add_check(
        "package.required_modules",
        "package",
        "pass" if not missing_required else "fail",
        (
            "All required runtime modules are discoverable."
            if not missing_required
            else "One or more required runtime modules are unavailable."
        ),
        action=(
            None
            if not missing_required
            else "Reinstall gex-terminal with its required dependencies."
        ),
        details={
            "required": [name for name, _module in REQUIRED_RUNTIME_MODULES],
            "missing": missing_required,
        },
        failure_code=EXIT_RUNTIME_FAILURE,
    )

    missing_resources = [
        resource
        for resource in REQUIRED_BUNDLED_RESOURCES
        if not safe_resource_exists(resource, resource_exists=resource_lookup)
    ]
    add_check(
        "package.bundled_resources",
        "package",
        "pass" if not missing_resources else "fail",
        (
            "All declared bundled resources are available."
            if not missing_resources
            else "One or more declared bundled resources are unavailable."
        ),
        action=(
            None
            if not missing_resources
            else "Reinstall the complete gex-terminal package."
        ),
        details={
            "expected_count": len(REQUIRED_BUNDLED_RESOURCES),
            "available_count": len(REQUIRED_BUNDLED_RESOURCES) - len(missing_resources),
            "missing": missing_resources,
        },
        failure_code=EXIT_RUNTIME_FAILURE,
    )

    try:
        hidden_result = dict(hidden_lookup())
    except Exception:
        hidden_result = {"supported": False, "hidden_count": 0, "probe_failed": True}
    hidden_count = _safe_non_negative_int(hidden_result.get("hidden_count"))
    hidden_probe_failed = bool(hidden_result.get("probe_failed", False))
    if hidden_probe_failed:
        add_check(
            "runtime.editable_pth_visibility",
            "runtime",
            "warning",
            "Editable-install visibility could not be inspected.",
            action=(
                "If the console launcher fails, install the reviewed wheel in a "
                "dedicated virtual environment."
            ),
            details={"hidden_count": 0},
        )
    elif hidden_count:
        add_check(
            "runtime.editable_pth_visibility",
            "runtime",
            "warning",
            "A hidden gex-terminal editable .pth file can be skipped by Python.",
            action=(
                "Clear the hidden flag only on the gex-terminal editable .pth file; "
                "if it recurs, install the reviewed wheel in a dedicated virtual "
                "environment."
            ),
            details={"hidden_count": hidden_count},
        )
    else:
        add_check(
            "runtime.editable_pth_visibility",
            "runtime",
            "pass",
            (
                "No hidden gex-terminal editable .pth file was detected."
                if hidden_result.get("supported", False)
                else "Hidden editable .pth flags are not exposed on this platform."
            ),
            details={
                "hidden_count": 0,
                "platform_flag_supported": bool(hidden_result.get("supported", False)),
            },
        )

    try:
        logging_valid = bool(logging_lookup())
    except Exception:
        logging_valid = False
    add_check(
        "configuration.logging",
        "configuration",
        "pass" if logging_valid else "fail",
        (
            "Logging configuration is valid."
            if logging_valid
            else "Logging configuration is invalid."
        ),
        action=(
            None
            if logging_valid
            else "Choose DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        ),
        details={"value_disclosed": False},
        failure_code=EXIT_CONFIGURATION_FAILURE,
    )

    resolved_config = config
    resolved_config_error = config_error
    if resolved_config is None and resolved_config_error is None:
        try:
            resolved_config = GexConfig.from_env()
        except ConfigValidationError as exc:
            resolved_config_error = exc

    if resolved_config_error is not None:
        safe_error = safe_config_error(resolved_config_error)
        add_check(
            "configuration.shape",
            "configuration",
            "fail",
            f"Configuration is invalid: {safe_error}",
            action="Review the documented environment and numeric constraints.",
            details={"fields": [], "values_disclosed": False},
            failure_code=EXIT_CONFIGURATION_FAILURE,
        )
    elif resolved_config is None:
        add_check(
            "configuration.shape",
            "configuration",
            "fail",
            "Configuration could not be constructed.",
            action="Review the documented environment settings.",
            details={"fields": [], "values_disclosed": False},
            failure_code=EXIT_CONFIGURATION_FAILURE,
        )
    else:
        add_check(
            "configuration.shape",
            "configuration",
            "pass",
            "Configuration passed validation; values are intentionally omitted.",
            details={
                "fields": config_shape(resolved_config),
                "values_disclosed": False,
            },
        )

    try:
        catalog = {
            str(name): str(readiness)
            for name, readiness in dict(catalog_lookup()).items()
            if str(readiness) in PROVIDER_READINESS_STATES
        }
        catalog_failed = False
    except Exception:
        catalog = {}
        catalog_failed = True

    sdk_presence = {
        provider: module_spec_present(module, find_spec=spec_lookup)
        for provider, (module, _extra) in OPTIONAL_PROVIDER_SDKS.items()
    }
    selection = evaluate_provider_selection(
        resolved_config,
        catalog=catalog,
        sdk_presence=sdk_presence,
        replay_readable=replay_lookup,
        config_valid=resolved_config_error is None,
        catalog_failed=catalog_failed,
    )
    add_check(
        "provider.selection",
        "provider",
        selection["status"],
        selection["summary"],
        action=selection.get("action"),
        details=selection.get("details"),
        failure_code=(
            EXIT_RUNTIME_FAILURE if catalog_failed else EXIT_CONFIGURATION_FAILURE
        ),
    )

    selected_provider = selection.get("selected_provider")
    for provider, (_module, extra) in OPTIONAL_PROVIDER_SDKS.items():
        present = sdk_presence[provider]
        selected = selected_provider == provider
        if present:
            status = "pass"
            summary = f"The {provider} optional SDK is discoverable."
            action = None
        elif selected:
            status = "fail"
            summary = f"The selected {provider} optional SDK is unavailable."
            action = f'Install the provider extra with: pip install "gex-terminal[{extra}]"'
        else:
            status = "warning"
            summary = f"The unselected {provider} optional SDK is not installed."
            action = f'Install only if needed: pip install "gex-terminal[{extra}]"'
        add_check(
            f"provider.sdk.{provider}",
            "provider",
            status,
            summary,
            action=action,
            details={"provider": provider, "present": present, "selected": selected},
            failure_code=EXIT_CONFIGURATION_FAILURE,
        )

    add_check(
        "provider.live_access",
        "provider",
        "unverified",
        "Authentication, entitlements, capacity, and live transport were not tested.",
        details={
            "authentication": "unverified",
            "entitlements": "unverified",
            "provider_capacity": "unverified",
            "live_transport": "unverified",
        },
    )

    try:
        storage_result = dict(storage_lookup())
    except Exception:
        storage_result = {"ok": False, "artifact_removed": True}
    storage_ok = bool(storage_result.get("ok", False))
    artifact_removed = bool(storage_result.get("artifact_removed", False))
    add_check(
        "storage.temporary_round_trip",
        "storage",
        "pass" if storage_ok and artifact_removed else "fail",
        (
            "Temporary storage round-trip succeeded and its probe was removed."
            if storage_ok and artifact_removed
            else "Temporary storage round-trip or cleanup failed."
        ),
        action=(
            None
            if storage_ok and artifact_removed
            else "Verify that the operating-system temporary directory is writable."
        ),
        details={
            "round_trip": storage_ok,
            "artifact_removed": artifact_removed,
        },
        failure_code=EXIT_RUNTIME_FAILURE,
    )

    exit_code = doctor_exit_code(failure_codes)
    counts = {
        status: sum(1 for check in checks if check["status"] == status)
        for status in ("pass", "warning", "fail", "unverified")
    }
    if exit_code:
        overall_status = "fail"
    elif counts["warning"]:
        overall_status = "warning"
    else:
        overall_status = "pass"

    return {
        "schema": DOCTOR_SCHEMA,
        "generated_at": safe_generated_at(generated_at),
        "application": {"name": "gex-terminal", "version": PUBLIC_VERSION},
        "execution": {
            "network_used": False,
            "live_adapter_constructed": False,
            "optional_sdk_imported": False,
            "persistent_state_created": not artifact_removed,
            "sensitive_values_included": False,
        },
        "checks": checks,
        "summary": {
            "status": overall_status,
            "exit_code": exit_code,
            "counts": counts,
        },
        "evidence_ceiling": (
            "Local preflight only; provider authentication, entitlements, capacity, "
            "live transport, market-data quality, and predictive validity are unverified."
        ),
    }


def doctor_report_to_text(report: Mapping[str, Any]) -> str:
    """Render a doctor report without adding environment-derived content."""
    summary = report["summary"]
    lines = [
        "gex-terminal doctor",
        f"Result: {str(summary['status']).upper()} (exit {summary['exit_code']})",
        "Offline preflight: no network, live adapter, or optional SDK import.",
        "",
    ]
    labels = {
        "pass": "PASS",
        "warning": "WARN",
        "fail": "FAIL",
        "unverified": "UNVERIFIED",
    }
    for check in report["checks"]:
        lines.append(f"[{labels[check['status']]}] {check['id']}: {check['summary']}")
        if check.get("action"):
            lines.append(f"  Action: {check['action']}")
    lines.extend(("", f"Evidence ceiling: {report['evidence_ceiling']}"))
    return "\n".join(lines)


def doctor_report_to_json(report: Mapping[str, Any]) -> str:
    """Render the versioned doctor report for automation and support reuse."""
    return json.dumps(report, indent=2, sort_keys=True)


def doctor_exit_code(failure_codes: list[int]) -> int:
    """Return the most fundamental failure class for process automation."""
    if EXIT_RUNTIME_FAILURE in failure_codes:
        return EXIT_RUNTIME_FAILURE
    if EXIT_CONFIGURATION_FAILURE in failure_codes:
        return EXIT_CONFIGURATION_FAILURE
    return EXIT_OK


def module_spec_present(
    module_name: str,
    *,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> bool:
    """Check discoverability without importing the target module."""
    try:
        return find_spec(module_name) is not None
    except Exception:
        return False


def bundled_resource_exists(resource: str) -> bool:
    """Check a stable package-relative resource identifier."""
    try:
        candidate = importlib.resources.files("gex_terminal")
        for part in resource.split("/"):
            candidate = candidate.joinpath(part)
        return candidate.is_file()
    except Exception:
        return False


def safe_resource_exists(
    resource: str,
    *,
    resource_exists: Callable[[str], bool],
) -> bool:
    try:
        return bool(resource_exists(resource))
    except Exception:
        return False


def probe_temporary_storage(
    *,
    parent: str | os.PathLike[str] | None = None,
    directory_factory: Callable[..., Any] = tempfile.TemporaryDirectory,
) -> dict[str, bool]:
    """Round-trip a fixed payload in a self-owned temporary directory."""
    directory_name: str | None = None
    artifact_removed = True
    round_trip = False
    try:
        options: dict[str, Any] = {"prefix": "gex-terminal-doctor-"}
        if parent is not None:
            options["dir"] = parent
        with directory_factory(**options) as temporary_directory:
            directory_name = str(temporary_directory)
            probe = Path(temporary_directory) / "probe"
            probe.write_bytes(b"gex-terminal-doctor")
            round_trip = probe.read_bytes() == b"gex-terminal-doctor"
            probe.unlink()
            artifact_removed = not probe.exists()
        if directory_name is not None:
            artifact_removed = artifact_removed and not Path(directory_name).exists()
    except Exception:
        round_trip = False
        if directory_name is not None:
            artifact_removed = not Path(directory_name).exists()
    return {"ok": round_trip, "artifact_removed": artifact_removed}


def probe_hidden_editable_pth(
    *,
    site_directories: tuple[str, ...] | None = None,
    flag_reader: Callable[[Path], int] | None = None,
    hidden_flag: int | None = None,
) -> dict[str, Any]:
    """Count hidden editable path files without returning their locations."""
    flag = getattr(stat, "UF_HIDDEN", 0) if hidden_flag is None else hidden_flag
    if not flag:
        return {"supported": False, "hidden_count": 0}

    directories = site_directories or _site_directories()
    read_flags = flag_reader or _filesystem_flags
    hidden_count = 0
    seen: set[str] = set()
    for directory in directories:
        if directory in seen:
            continue
        seen.add(directory)
        try:
            candidates = tuple(Path(directory).glob("*.pth"))
        except OSError:
            continue
        for candidate in candidates:
            normalized_name = candidate.name.lower().replace("-", "_")
            if "gex_terminal" not in normalized_name or "editable" not in normalized_name:
                continue
            try:
                if read_flags(candidate) & flag:
                    hidden_count += 1
            except OSError:
                continue
    return {"supported": True, "hidden_count": hidden_count}


def load_provider_catalog() -> dict[str, str]:
    """Load provider metadata only; adapter builders are never called."""
    from gex_terminal.adapters.registry import ADAPTER_INFOS

    return {name: info.status for name, info in ADAPTER_INFOS.items()}


def logging_configuration_valid() -> bool:
    """Validate logging configuration without returning the configured value."""
    from gex_terminal.logging_config import resolve_log_level

    try:
        resolve_log_level(environ=os.environ)
    except ValueError:
        return False
    return True


def evaluate_provider_selection(
    config: GexConfig | None,
    *,
    catalog: Mapping[str, str],
    sdk_presence: Mapping[str, bool],
    replay_readable: Callable[[str], bool],
    config_valid: bool,
    catalog_failed: bool,
) -> dict[str, Any]:
    """Classify selected-path runnability without validating or constructing it."""
    if catalog_failed:
        return {
            "status": "fail",
            "summary": "Provider metadata could not be loaded.",
            "action": "Reinstall the complete gex-terminal package.",
            "details": {"selected_provider": "unavailable", "readiness": "unavailable"},
            "selected_provider": None,
        }
    if not config_valid or config is None:
        return {
            "status": "unverified",
            "summary": "Provider selection was not evaluated because configuration is invalid.",
            "details": {"selected_provider": "unverified", "readiness": "unverified"},
            "selected_provider": None,
        }

    mode = str(config.data_mode).lower()
    configured_provider = str(config.data_provider).lower()
    if mode not in {"demo", "replay", "live"}:
        return {
            "status": "fail",
            "summary": "Configured data mode is unsupported.",
            "action": "Choose demo, replay, or live mode.",
            "details": {"mode": "unsupported", "selected_provider": "unavailable"},
            "selected_provider": None,
        }

    if mode == "replay":
        selected_provider = "replay"
    elif mode == "demo":
        selected_provider = "demo"
    else:
        selected_provider = configured_provider

    if mode != "replay" and configured_provider not in catalog:
        return {
            "status": "fail",
            "summary": "Configured provider is unsupported.",
            "action": "Choose a provider reported by gex-terminal --providers.",
            "details": {"mode": mode, "selected_provider": "unsupported"},
            "selected_provider": None,
        }

    if mode == "demo":
        return {
            "status": "pass",
            "summary": "Seeded demo mode is structurally runnable offline.",
            "details": {
                "mode": "demo",
                "selected_provider": "demo",
                "readiness": "offline-certified",
            },
            "selected_provider": "demo",
        }

    if mode == "replay":
        try:
            readable = bool(replay_readable(config.replay_path))
        except Exception:
            readable = False
        if not readable:
            return {
                "status": "fail",
                "summary": "Configured replay source is not readable.",
                "action": "Choose an existing readable replay or bundled replay session.",
                "details": {
                    "mode": "replay",
                    "selected_provider": "replay",
                    "readiness": catalog.get("replay", "unavailable"),
                },
                "selected_provider": "replay",
            }
        return {
            "status": "pass",
            "summary": "Replay mode is structurally runnable offline.",
            "details": {
                "mode": "replay",
                "selected_provider": "replay",
                "readiness": catalog.get("replay", "unavailable"),
            },
            "selected_provider": "replay",
        }

    readiness = catalog[selected_provider]
    details = {
        "mode": "live",
        "selected_provider": selected_provider,
        "readiness": readiness,
    }
    if selected_provider == "replay":
        return {
            "status": "fail",
            "summary": "Replay provider requires replay mode.",
            "action": "Select replay mode for a replay source.",
            "details": details,
            "selected_provider": selected_provider,
        }
    if readiness == "scaffold":
        return {
            "status": "fail",
            "summary": "Selected live provider remains a non-runnable scaffold.",
            "action": "Choose an implemented path or continue with demo/replay.",
            "details": details,
            "selected_provider": selected_provider,
        }
    if selected_provider in sdk_presence and not sdk_presence[selected_provider]:
        return {
            "status": "fail",
            "summary": "Selected live provider is missing its optional SDK.",
            "action": "Install the provider extra reported below.",
            "details": details,
            "selected_provider": selected_provider,
        }
    if not provider_instrument_supported(selected_provider, config.symbol):
        return {
            "status": "fail",
            "summary": "Selected provider does not support the configured instrument class.",
            "action": "Choose a compatible provider/instrument combination.",
            "details": details,
            "selected_provider": selected_provider,
        }
    return {
        "status": "warning",
        "summary": "Selected provider is structurally runnable; live access remains unverified.",
        "details": details,
        "selected_provider": selected_provider,
    }


def provider_instrument_supported(provider: str, symbol: str) -> bool:
    normalized_symbol = str(symbol).strip().upper()
    if provider == "databento":
        return normalized_symbol in {"ES", "NQ"}
    if provider == "yfinance":
        return normalized_symbol not in {"ES", "MES", "NQ", "MNQ"}
    return True


def configured_replay_is_readable(value: str) -> bool:
    """Open a configured replay without reading or reporting its contents/path."""
    if not value:
        return False
    try:
        with Path(value).open("rb"):
            return True
    except (OSError, TypeError, ValueError):
        return False


def config_shape(config: GexConfig) -> list[dict[str, str]]:
    if not is_dataclass(config):
        return []
    return [
        {"name": field.name, "type": type(getattr(config, field.name)).__name__}
        for field in fields(config)
    ]


def safe_config_error(exc: ConfigValidationError) -> str:
    """Allow only known field/constraint text from the config boundary."""
    try:
        message = str(exc)
    except Exception:
        return "a configuration field failed validation"
    for field_name in sorted(_SAFE_CONFIG_FIELDS, key=len, reverse=True):
        prefix = f"{field_name} must be "
        if not message.startswith(prefix):
            continue
        constraint = message[len(prefix):]
        if constraint in _SAFE_CONFIG_CONSTRAINTS:
            return message
    return "a configuration field failed validation"


def _site_directories() -> tuple[str, ...]:
    discovered: list[str] = []
    try:
        discovered.extend(site.getsitepackages())
    except (AttributeError, OSError):
        pass
    try:
        user_site = site.getusersitepackages()
    except (AttributeError, OSError):
        user_site = None
    if isinstance(user_site, str):
        discovered.append(user_site)
    elif user_site:
        discovered.extend(str(path) for path in user_site)
    return tuple(discovered)


def _filesystem_flags(path: Path) -> int:
    return int(getattr(path.stat(), "st_flags", 0))


def _safe_non_negative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def safe_public_version(value: Any) -> str | None:
    candidate = str(value)
    return candidate if _SAFE_VERSION.fullmatch(candidate) else None


def safe_generated_at(value: str | None) -> str:
    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        return value
    return _utc_now()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main_sync(argv: list[str] | None = None) -> None:
    """Minimal module entry point for diagnosis when the main CLI cannot import."""
    parser = _DoctorArgumentParser(description="Offline gex-terminal preflight")
    parser.add_argument("--json", action="store_true", help="Print versioned JSON.")
    args = parser.parse_args(argv)
    try:
        report = build_doctor_report()
    except Exception:
        report = _internal_failure_report()
    print(doctor_report_to_json(report) if args.json else doctor_report_to_text(report))
    raise SystemExit(int(report["summary"]["exit_code"]))


class _DoctorArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        super().error("invalid arguments; use --help to see supported values")


def _internal_failure_report() -> dict[str, Any]:
    """Return a last-resort fixed failure without serializing exception content."""
    return {
        "schema": DOCTOR_SCHEMA,
        "generated_at": _utc_now(),
        "application": {"name": "gex-terminal", "version": PUBLIC_VERSION},
        "execution": {
            "network_used": False,
            "live_adapter_constructed": False,
            "optional_sdk_imported": False,
            "persistent_state_created": False,
            "sensitive_values_included": False,
        },
        "checks": [
            {
                "id": "doctor.internal",
                "category": "runtime",
                "status": "fail",
                "summary": "Doctor could not complete its local checks.",
                "action": "Reinstall gex-terminal and rerun the offline doctor.",
            }
        ],
        "summary": {
            "status": "fail",
            "exit_code": EXIT_RUNTIME_FAILURE,
            "counts": {"pass": 0, "warning": 0, "fail": 1, "unverified": 0},
        },
        "evidence_ceiling": (
            "Local preflight only; provider authentication, entitlements, capacity, "
            "live transport, market-data quality, and predictive validity are unverified."
        ),
    }


if __name__ == "__main__":
    main_sync()

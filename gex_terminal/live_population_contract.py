"""Offline contracts for a preregistered Databento ES observation population.

This module validates local JSON only.  It deliberately contains no adapter,
credential, scheduling, capture, or network integration.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from numbers import Real
from pathlib import Path
from typing import Any

from gex_terminal.databento_certification_policy import (
    ES_PRELIVE_V1,
    certification_policy_identity,
)


LIVE_POPULATION_PLAN_SCHEMA = (
    "gex-terminal.databento-live-population-plan.v1"
)
LIVE_POPULATION_RESULT_SCHEMA = (
    "gex-terminal.databento-live-population-results.v1"
)
LIVE_POPULATION_PLAN_IDENTITY_SCHEMA = (
    "gex-terminal.databento-live-population-plan-identity.v1"
)
LIVE_POPULATION_RESULT_IDENTITY_SCHEMA = (
    "gex-terminal.databento-live-population-results-identity.v1"
)
LIVE_POPULATION_CANONICALIZATION = "gex-terminal.canonical-json.v1"
LIVE_POPULATION_EVIDENCE_CEILING = (
    "offline structural validation only; no execution authority, live-provider "
    "observation, report-authenticity, provider-readiness, predictive, execution, "
    "or profitability claim"
)

PLANNED_SLOT_COUNT = 12
PLANNED_SLOT_DURATION = timedelta(minutes=20)
WINDOW_TYPES = ("regular_open", "midday", "regular_close", "globex")
CALENDAR_CONTEXTS = ("ordinary", "scheduled_event", "other")
OBSERVATION_OUTCOMES = (
    "passed",
    "authentication_failure",
    "entitlement_failure",
    "policy_failure",
    "payload_failure",
    "temporal_failure",
    "lifecycle_failure",
    "operator_interruption",
    "environment_failure",
    "missed",
)

_PLAN_FIELDS = frozenset(
    {
        "schema",
        "canonicalization",
        "population_id",
        "target",
        "certification_policy",
        "runtime",
        "authority",
        "timing",
        "lineage",
        "coverage_limitations",
        "planned_slots",
        "evidence_ceiling",
    }
)
_TARGET_FIELDS = frozenset(
    {"provider", "dataset", "symbol", "canonical_contract_multiplier"}
)
_POLICY_IDENTITY_FIELDS = frozenset(
    {
        "schema",
        "canonicalization",
        "policy_schema",
        "policy_id",
        "policy_version",
        "sha256",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "gex_terminal_version",
        "python_version",
        "provider_sdk_version",
        "operating_system",
        "architecture",
    }
)
_AUTHORITY_FIELDS = frozenset(
    {
        "operator_alias",
        "reviewer_alias",
        "approval_reference",
        "entitlement_scope",
        "rights_reference",
        "retention_reference",
        "read_only_provider_access",
        "raw_capture",
    }
)
_TIMING_FIELDS = frozenset(
    {
        "timezone",
        "clock_source",
        "exchange_calendar_source",
        "stale_response",
    }
)
_LINEAGE_FIELDS = frozenset(
    {"status", "prior_population_id", "prior_result_manifest_sha256"}
)
_SLOT_FIELDS = frozenset(
    {
        "run_id",
        "window",
        "trading_date",
        "start_utc",
        "end_utc",
        "calendar_context",
        "restart_observation",
    }
)
_PLAN_IDENTITY_FIELDS = frozenset(
    {"schema", "canonicalization", "plan_schema", "population_id", "sha256"}
)
_RESULT_FIELDS = frozenset(
    {
        "schema",
        "canonicalization",
        "plan_identity",
        "observations",
        "evidence_ceiling",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "run_id",
        "outcome",
        "actual_start_utc",
        "actual_stop_utc",
        "runtime",
        "certification_policy_sha256",
        "report",
        "redacted_notes",
    }
)
_REPORT_FIELDS = frozenset({"status", "sha256"})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.+_-]*)?$")
_UTC_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:00Z$")
_OBSERVED_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_MAX_JSON_BYTES = 1_000_000


class LivePopulationContractError(ValueError):
    """Raised when a live-observation preparation artifact is unsupported."""


def load_live_population_plan(path: str | Path) -> dict[str, Any]:
    """Load and strictly validate one local population-plan JSON file."""
    return validate_live_population_plan(_load_json_object(path, "population plan"))


def validate_live_population_plan(value: Any) -> dict[str, Any]:
    """Return the canonical representation of one complete ES population plan."""
    plan = _required_mapping(value, "population plan")
    _require_fields(plan, _PLAN_FIELDS, "population plan")
    if plan.get("schema") != LIVE_POPULATION_PLAN_SCHEMA:
        raise LivePopulationContractError("population plan schema is unsupported")
    if plan.get("canonicalization") != LIVE_POPULATION_CANONICALIZATION:
        raise LivePopulationContractError(
            "population plan canonicalization is unsupported"
        )
    if plan.get("evidence_ceiling") != LIVE_POPULATION_EVIDENCE_CEILING:
        raise LivePopulationContractError(
            "population plan evidence ceiling is unsupported"
        )

    population_id = _required_identifier(
        plan.get("population_id"), "population plan population_id"
    )
    target = _validate_target(plan.get("target"))
    policy_identity = _validate_policy_identity(plan.get("certification_policy"))
    runtime = _validate_runtime(plan.get("runtime"), "population plan runtime")
    authority = _validate_authority(plan.get("authority"))
    timing = _validate_timing(plan.get("timing"))
    lineage = _validate_lineage(plan.get("lineage"), population_id)
    limitations = _validate_limitations(plan.get("coverage_limitations"))
    slots = _validate_slots(plan.get("planned_slots"))

    return {
        "schema": LIVE_POPULATION_PLAN_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "population_id": population_id,
        "target": target,
        "certification_policy": policy_identity,
        "runtime": runtime,
        "authority": authority,
        "timing": timing,
        "lineage": lineage,
        "coverage_limitations": limitations,
        "planned_slots": slots,
        "evidence_ceiling": LIVE_POPULATION_EVIDENCE_CEILING,
    }


def live_population_plan_identity(value: Any) -> dict[str, str]:
    """Hash the complete normalized plan without excluding any field."""
    plan = validate_live_population_plan(value)
    return {
        "schema": LIVE_POPULATION_PLAN_IDENTITY_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "plan_schema": LIVE_POPULATION_PLAN_SCHEMA,
        "population_id": plan["population_id"],
        "sha256": _canonical_sha256(plan),
    }


def load_live_population_result_manifest(
    plan_path: str | Path,
    result_path: str | Path,
) -> dict[str, Any]:
    """Load and cross-validate a local result manifest against its frozen plan."""
    plan = load_live_population_plan(plan_path)
    result = _load_json_object(result_path, "population result manifest")
    return validate_live_population_result_manifest(plan, result)


def validate_live_population_result_manifest(
    plan_value: Any,
    result_value: Any,
) -> dict[str, Any]:
    """Validate complete observed outcomes against one exact frozen plan."""
    plan = validate_live_population_plan(plan_value)
    result = _required_mapping(result_value, "population result manifest")
    _require_fields(result, _RESULT_FIELDS, "population result manifest")
    if result.get("schema") != LIVE_POPULATION_RESULT_SCHEMA:
        raise LivePopulationContractError(
            "population result manifest schema is unsupported"
        )
    if result.get("canonicalization") != LIVE_POPULATION_CANONICALIZATION:
        raise LivePopulationContractError(
            "population result manifest canonicalization is unsupported"
        )
    if result.get("evidence_ceiling") != LIVE_POPULATION_EVIDENCE_CEILING:
        raise LivePopulationContractError(
            "population result manifest evidence ceiling is unsupported"
        )

    expected_plan_identity = live_population_plan_identity(plan)
    supplied_plan_identity = _validate_plan_identity(result.get("plan_identity"))
    if not _constant_time_mapping_equal(
        supplied_plan_identity, expected_plan_identity
    ):
        raise LivePopulationContractError(
            "population result manifest does not match the frozen plan identity"
        )

    raw_observations = result.get("observations")
    if not isinstance(raw_observations, list):
        raise LivePopulationContractError(
            "population result observations must be a JSON array"
        )
    if len(raw_observations) != PLANNED_SLOT_COUNT:
        raise LivePopulationContractError(
            "population result manifest must contain all 12 planned runs"
        )

    planned_slots = plan["planned_slots"]
    observations = [
        _validate_observation(raw, planned, plan)
        for raw, planned in zip(raw_observations, planned_slots, strict=True)
    ]
    observed_ids = [item["run_id"] for item in observations]
    planned_ids = [item["run_id"] for item in planned_slots]
    if observed_ids != planned_ids:
        raise LivePopulationContractError(
            "population result runs must exactly match planned run IDs and order"
        )

    return {
        "schema": LIVE_POPULATION_RESULT_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "plan_identity": supplied_plan_identity,
        "observations": observations,
        "evidence_ceiling": LIVE_POPULATION_EVIDENCE_CEILING,
    }


def live_population_result_identity(
    plan_value: Any,
    result_value: Any,
) -> dict[str, str]:
    """Hash every normalized field of a validated observed-result manifest."""
    result = validate_live_population_result_manifest(plan_value, result_value)
    return {
        "schema": LIVE_POPULATION_RESULT_IDENTITY_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "plan_sha256": result["plan_identity"]["sha256"],
        "population_id": result["plan_identity"]["population_id"],
        "sha256": _canonical_sha256(result),
    }


def _validate_target(value: Any) -> dict[str, Any]:
    target = _required_mapping(value, "population plan target")
    _require_fields(target, _TARGET_FIELDS, "population plan target")
    multiplier = _finite_number(
        target.get("canonical_contract_multiplier"),
        "population plan canonical_contract_multiplier",
    )
    expected = {
        "provider": ES_PRELIVE_V1.provider,
        "dataset": ES_PRELIVE_V1.dataset,
        "symbol": ES_PRELIVE_V1.symbol,
        "canonical_contract_multiplier": float(
            ES_PRELIVE_V1.canonical_contract_multiplier
        ),
    }
    supplied = {
        "provider": target.get("provider"),
        "dataset": target.get("dataset"),
        "symbol": target.get("symbol"),
        "canonical_contract_multiplier": multiplier,
    }
    if supplied != expected:
        raise LivePopulationContractError(
            "population plan target must match the canonical Databento ES target"
        )
    return expected


def _validate_policy_identity(value: Any) -> dict[str, str | int]:
    identity = _required_mapping(value, "population plan certification_policy")
    _require_fields(
        identity,
        _POLICY_IDENTITY_FIELDS,
        "population plan certification_policy",
    )
    sha256 = _required_sha256(
        identity.get("sha256"), "population plan certification policy sha256"
    )
    supplied = {
        "schema": identity.get("schema"),
        "canonicalization": identity.get("canonicalization"),
        "policy_schema": identity.get("policy_schema"),
        "policy_id": identity.get("policy_id"),
        "policy_version": identity.get("policy_version"),
        "sha256": sha256,
    }
    expected = certification_policy_identity(ES_PRELIVE_V1)
    if not _constant_time_mapping_equal(supplied, expected):
        raise LivePopulationContractError(
            "population plan certification policy identity does not match the "
            "registered Databento ES policy"
        )
    return expected


def _validate_runtime(value: Any, label: str) -> dict[str, str]:
    runtime = _required_mapping(value, label)
    _require_fields(runtime, _RUNTIME_FIELDS, label)
    return {
        "gex_terminal_version": _required_version(
            runtime.get("gex_terminal_version"), f"{label} gex_terminal_version"
        ),
        "python_version": _required_version(
            runtime.get("python_version"), f"{label} python_version"
        ),
        "provider_sdk_version": _required_version(
            runtime.get("provider_sdk_version"), f"{label} provider_sdk_version"
        ),
        "operating_system": _required_decision_text(
            runtime.get("operating_system"), f"{label} operating_system"
        ),
        "architecture": _required_decision_text(
            runtime.get("architecture"), f"{label} architecture"
        ),
    }


def _validate_authority(value: Any) -> dict[str, Any]:
    authority = _required_mapping(value, "population plan authority")
    _require_fields(authority, _AUTHORITY_FIELDS, "population plan authority")
    if authority.get("read_only_provider_access") is not True:
        raise LivePopulationContractError(
            "population plan requires explicit read-only provider access"
        )
    if authority.get("raw_capture") is not False:
        raise LivePopulationContractError(
            "population plan raw_capture must be false; capture needs separate authority"
        )
    return {
        "operator_alias": _required_identifier(
            authority.get("operator_alias"), "population plan operator_alias"
        ),
        "reviewer_alias": _required_identifier(
            authority.get("reviewer_alias"), "population plan reviewer_alias"
        ),
        "approval_reference": _required_decision_text(
            authority.get("approval_reference"), "population plan approval_reference"
        ),
        "entitlement_scope": _required_decision_text(
            authority.get("entitlement_scope"), "population plan entitlement_scope"
        ),
        "rights_reference": _required_decision_text(
            authority.get("rights_reference"), "population plan rights_reference"
        ),
        "retention_reference": _required_decision_text(
            authority.get("retention_reference"), "population plan retention_reference"
        ),
        "read_only_provider_access": True,
        "raw_capture": False,
    }


def _validate_timing(value: Any) -> dict[str, str]:
    timing = _required_mapping(value, "population plan timing")
    _require_fields(timing, _TIMING_FIELDS, "population plan timing")
    if timing.get("timezone") != "UTC":
        raise LivePopulationContractError("population plan timezone must be UTC")
    return {
        "timezone": "UTC",
        "clock_source": _required_decision_text(
            timing.get("clock_source"), "population plan clock_source"
        ),
        "exchange_calendar_source": _required_decision_text(
            timing.get("exchange_calendar_source"),
            "population plan exchange_calendar_source",
        ),
        "stale_response": _required_decision_text(
            timing.get("stale_response"), "population plan stale_response"
        ),
    }


def _validate_lineage(value: Any, population_id: str) -> dict[str, Any]:
    lineage = _required_mapping(value, "population plan lineage")
    _require_fields(lineage, _LINEAGE_FIELDS, "population plan lineage")
    status = lineage.get("status")
    prior_id = lineage.get("prior_population_id")
    prior_sha256 = lineage.get("prior_result_manifest_sha256")
    if status == "first_population":
        if prior_id is not None or prior_sha256 is not None:
            raise LivePopulationContractError(
                "first population lineage requires null prior identity fields"
            )
        return {
            "status": "first_population",
            "prior_population_id": None,
            "prior_result_manifest_sha256": None,
        }
    if status != "successor_population":
        raise LivePopulationContractError("population plan lineage status is unsupported")
    normalized_prior_id = _required_identifier(
        prior_id, "population plan prior_population_id"
    )
    if normalized_prior_id == population_id:
        raise LivePopulationContractError(
            "successor population must reference a different prior population"
        )
    return {
        "status": "successor_population",
        "prior_population_id": normalized_prior_id,
        "prior_result_manifest_sha256": _required_sha256(
            prior_sha256, "population plan prior_result_manifest_sha256"
        ),
    }


def _validate_limitations(value: Any) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise LivePopulationContractError(
            "population plan coverage_limitations must contain 1-20 entries"
        )
    return [
        _required_decision_text(item, "population plan coverage limitation")
        for item in value
    ]


def _validate_slots(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != PLANNED_SLOT_COUNT:
        raise LivePopulationContractError(
            "population plan must contain exactly 12 planned slots"
        )
    normalized: list[dict[str, Any]] = []
    parsed: list[tuple[datetime, datetime]] = []
    for raw in value:
        slot = _required_mapping(raw, "population plan slot")
        _require_fields(slot, _SLOT_FIELDS, "population plan slot")
        run_id = _required_identifier(slot.get("run_id"), "population plan run_id")
        window = slot.get("window")
        if window not in WINDOW_TYPES:
            raise LivePopulationContractError("population plan slot window is unsupported")
        trading_date = _required_date(
            slot.get("trading_date"), "population plan trading_date"
        )
        start_text, start = _required_utc_timestamp(
            slot.get("start_utc"), "population plan start_utc"
        )
        end_text, end = _required_utc_timestamp(
            slot.get("end_utc"), "population plan end_utc"
        )
        if end - start != PLANNED_SLOT_DURATION:
            raise LivePopulationContractError(
                "every population plan slot must be exactly 20 minutes"
            )
        context = slot.get("calendar_context")
        if context not in CALENDAR_CONTEXTS:
            raise LivePopulationContractError(
                "population plan slot calendar_context is unsupported"
            )
        restart = slot.get("restart_observation")
        if not isinstance(restart, bool):
            raise LivePopulationContractError(
                "population plan restart_observation must be boolean"
            )
        normalized.append(
            {
                "run_id": run_id,
                "window": window,
                "trading_date": trading_date,
                "start_utc": start_text,
                "end_utc": end_text,
                "calendar_context": context,
                "restart_observation": restart,
            }
        )
        parsed.append((start, end))

    run_ids = [slot["run_id"] for slot in normalized]
    if len(set(run_ids)) != PLANNED_SLOT_COUNT:
        raise LivePopulationContractError("population plan run IDs must be unique")
    if parsed != sorted(parsed):
        raise LivePopulationContractError(
            "population plan slots must be ordered by start_utc"
        )
    for (_, earlier_end), (later_start, _) in zip(parsed, parsed[1:]):
        if later_start < earlier_end:
            raise LivePopulationContractError(
                "population plan slots must not overlap"
            )

    window_counts = Counter(slot["window"] for slot in normalized)
    if any(window_counts[window] != 3 for window in WINDOW_TYPES):
        raise LivePopulationContractError(
            "population plan requires three slots for each window type"
        )
    if len({slot["trading_date"] for slot in normalized}) < 4:
        raise LivePopulationContractError(
            "population plan requires at least four trading dates"
        )
    restart_dates = {
        slot["trading_date"]
        for slot in normalized
        if slot["restart_observation"]
    }
    restart_count = sum(slot["restart_observation"] for slot in normalized)
    if restart_count != 2 or len(restart_dates) != 2:
        raise LivePopulationContractError(
            "population plan requires two restart observations on distinct dates"
        )
    return normalized


def _validate_plan_identity(value: Any) -> dict[str, str]:
    identity = _required_mapping(value, "population result plan_identity")
    _require_fields(identity, _PLAN_IDENTITY_FIELDS, "population result plan_identity")
    if identity.get("schema") != LIVE_POPULATION_PLAN_IDENTITY_SCHEMA:
        raise LivePopulationContractError("population plan identity schema is unsupported")
    if identity.get("canonicalization") != LIVE_POPULATION_CANONICALIZATION:
        raise LivePopulationContractError(
            "population plan identity canonicalization is unsupported"
        )
    if identity.get("plan_schema") != LIVE_POPULATION_PLAN_SCHEMA:
        raise LivePopulationContractError("population plan identity plan_schema is unsupported")
    return {
        "schema": LIVE_POPULATION_PLAN_IDENTITY_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "plan_schema": LIVE_POPULATION_PLAN_SCHEMA,
        "population_id": _required_identifier(
            identity.get("population_id"), "population plan identity population_id"
        ),
        "sha256": _required_sha256(
            identity.get("sha256"), "population plan identity sha256"
        ),
    }


def _validate_observation(
    value: Any,
    planned_slot: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    observation = _required_mapping(value, "population result observation")
    _require_fields(
        observation, _OBSERVATION_FIELDS, "population result observation"
    )
    run_id = _required_identifier(
        observation.get("run_id"), "population result run_id"
    )
    outcome = observation.get("outcome")
    if outcome not in OBSERVATION_OUTCOMES:
        raise LivePopulationContractError("population result outcome is unsupported")

    report = _validate_report(observation.get("report"))
    notes = _bounded_notes(observation.get("redacted_notes"))
    if outcome == "missed":
        if any(
            observation.get(field) is not None
            for field in (
                "actual_start_utc",
                "actual_stop_utc",
                "runtime",
                "certification_policy_sha256",
            )
        ):
            raise LivePopulationContractError(
                "missed population runs require null actual runtime fields"
            )
        if report != {"status": "not_produced", "sha256": None}:
            raise LivePopulationContractError(
                "missed population runs cannot claim a produced report"
            )
        if not notes:
            raise LivePopulationContractError(
                "missed population runs require redacted notes"
            )
        return {
            "run_id": run_id,
            "outcome": outcome,
            "actual_start_utc": None,
            "actual_stop_utc": None,
            "runtime": None,
            "certification_policy_sha256": None,
            "report": report,
            "redacted_notes": notes,
        }

    start_text, actual_start = _required_observed_utc_timestamp(
        observation.get("actual_start_utc"), "population result actual_start_utc"
    )
    stop_text, actual_stop = _required_observed_utc_timestamp(
        observation.get("actual_stop_utc"), "population result actual_stop_utc"
    )
    if actual_stop <= actual_start:
        raise LivePopulationContractError(
            "population result actual_stop_utc must follow actual_start_utc"
        )
    runtime = _validate_runtime(
        observation.get("runtime"), "population result runtime"
    )
    runtime_matches = runtime == plan["runtime"]
    policy_sha256 = _required_sha256(
        observation.get("certification_policy_sha256"),
        "population result certification_policy_sha256",
    )
    policy_matches = hmac.compare_digest(
        policy_sha256, plan["certification_policy"]["sha256"]
    )

    if outcome == "passed":
        if not runtime_matches or not policy_matches:
            raise LivePopulationContractError(
                "a passed run must match the frozen runtime and policy"
            )
        planned_start = _parse_validated_utc(planned_slot["start_utc"])
        planned_end = _parse_validated_utc(planned_slot["end_utc"])
        if actual_start > planned_start or actual_stop < planned_end:
            raise LivePopulationContractError(
                "a passed run must cover its complete planned observation window"
            )
        if report["status"] != "produced":
            raise LivePopulationContractError("a passed run requires a report digest")
    elif not runtime_matches and policy_matches and outcome != "environment_failure":
        raise LivePopulationContractError(
            "runtime drift must be retained as an environment failure"
        )
    elif runtime_matches and not policy_matches and outcome != "policy_failure":
        raise LivePopulationContractError(
            "policy drift must be retained as a policy failure"
        )
    elif (
        not runtime_matches
        and not policy_matches
        and outcome not in {"environment_failure", "policy_failure"}
    ):
        raise LivePopulationContractError(
            "runtime and policy drift require an explicit configuration failure outcome"
        )
    if (
        outcome == "policy_failure"
        and policy_matches
        and report["status"] != "produced"
    ):
        raise LivePopulationContractError(
            "a policy failure requires the failing report digest"
        )
    if outcome != "passed" and not notes:
        raise LivePopulationContractError(
            "failed population runs require redacted notes"
        )

    return {
        "run_id": run_id,
        "outcome": outcome,
        "actual_start_utc": start_text,
        "actual_stop_utc": stop_text,
        "runtime": runtime,
        "certification_policy_sha256": policy_sha256,
        "report": report,
        "redacted_notes": notes,
    }


def _validate_report(value: Any) -> dict[str, str | None]:
    report = _required_mapping(value, "population result report")
    _require_fields(report, _REPORT_FIELDS, "population result report")
    status = report.get("status")
    digest = report.get("sha256")
    if status == "produced":
        return {
            "status": "produced",
            "sha256": _required_sha256(digest, "population result report sha256"),
        }
    if status == "not_produced" and digest is None:
        return {"status": "not_produced", "sha256": None}
    raise LivePopulationContractError("population result report state is unsupported")


def _load_json_object(path: str | Path, label: str) -> dict[str, Any]:
    target = Path(path)
    try:
        if target.stat().st_size > _MAX_JSON_BYTES:
            raise LivePopulationContractError(f"{label} exceeds the local size limit")
        text = target.read_text(encoding="utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except FileNotFoundError as exc:
        raise LivePopulationContractError(f"{label} file was not found") from exc
    except UnicodeDecodeError as exc:
        raise LivePopulationContractError(f"{label} must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise LivePopulationContractError(
            f"{label} is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except OSError as exc:
        raise LivePopulationContractError(f"{label} file could not be read") from exc
    if not isinstance(value, Mapping):
        raise LivePopulationContractError(f"{label} must be a JSON object")
    return dict(value)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LivePopulationContractError(
                "live population JSON contains a duplicate field"
            )
        result[key] = value
    return result


def _reject_nonfinite_constant(_value: str) -> Any:
    raise LivePopulationContractError(
        "live population JSON contains a non-finite number"
    )


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LivePopulationContractError(f"{label} must be a JSON object")
    return value


def _require_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    present = set(value)
    missing = sorted(expected - present)
    if missing:
        raise LivePopulationContractError(
            f"{label} is missing required fields: {', '.join(missing)}"
        )
    if present - expected:
        raise LivePopulationContractError(f"{label} contains unknown fields")


def _required_text(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise LivePopulationContractError(f"{label} must be a non-empty string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise LivePopulationContractError(
            f"{label} must be a non-empty string no longer than {maximum} characters"
        )
    return normalized


def _required_decision_text(value: Any, label: str) -> str:
    normalized = _required_text(value, label)
    lowered = normalized.casefold()
    if lowered.startswith(("replace_", "replace ", "todo", "tbd", "unset", "unknown", "<")):
        raise LivePopulationContractError(f"{label} contains an unresolved placeholder")
    return normalized


def _required_identifier(value: Any, label: str) -> str:
    normalized = _required_decision_text(value, label)
    if not _IDENTIFIER.fullmatch(normalized):
        raise LivePopulationContractError(
            f"{label} must be 3-128 letters, digits, dots, underscores, or hyphens"
        )
    return normalized


def _required_version(value: Any, label: str) -> str:
    normalized = _required_decision_text(value, label)
    if not _VERSION.fullmatch(normalized):
        raise LivePopulationContractError(
            f"{label} must be one exact three-part version, not a range"
        )
    return normalized


def _required_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LivePopulationContractError(f"{label} must be lowercase SHA-256")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise LivePopulationContractError(f"{label} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise LivePopulationContractError(f"{label} must be finite")
    return number


def _required_date(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise LivePopulationContractError(f"{label} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise LivePopulationContractError(f"{label} is not a calendar date") from exc
    return parsed.isoformat()


def _required_utc_timestamp(value: Any, label: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        raise LivePopulationContractError(
            f"{label} must be an exact UTC timestamp ending in Z with zero seconds"
        )
    try:
        parsed = _parse_validated_utc(value)
    except ValueError as exc:
        raise LivePopulationContractError(f"{label} is not a valid UTC time") from exc
    return value, parsed


def _required_observed_utc_timestamp(
    value: Any, label: str
) -> tuple[str, datetime]:
    if not isinstance(value, str) or not _OBSERVED_UTC_TIMESTAMP.fullmatch(value):
        raise LivePopulationContractError(
            f"{label} must be an exact UTC timestamp ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LivePopulationContractError(f"{label} is not a valid UTC time") from exc
    if parsed.utcoffset() != timedelta(0):
        raise LivePopulationContractError(f"{label} must be UTC")
    if parsed.microsecond:
        normalized = parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    else:
        normalized = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    return normalized, parsed


def _parse_validated_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def _bounded_notes(value: Any) -> str:
    if not isinstance(value, str):
        raise LivePopulationContractError("population result redacted_notes must be a string")
    normalized = value.strip()
    if len(normalized) > 1_000:
        raise LivePopulationContractError(
            "population result redacted_notes must not exceed 1000 characters"
        )
    return normalized


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _constant_time_mapping_equal(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    return hmac.compare_digest(_canonical_sha256(left), _canonical_sha256(right))

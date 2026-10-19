"""Versioned, fail-closed governance decisions required before live capture."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


CAPTURE_POLICY_SCHEMA = "gex-terminal.capture-policy.v1"
RIGHTS_STATUSES = {"licensed", "owned", "public_domain"}
RETENTION_MODES = {"indefinite", "time_limited"}
RESEARCH_USE_STATUSES = {"approved", "prohibited"}
_POLICY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


class CapturePolicyError(ValueError):
    """Raised when a capture policy is unsupported, incomplete, or ambiguous."""


def load_capture_policy(path: str | Path) -> dict[str, Any]:
    """Load and validate one JSON capture policy."""
    target = Path(path)
    try:
        policy = json.loads(
            target.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except FileNotFoundError as exc:
        raise CapturePolicyError("capture policy file was not found") from exc
    except OSError as exc:
        raise CapturePolicyError("capture policy file could not be read") from exc
    except json.JSONDecodeError as exc:
        raise CapturePolicyError(
            f"capture policy is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    return validate_capture_policy(policy)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON objects without echoing their decision values."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CapturePolicyError(
                f"capture policy contains duplicate field: {key}"
            )
        result[key] = value
    return result


def validate_capture_policy(policy: Any) -> dict[str, Any]:
    """Validate an explicit v1 policy and return its canonical representation."""
    root = _require_object(policy, "capture policy")
    _require_keys(
        root,
        "capture policy",
        {"schema", "policy_id", "rights", "retention", "redaction", "research_use"},
    )
    if root["schema"] != CAPTURE_POLICY_SCHEMA:
        raise CapturePolicyError(
            f"capture policy schema must be {CAPTURE_POLICY_SCHEMA}"
        )
    policy_id = _required_text(root["policy_id"], "capture policy policy_id")
    if not _POLICY_ID.fullmatch(policy_id):
        raise CapturePolicyError(
            "capture policy policy_id must be 3-128 letters, digits, dots, underscores, or hyphens"
        )

    rights = _validate_rights(root["rights"])
    retention = _validate_retention(root["retention"])
    redaction = _validate_redaction(root["redaction"])
    research_use = _validate_research_use(root["research_use"])
    return {
        "schema": CAPTURE_POLICY_SCHEMA,
        "policy_id": policy_id,
        "rights": rights,
        "retention": retention,
        "redaction": redaction,
        "research_use": research_use,
    }


def capture_policy_identity(policy: Mapping[str, Any]) -> dict[str, str]:
    """Return the stable identity embedded in a capture, never the full policy."""
    normalized = validate_capture_policy(policy)
    digest = hashlib.sha256(_canonical_bytes(normalized)).hexdigest()
    return {
        "schema": CAPTURE_POLICY_SCHEMA,
        "policy_id": normalized["policy_id"],
        "sha256": digest,
    }


def _validate_rights(value: Any) -> dict[str, Any]:
    rights = _require_object(value, "capture policy rights")
    _require_keys(rights, "capture policy rights", {"status", "basis", "redistributable"})
    status = _required_text(rights["status"], "capture policy rights.status").lower()
    if status not in RIGHTS_STATUSES:
        raise CapturePolicyError(
            "capture policy rights.status must be one of: "
            + ", ".join(sorted(RIGHTS_STATUSES))
        )
    redistributable = rights["redistributable"]
    if not isinstance(redistributable, bool):
        raise CapturePolicyError(
            "capture policy rights.redistributable must be an explicit boolean"
        )
    return {
        "status": status,
        "basis": _required_text(rights["basis"], "capture policy rights.basis"),
        "redistributable": redistributable,
    }


def _validate_retention(value: Any) -> dict[str, Any]:
    retention = _require_object(value, "capture policy retention")
    _require_keys(
        retention,
        "capture policy retention",
        {"mode", "days", "storage", "owner"},
    )
    mode = _required_text(retention["mode"], "capture policy retention.mode").lower()
    if mode not in RETENTION_MODES:
        raise CapturePolicyError(
            "capture policy retention.mode must be one of: "
            + ", ".join(sorted(RETENTION_MODES))
        )
    days = retention["days"]
    if mode == "time_limited":
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 3650:
            raise CapturePolicyError(
                "time-limited capture retention requires integer days from 1 through 3650"
            )
    elif days is not None:
        raise CapturePolicyError(
            "indefinite capture retention requires an explicit null days decision"
        )
    return {
        "mode": mode,
        "days": days,
        "storage": _required_text(
            retention["storage"], "capture policy retention.storage"
        ),
        "owner": _required_text(retention["owner"], "capture policy retention.owner"),
    }


def _validate_redaction(value: Any) -> dict[str, Any]:
    redaction = _require_object(value, "capture policy redaction")
    _require_keys(
        redaction,
        "capture policy redaction",
        {"status", "profile", "review_before_sharing"},
    )
    status = _required_text(redaction["status"], "capture policy redaction.status").lower()
    if status != "required":
        raise CapturePolicyError(
            "capture policy redaction.status must be required for provider capture"
        )
    if redaction["review_before_sharing"] is not True:
        raise CapturePolicyError(
            "capture policy redaction.review_before_sharing must explicitly be true"
        )
    return {
        "status": status,
        "profile": _required_text(
            redaction["profile"], "capture policy redaction.profile"
        ),
        "review_before_sharing": True,
    }


def _validate_research_use(value: Any) -> dict[str, str]:
    research_use = _require_object(value, "capture policy research_use")
    _require_keys(
        research_use,
        "capture policy research_use",
        {"status", "scope"},
    )
    status = _required_text(
        research_use["status"], "capture policy research_use.status"
    ).lower()
    if status not in RESEARCH_USE_STATUSES:
        raise CapturePolicyError(
            "capture policy research_use.status must be one of: "
            + ", ".join(sorted(RESEARCH_USE_STATUSES))
        )
    return {
        "status": status,
        "scope": _required_text(
            research_use["scope"], "capture policy research_use.scope"
        ),
    }


def _require_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CapturePolicyError(f"{label} must be a JSON object")
    return value


def _require_keys(value: Mapping[str, Any], label: str, expected: set[str]) -> None:
    present = set(value)
    missing = sorted(expected - present)
    unknown = sorted(present - expected)
    if missing:
        raise CapturePolicyError(f"{label} is missing: {', '.join(missing)}")
    if unknown:
        raise CapturePolicyError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CapturePolicyError(f"{label} must be an explicit non-empty string")
    return value.strip()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

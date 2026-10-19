"""Private backup, restore, and confirmation-gated retention for research artifacts."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import stat
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from gex_terminal.local_support import (
    SUPPORTED_ARTIFACT_KINDS,
    canonical_sha256,
    inspect_research_artifact,
    inventory_directory,
    load_json_object,
    repository_root,
    validate_new_destination,
    validate_relative_path,
    validate_selected_directory,
    validate_sha256,
)


PRIVATE_BACKUP_SCHEMA = "gex-terminal.private-research-backup.v1"
BACKUP_VERIFICATION_SCHEMA = "gex-terminal.private-backup-verification.v1"
RESTORE_RECEIPT_SCHEMA = "gex-terminal.private-backup-restore.v1"
RETENTION_PLAN_SCHEMA = "gex-terminal.research-retention-plan.v1"
RETENTION_RECEIPT_SCHEMA = "gex-terminal.research-retention-receipt.v1"
PRIVATE_BACKUP_NOTICE = (
    "private local backup; may contain authorized research data and must not be "
    "attached to a support request or redistributed without an independent rights review"
)
RETENTION_NOTICE = (
    "private local deletion plan; apply deletes only complete recognized artifact "
    "directories after exact confirmation and unchanged-target verification"
)

_BACKUP_MANIFEST = "backup-manifest.json"
_BACKUP_PAYLOAD = "payload"
_MAX_RETENTION_TARGETS = 32
_BACKUP_FIELDS = frozenset(
    {
        "schema",
        "created_at",
        "classification",
        "shareable",
        "artifact",
        "files",
        "notice",
        "manifest_sha256",
    }
)
_BACKUP_ARTIFACT_FIELDS = frozenset(
    {
        "kind",
        "artifact_id",
        "artifact_schema",
        "primary_sha256",
        "recorded_identities",
        "content_sha256",
        "file_count",
        "total_bytes",
    }
)
_FILE_FIELDS = frozenset({"path", "sha256", "bytes"})
_RETENTION_FILE_FIELDS = frozenset({"path", "sha256", "bytes", "modified_ns"})
_PLAN_FIELDS = frozenset(
    {
        "schema",
        "created_at",
        "classification",
        "mode",
        "cutoff",
        "targets",
        "notice",
        "plan_sha256",
    }
)
_PLAN_TARGET_FIELDS = frozenset(
    {
        "path",
        "kind",
        "artifact",
        "content_sha256",
        "state_sha256",
        "file_count",
        "total_bytes",
        "latest_mtime_ns",
        "latest_mtime",
        "files",
        "action",
        "backup",
    }
)
_PLAN_BACKUP_FIELDS = frozenset({"path", "manifest_sha256", "artifact"})


def create_private_backup(
    source_dir: str | Path,
    backup_dir: str | Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Copy one recognized artifact directory into a new private backup."""
    _require_private_permissions_supported()
    source = validate_selected_directory(source_dir)
    artifact = inspect_research_artifact(source)
    destination = validate_new_destination(backup_dir)
    _reject_overlapping_paths(source, destination, "backup source and destination")
    _mkdir_private(destination)
    payload = destination / _BACKUP_PAYLOAD
    _mkdir_private(payload)

    expected_files = _content_file_records(artifact["files"])
    for record in expected_files:
        relative = validate_relative_path(record["path"])
        _copy_file_exclusive(
            source / PurePosixPath(relative),
            payload / PurePosixPath(relative),
            expected_sha256=record["sha256"],
            expected_bytes=record["bytes"],
        )

    current_source = inspect_research_artifact(source)
    _require_same_artifact_state(artifact, current_source)
    restored_artifact = inspect_research_artifact(payload)
    _require_same_artifact_content(artifact, restored_artifact)

    manifest = {
        "schema": PRIVATE_BACKUP_SCHEMA,
        "created_at": created_at or _now(),
        "classification": "private-local-research",
        "shareable": False,
        "artifact": _manifest_artifact(artifact),
        "files": expected_files,
        "notice": PRIVATE_BACKUP_NOTICE,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    _write_json_exclusive(destination / _BACKUP_MANIFEST, manifest)
    return verify_private_backup(destination)


def verify_private_backup(backup_dir: str | Path) -> dict[str, Any]:
    """Verify backup manifest, complete payload, and recorded artifact identities."""
    _require_private_permissions_supported()
    _manifest, artifact = _load_verified_backup(backup_dir)
    return {
        "schema": BACKUP_VERIFICATION_SCHEMA,
        "status": "verified",
        "manifest_sha256": _manifest["manifest_sha256"],
        "artifact": _manifest["artifact"],
        "file_count": artifact["file_count"],
        "total_bytes": artifact["total_bytes"],
        "notice": PRIVATE_BACKUP_NOTICE,
    }


def restore_private_backup(
    backup_dir: str | Path,
    destination_dir: str | Path,
) -> dict[str, Any]:
    """Restore a verified backup to a new destination and verify it byte-for-byte."""
    _require_private_permissions_supported()
    manifest, backup_artifact = _load_verified_backup(backup_dir)
    backup = validate_selected_directory(backup_dir)
    payload = backup / _BACKUP_PAYLOAD
    destination = validate_new_destination(destination_dir)
    _reject_overlapping_paths(backup, destination, "backup and restore destination")
    _mkdir_private(destination)

    for record in manifest["files"]:
        relative = validate_relative_path(record["path"])
        _copy_file_exclusive(
            payload / PurePosixPath(relative),
            destination / PurePosixPath(relative),
            expected_sha256=record["sha256"],
            expected_bytes=record["bytes"],
        )
    restored = inspect_research_artifact(destination)
    _require_same_artifact_content(backup_artifact, restored)
    return {
        "schema": RESTORE_RECEIPT_SCHEMA,
        "status": "restored_and_verified",
        "source_manifest_sha256": manifest["manifest_sha256"],
        "artifact": manifest["artifact"],
        "file_count": restored["file_count"],
        "total_bytes": restored["total_bytes"],
        "notice": PRIVATE_BACKUP_NOTICE,
    }


def create_retention_plan(
    artifact_dirs: Sequence[str | Path],
    cutoff: str,
    output_path: str | Path,
    *,
    backup_dirs: Sequence[str | Path],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Write a non-destructive, exact-state plan for whole-group retention."""
    _require_private_permissions_supported()
    selected = tuple(artifact_dirs)
    if not selected:
        raise ValueError("retention planning requires at least one artifact directory")
    if len(selected) > _MAX_RETENTION_TARGETS:
        raise ValueError(
            f"retention planning accepts at most {_MAX_RETENTION_TARGETS} targets"
        )
    selected_backups = tuple(backup_dirs)
    if len(selected_backups) != len(selected):
        raise ValueError(
            "retention planning requires one explicit verified backup per target"
        )
    cutoff_time = _aware_timestamp(cutoff, "retention cutoff")
    plan_path = validate_new_destination(output_path)

    roots = [validate_selected_directory(path) for path in selected]
    backup_roots = [validate_selected_directory(path) for path in selected_backups]
    _reject_duplicate_or_overlapping_targets([*roots, *backup_roots])
    for root, backup_root in zip(roots, backup_roots, strict=True):
        if _is_relative_to(root, repository_root()):
            raise ValueError("retention targets inside the repository are unsupported")
        if _is_relative_to(plan_path, root) or _is_relative_to(plan_path, backup_root):
            raise ValueError(
                "retention plan output must be outside every target and backup"
            )

    targets = []
    pairs = sorted(
        zip(roots, backup_roots, strict=True), key=lambda pair: str(pair[0])
    )
    for root, backup_root in pairs:
        artifact = inspect_research_artifact(root)
        backup_manifest, backup_artifact = _load_verified_backup(backup_root)
        _require_same_artifact_content(artifact, backup_artifact)
        latest = datetime.fromtimestamp(
            artifact["latest_mtime_ns"] / 1_000_000_000,
            tz=timezone.utc,
        )
        eligible = latest < cutoff_time
        targets.append(
            {
                "path": str(root),
                "kind": artifact["kind"],
                "artifact": _manifest_artifact(artifact),
                "content_sha256": artifact["content_sha256"],
                "state_sha256": artifact["state_sha256"],
                "file_count": artifact["file_count"],
                "total_bytes": artifact["total_bytes"],
                "latest_mtime_ns": artifact["latest_mtime_ns"],
                "latest_mtime": latest.isoformat().replace("+00:00", "Z"),
                "files": [dict(record) for record in artifact["files"]],
                "action": "delete_whole_group" if eligible else "retain",
                "backup": {
                    "path": str(backup_root),
                    "manifest_sha256": backup_manifest["manifest_sha256"],
                    "artifact": _manifest_artifact(backup_artifact),
                },
            }
        )
    plan = {
        "schema": RETENTION_PLAN_SCHEMA,
        "created_at": created_at or _now(),
        "classification": "private-local-lifecycle",
        "mode": "dry_run",
        "cutoff": cutoff_time.isoformat().replace("+00:00", "Z"),
        "targets": targets,
        "notice": RETENTION_NOTICE,
    }
    plan["plan_sha256"] = canonical_sha256(plan)
    _write_json_exclusive(plan_path, plan)
    return plan


def apply_retention_plan(
    plan_path: str | Path,
    *,
    confirmation: str,
) -> dict[str, Any]:
    """Delete only unchanged whole groups named by an exactly confirmed plan."""
    _require_private_permissions_supported()
    plan = _load_retention_plan(plan_path)
    expected_confirmation = plan["plan_sha256"]
    validate_sha256(confirmation, "retention confirmation")
    if not hmac.compare_digest(confirmation, expected_confirmation):
        raise ValueError("retention confirmation must equal the exact plan SHA-256")
    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise ValueError("safe whole-directory deletion is unavailable on this platform")

    validated: list[tuple[Path, Mapping[str, Any], Mapping[str, Any]]] = []
    for target in plan["targets"]:
        try:
            root = validate_selected_directory(target["path"])
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError("retention target changed after planning") from exc
        if _is_relative_to(root, repository_root()):
            raise ValueError("retention targets inside the repository are unsupported")
        try:
            current = inspect_research_artifact(root)
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError("retention target changed after planning") from exc
        _validate_planned_target(target, current, plan["cutoff"])
        _verify_planned_backup(target["backup"], current)
        validated.append((root, target, current))

    retained = [
        _receipt_target(target)
        for _root, target, _expected in validated
        if target["action"] == "retain"
    ]
    staged: list[
        tuple[Path, Path, Mapping[str, Any], Mapping[str, Any]]
    ] = []
    try:
        for root, target, expected in validated:
            if target["action"] != "delete_whole_group":
                continue
            quarantine = _stage_retention_target(root)
            staged.append((root, quarantine, target, expected))
        for _root, quarantine, _target, expected in staged:
            current = inspect_research_artifact(quarantine)
            _require_same_artifact_state(expected, current)
            _verify_planned_backup(_target["backup"], current)
    except (FileNotFoundError, OSError, ValueError) as exc:
        rollback_failures = _rollback_staged_targets(staged)
        if rollback_failures:
            raise ValueError(
                "retention staging failed and one or more quarantined targets "
                "require manual recovery"
            ) from exc
        raise ValueError("retention staging failed; all staged targets were restored") from exc

    deleted = []
    for _root, quarantine, target, _expected in staged:
        try:
            shutil.rmtree(quarantine)
        except OSError as exc:
            raise ValueError(
                "retention deletion did not complete; inspect the remaining "
                "same-parent quarantine before retrying"
            ) from exc
        if _path_exists(quarantine):
            raise ValueError("quarantined retention target still exists after deletion")
        deleted.append(_receipt_target(target))

    return {
        "schema": RETENTION_RECEIPT_SCHEMA,
        "status": "applied",
        "plan_sha256": expected_confirmation,
        "deleted": deleted,
        "retained": retained,
        "deleted_count": len(deleted),
        "retained_count": len(retained),
        "notice": RETENTION_NOTICE,
    }


def _load_verified_backup(
    backup_dir: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    backup = validate_selected_directory(backup_dir)
    if _is_relative_to(backup, repository_root()):
        raise ValueError("private backups inside the repository are unsupported")
    backup_inventory = inventory_directory(backup)
    _verify_private_tree_modes(backup, backup_inventory)
    manifest_path = backup / _BACKUP_MANIFEST
    payload = backup / _BACKUP_PAYLOAD
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("private backup manifest is missing or symlinked")
    if not payload.is_dir() or payload.is_symlink():
        raise ValueError("private backup payload is missing or symlinked")
    top_level = {entry.name for entry in backup.iterdir()}
    if top_level != {_BACKUP_MANIFEST, _BACKUP_PAYLOAD}:
        raise ValueError("private backup contains unexpected top-level entries")

    manifest = load_json_object(manifest_path, "private backup manifest")
    _reject_unknown_fields(manifest, _BACKUP_FIELDS, "private backup manifest")
    if manifest.get("schema") != PRIVATE_BACKUP_SCHEMA:
        raise ValueError(f"private backup schema must be {PRIVATE_BACKUP_SCHEMA}")
    if manifest.get("classification") != "private-local-research":
        raise ValueError("private backup classification is unsupported")
    if manifest.get("shareable") is not False:
        raise ValueError("private backup must declare shareable=false")
    if manifest.get("notice") != PRIVATE_BACKUP_NOTICE:
        raise ValueError("private backup notice is unsupported")
    _aware_timestamp(manifest.get("created_at"), "private backup created_at")
    recorded_manifest_sha256 = validate_sha256(
        manifest.get("manifest_sha256"), "private backup manifest_sha256"
    )
    identity_payload = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    if not hmac.compare_digest(
        recorded_manifest_sha256, canonical_sha256(identity_payload)
    ):
        raise ValueError("private backup manifest identity is inconsistent")

    recorded_artifact = _validate_manifest_artifact(manifest.get("artifact"))
    recorded_files = _validate_content_file_records(manifest.get("files"))
    payload_inventory = inventory_directory(payload)
    if recorded_files != _content_file_records(payload_inventory["files"]):
        raise ValueError("private backup payload is missing, changed, or contains extras")
    artifact = inspect_research_artifact(payload)
    if recorded_artifact != _manifest_artifact(artifact):
        raise ValueError("private backup artifact identity is inconsistent")
    return manifest, artifact


def _load_retention_plan(plan_path: str | Path) -> dict[str, Any]:
    source = _validate_private_plan_path(plan_path)
    plan = load_json_object(source, "retention plan")
    _reject_unknown_fields(plan, _PLAN_FIELDS, "retention plan")
    if plan.get("schema") != RETENTION_PLAN_SCHEMA:
        raise ValueError(f"retention plan schema must be {RETENTION_PLAN_SCHEMA}")
    if plan.get("classification") != "private-local-lifecycle":
        raise ValueError("retention plan classification is unsupported")
    if plan.get("mode") != "dry_run":
        raise ValueError("retention plan mode must be dry_run")
    if plan.get("notice") != RETENTION_NOTICE:
        raise ValueError("retention plan notice is unsupported")
    _aware_timestamp(plan.get("created_at"), "retention plan created_at")
    _aware_timestamp(plan.get("cutoff"), "retention cutoff")
    recorded_sha256 = validate_sha256(
        plan.get("plan_sha256"), "retention plan_sha256"
    )
    identity_payload = {
        key: value for key, value in plan.items() if key != "plan_sha256"
    }
    if not hmac.compare_digest(recorded_sha256, canonical_sha256(identity_payload)):
        raise ValueError("retention plan identity is inconsistent")
    targets = plan.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= _MAX_RETENTION_TARGETS:
        raise ValueError("retention plan targets are missing or exceed the supported limit")
    validated_targets = [_validate_plan_target(target) for target in targets]
    roots = [Path(target["path"]) for target in validated_targets]
    backup_roots = [Path(target["backup"]["path"]) for target in validated_targets]
    _reject_duplicate_or_overlapping_targets([*roots, *backup_roots])
    return {**plan, "targets": validated_targets}


def _validate_plan_target(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("retention plan targets must be objects")
    _reject_unknown_fields(value, _PLAN_TARGET_FIELDS, "retention target")
    path = value.get("path")
    if not isinstance(path, str) or not Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError("retention target path must be an absolute path without traversal")
    kind = value.get("kind")
    if kind not in SUPPORTED_ARTIFACT_KINDS:
        raise ValueError(f"unsupported retention artifact kind: {kind}")
    artifact = _validate_manifest_artifact(value.get("artifact"))
    if artifact["kind"] != kind:
        raise ValueError("retention target kind does not match artifact identity")
    files = _validate_state_file_records(value.get("files"))
    content_sha256 = validate_sha256(
        value.get("content_sha256"), "retention content_sha256"
    )
    state_sha256 = validate_sha256(
        value.get("state_sha256"), "retention state_sha256"
    )
    if canonical_sha256(_content_file_records(files)) != content_sha256:
        raise ValueError("retention target content identity is inconsistent")
    if canonical_sha256(files) != state_sha256:
        raise ValueError("retention target state identity is inconsistent")
    file_count = _nonnegative_integer(value.get("file_count"), "retention file_count")
    total_bytes = _nonnegative_integer(value.get("total_bytes"), "retention total_bytes")
    latest_mtime_ns = _nonnegative_integer(
        value.get("latest_mtime_ns"), "retention latest_mtime_ns"
    )
    if file_count != len(files):
        raise ValueError("retention target file_count is inconsistent")
    if total_bytes != sum(record["bytes"] for record in files):
        raise ValueError("retention target total_bytes is inconsistent")
    if latest_mtime_ns != max(record["modified_ns"] for record in files):
        raise ValueError("retention target latest_mtime_ns is inconsistent")
    latest = datetime.fromtimestamp(latest_mtime_ns / 1_000_000_000, tz=timezone.utc)
    if value.get("latest_mtime") != latest.isoformat().replace("+00:00", "Z"):
        raise ValueError("retention target latest_mtime is inconsistent")
    action = value.get("action")
    if action not in {"delete_whole_group", "retain"}:
        raise ValueError("retention target action is unsupported")
    backup = _validate_plan_backup(value.get("backup"))
    if backup["artifact"] != artifact:
        raise ValueError("retention backup identity does not match its target")
    return {
        **dict(value),
        "artifact": artifact,
        "files": files,
        "content_sha256": content_sha256,
        "state_sha256": state_sha256,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "latest_mtime_ns": latest_mtime_ns,
        "action": action,
        "backup": backup,
    }


def _validate_plan_backup(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("retention backup binding must be an object")
    _reject_unknown_fields(value, _PLAN_BACKUP_FIELDS, "retention backup binding")
    path = value.get("path")
    if not isinstance(path, str) or not Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError("retention backup path must be absolute without traversal")
    return {
        "path": path,
        "manifest_sha256": validate_sha256(
            value.get("manifest_sha256"), "retention backup manifest_sha256"
        ),
        "artifact": _validate_manifest_artifact(value.get("artifact")),
    }


def _verify_planned_backup(
    planned: Mapping[str, Any], current: Mapping[str, Any]
) -> None:
    try:
        manifest, backup_artifact = _load_verified_backup(planned["path"])
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ValueError("retention backup changed or no longer verifies") from exc
    if manifest["manifest_sha256"] != planned["manifest_sha256"]:
        raise ValueError("retention backup manifest changed after planning")
    if _manifest_artifact(backup_artifact) != planned["artifact"]:
        raise ValueError("retention backup artifact identity changed after planning")
    _require_same_artifact_content(current, backup_artifact)


def _validate_planned_target(
    planned: Mapping[str, Any], current: Mapping[str, Any], cutoff: str
) -> None:
    if planned["artifact"] != _manifest_artifact(current):
        raise ValueError("retention artifact identity changed after planning")
    for field in (
        "content_sha256",
        "state_sha256",
        "file_count",
        "total_bytes",
        "latest_mtime_ns",
    ):
        if planned[field] != current[field]:
            raise ValueError("retention target changed after planning")
    if planned["files"] != current["files"]:
        raise ValueError("retention target file state changed after planning")
    cutoff_time = _aware_timestamp(cutoff, "retention cutoff")
    latest = datetime.fromtimestamp(
        current["latest_mtime_ns"] / 1_000_000_000,
        tz=timezone.utc,
    )
    expected_action = "delete_whole_group" if latest < cutoff_time else "retain"
    if planned["action"] != expected_action:
        raise ValueError("retention action is inconsistent with the recorded cutoff")


def _manifest_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": artifact["kind"],
        "artifact_id": artifact["artifact_id"],
        "artifact_schema": artifact["artifact_schema"],
        "primary_sha256": artifact["primary_sha256"],
        "recorded_identities": artifact["recorded_identities"],
        "content_sha256": artifact["content_sha256"],
        "file_count": artifact["file_count"],
        "total_bytes": artifact["total_bytes"],
    }


def _validate_manifest_artifact(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("lifecycle artifact identity must be an object")
    _reject_unknown_fields(value, _BACKUP_ARTIFACT_FIELDS, "artifact identity")
    kind = value.get("kind")
    if kind not in SUPPORTED_ARTIFACT_KINDS:
        raise ValueError(f"unsupported lifecycle artifact kind: {kind}")
    artifact_id = _required_text(value.get("artifact_id"), "artifact_id")
    artifact_schema = _required_text(value.get("artifact_schema"), "artifact_schema")
    primary_sha256 = validate_sha256(value.get("primary_sha256"), "primary_sha256")
    content_sha256 = validate_sha256(value.get("content_sha256"), "content_sha256")
    recorded = value.get("recorded_identities")
    if not isinstance(recorded, Mapping):
        raise ValueError("recorded_identities must be an object")
    file_count = _nonnegative_integer(value.get("file_count"), "artifact file_count")
    total_bytes = _nonnegative_integer(value.get("total_bytes"), "artifact total_bytes")
    return {
        "kind": kind,
        "artifact_id": artifact_id,
        "artifact_schema": artifact_schema,
        "primary_sha256": primary_sha256,
        "recorded_identities": dict(recorded),
        "content_sha256": content_sha256,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def _content_file_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": record["path"],
            "sha256": record["sha256"],
            "bytes": record["bytes"],
        }
        for record in records
    ]


def _validate_content_file_records(value: Any) -> list[dict[str, Any]]:
    return _validate_file_records(value, include_modified=False)


def _validate_state_file_records(value: Any) -> list[dict[str, Any]]:
    return _validate_file_records(value, include_modified=True)


def _validate_file_records(value: Any, *, include_modified: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("lifecycle file inventory must be a nonempty list")
    allowed = _RETENTION_FILE_FIELDS if include_modified else _FILE_FIELDS
    records = []
    seen = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("lifecycle file inventory entries must be objects")
        _reject_unknown_fields(item, allowed, "lifecycle file inventory entry")
        relative = validate_relative_path(item.get("path"))
        if relative in seen:
            raise ValueError("lifecycle file inventory contains duplicate paths")
        seen.add(relative)
        record = {
            "path": relative,
            "sha256": validate_sha256(item.get("sha256"), "artifact file sha256"),
            "bytes": _nonnegative_integer(item.get("bytes"), "artifact file bytes"),
        }
        if include_modified:
            record["modified_ns"] = _nonnegative_integer(
                item.get("modified_ns"), "artifact file modified_ns"
            )
        records.append(record)
    if records != sorted(records, key=lambda record: record["path"]):
        raise ValueError("lifecycle file inventory must be sorted by path")
    return records


def _require_private_permissions_supported() -> None:
    required = ("O_NOFOLLOW", "O_DIRECTORY", "fchmod")
    if os.name != "posix" or any(not hasattr(os, name) for name in required):
        raise ValueError(
            "owner-only private lifecycle permissions are unavailable on this platform"
        )


def _mkdir_private(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError as exc:
        raise ValueError("private lifecycle directory already exists") from exc
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _set_private_fd_mode(
            descriptor, 0o700, "private lifecycle directory"
        )
    except OSError as exc:
        raise ValueError("private lifecycle directory could not be protected") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _ensure_private_directory(path: Path) -> None:
    missing = []
    cursor = path
    while not _path_exists(cursor):
        missing.append(cursor)
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise ValueError("private lifecycle parent must be a regular directory")
    _require_path_mode(cursor, 0o700, "private lifecycle parent")
    for directory in reversed(missing):
        _mkdir_private(directory)


def _set_private_fd_mode(descriptor: int, expected: int, label: str) -> None:
    os.fchmod(descriptor, expected)
    actual = stat.S_IMODE(os.fstat(descriptor).st_mode)
    if actual != expected:
        raise ValueError(f"{label} could not be protected with owner-only permissions")


def _require_path_mode(path: Path, expected: int, label: str) -> None:
    actual = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    if actual != expected:
        raise ValueError(f"{label} must have owner-only permissions")


def _verify_private_tree_modes(
    root: Path, inventory: Mapping[str, Any]
) -> None:
    _require_path_mode(root, 0o700, "private backup directory")
    for reference in inventory["directories"]:
        _require_path_mode(
            root / PurePosixPath(reference),
            0o700,
            "private backup directory",
        )
    for record in inventory["files"]:
        _require_path_mode(
            root / PurePosixPath(record["path"]),
            0o600,
            "private backup file",
        )


def _validate_private_plan_path(plan_path: str | Path) -> Path:
    raw = Path(plan_path).expanduser()
    if ".." in raw.parts:
        raise ValueError("retention plan path must not contain traversal segments")
    if raw.is_symlink():
        raise ValueError("retention plan must not be a symlink")
    try:
        source = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"retention plan not found: {raw}") from exc
    if not source.is_file():
        raise ValueError("retention plan path must be a regular file")
    if _is_relative_to(source, repository_root()):
        raise ValueError("private retention plans inside the repository are unsupported")
    lowered = source.name.lower()
    if lowered == ".env" or lowered.startswith(".env."):
        raise ValueError("environment and credential files are not retention plans")
    _require_path_mode(source, 0o600, "private retention plan")
    return source


def _copy_file_exclusive(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError("backup source files must be regular and must not be symlinks")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("safe no-follow private file copying is unavailable")
    _ensure_private_directory(destination.parent)
    digest = hashlib.sha256()
    size = 0
    try:
        with ExitStack() as stack:
            reader = stack.enter_context(
                os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb")
            )
            writer = stack.enter_context(
                os.fdopen(
                    os.open(
                        destination,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                    ),
                    "wb",
                )
            )
            _set_private_fd_mode(
                writer.fileno(), 0o600, "private research file"
            )
            before = os.fstat(reader.fileno())
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
            after = os.fstat(reader.fileno())
    except FileExistsError as exc:
        raise ValueError("lifecycle copy refused to overwrite an existing file") from exc
    except OSError as exc:
        raise ValueError("lifecycle copy refused an unsafe or unreadable file") from exc
    before_state = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_state = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_state != after_state:
        raise ValueError("source artifact changed while it was copied")
    if size != expected_bytes or not hmac.compare_digest(
        digest.hexdigest(), expected_sha256
    ):
        raise ValueError("source artifact changed while it was copied")


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("private lifecycle output parent must be a regular directory")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("safe no-follow private file creation is unavailable")
    try:
        with os.fdopen(
            os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            ),
            "w",
            encoding="utf-8",
        ) as handle:
            _set_private_fd_mode(
                handle.fileno(), 0o600, "private lifecycle file"
            )
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError("lifecycle artifact output already exists") from exc


def _require_same_artifact_content(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> None:
    expected_content = _manifest_artifact(expected)
    actual_content = _manifest_artifact(actual)
    if expected_content != actual_content:
        raise ValueError("research artifact content or recorded identity changed")
    if _content_file_records(expected["files"]) != _content_file_records(actual["files"]):
        raise ValueError("research artifact file inventory changed")


def _require_same_artifact_state(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> None:
    _require_same_artifact_content(expected, actual)
    for field in ("state_sha256", "latest_mtime_ns"):
        if expected[field] != actual[field]:
            raise ValueError("research artifact state changed after inspection")
    if expected["files"] != actual["files"]:
        raise ValueError("research artifact file state changed after inspection")


def _receipt_target(target: Mapping[str, Any]) -> dict[str, Any]:
    artifact = target["artifact"]
    return {
        "kind": artifact["kind"],
        "artifact_id": artifact["artifact_id"],
        "primary_sha256": artifact["primary_sha256"],
        "content_sha256": artifact["content_sha256"],
        "backup_manifest_sha256": target["backup"]["manifest_sha256"],
    }


def _reject_unknown_fields(
    value: Mapping[str, Any], allowed: frozenset[str], label: str
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(unknown)}")


def _reject_duplicate_or_overlapping_targets(paths: Sequence[Path]) -> None:
    resolved = sorted((path.resolve(strict=False) for path in paths), key=str)
    if len(set(resolved)) != len(resolved):
        raise ValueError("lifecycle target directories must be unique")
    for index, path in enumerate(resolved):
        for other in resolved[index + 1 :]:
            if _is_relative_to(other, path) or _is_relative_to(path, other):
                raise ValueError("lifecycle target directories must not overlap")


def _reject_overlapping_paths(first: Path, second: Path, label: str) -> None:
    first_resolved = first.resolve(strict=False)
    second_resolved = second.resolve(strict=False)
    if (
        first_resolved == second_resolved
        or _is_relative_to(first_resolved, second_resolved)
        or _is_relative_to(second_resolved, first_resolved)
    ):
        raise ValueError(f"{label} must not overlap")


def _stage_retention_target(root: Path) -> Path:
    """Atomically move one validated target to a randomized same-parent name."""
    for _attempt in range(16):
        quarantine = root.parent / (
            f".gex-terminal-retention-{secrets.token_hex(16)}"
        )
        if _path_exists(quarantine):
            continue
        try:
            os.rename(root, quarantine)
        except FileExistsError:
            continue
        return quarantine
    raise ValueError("could not allocate a private retention quarantine name")


def _rollback_staged_targets(
    staged: Sequence[tuple[Path, Path, Mapping[str, Any], Mapping[str, Any]]],
) -> list[Path]:
    failures = []
    for original, quarantine, _target, _expected in reversed(staged):
        if not _path_exists(quarantine):
            continue
        if _path_exists(original):
            failures.append(quarantine)
            continue
        try:
            os.rename(quarantine, original)
        except OSError:
            failures.append(quarantine)
    return failures


def _path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _aware_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty ISO 8601 timestamp")
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

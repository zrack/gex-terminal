"""Redacted support evidence and structural research-artifact inventory."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import fields
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence, get_args, get_origin

from gex_terminal import __version__
from gex_terminal.adapters.registry import adapter_info, available_provider_names
from gex_terminal.config import GexConfig
from gex_terminal.experiment_manifest import (
    EXPERIMENT_MANIFEST_SCHEMA_V1,
    EXPERIMENT_MANIFEST_SCHEMA_V2,
    _validate_recorded_manifest,
    semantic_sha256,
)
from gex_terminal.provider_readiness import validate_provider_readiness
from gex_terminal.redaction import (
    REDACTED,
    environment_secret_values,
    is_sensitive_key,
    redact_text,
)
from gex_terminal.research_corpus import (
    CORPUS_EVENT_FILE,
    CORPUS_EVENT_SCHEMA,
    verify_corpus,
)
from gex_terminal.research_journal import ENTRY_SCHEMA


SUPPORT_BUNDLE_SCHEMA = "gex-terminal.support-bundle.v1"
PRIVATE_ARTIFACT_INVENTORY_SCHEMA = "gex-terminal.research-artifact-inventory.v1"
SUPPORTED_ARTIFACT_KINDS = (
    "demo_lab",
    "experiment",
    "research_corpus",
    "research_journal",
)
SUPPORT_EVIDENCE_CEILING = (
    "redacted local software diagnostics and artifact identities only; no raw "
    "research data, credential validation, live-provider proof, or predictive claim"
)

_DOCTOR_SCHEMA = "gex-terminal.doctor.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?:^|[\s=:'\"(])[A-Za-z]:[\\/]")
_EMBEDDED_LOCAL_PATH = re.compile(
    r"(?:^|[\s=:'\"(])(?:file://|~[/\\]|/(?!/)[A-Za-z0-9._-]+(?:[/\\]|$))",
    re.IGNORECASE,
)
_MAX_SUPPORT_ARTIFACTS = 32
_MAX_DOCTOR_CHECKS = 64
_MAX_DETAIL_ITEMS = 64
_MAX_SUPPORT_TEXT = 512
_MAX_DETAIL_DEPTH = 8
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SYSTEM_PATH_ALIASES = {
    Path("/tmp"): Path("/private/tmp"),
    Path("/var"): Path("/private/var"),
}


def build_support_bundle(
    config: GexConfig,
    *,
    artifact_dirs: Sequence[str | Path] = (),
    doctor_report: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build one bounded, shareable report without configuration values or payloads."""
    selected = tuple(artifact_dirs)
    if len(selected) > _MAX_SUPPORT_ARTIFACTS:
        raise ValueError(
            f"support bundle accepts at most {_MAX_SUPPORT_ARTIFACTS} artifact directories"
        )
    environment = os.environ if environ is None else environ
    secrets = environment_secret_values(environment)
    doctor = doctor_report if doctor_report is not None else _build_doctor_report(config)
    sensitive_paths = {
        str(Path.home()),
        str(_REPOSITORY_ROOT),
        *(str(Path(path).expanduser().absolute()) for path in selected),
    }
    artifacts = [
        _support_artifact_summary(inspect_research_artifact(path))
        for path in selected
    ]
    bundle = {
        "schema": SUPPORT_BUNDLE_SCHEMA,
        "generated_at": generated_at or _now(),
        "application": {
            "name": "gex-terminal",
            "version": __version__,
        },
        "configuration_shape": {
            "schema": "gex-terminal.configuration-shape.v1",
            "field_count": len(fields(GexConfig)),
            "fields": [
                {
                    "name": field.name,
                    "type": _annotation_shape(field.type),
                }
                for field in fields(GexConfig)
            ],
            "values_included": False,
        },
        "provider_readiness": [
            {
                "provider": provider,
                "readiness": validate_provider_readiness(adapter_info(provider).status),
            }
            for provider in available_provider_names()
        ],
        "doctor": _bounded_doctor_report(
            doctor,
            secrets=secrets,
            sensitive_paths=sensitive_paths,
        ),
        "artifacts": artifacts,
        "privacy": {
            "classification": "shareable-redacted-support",
            "raw_paths_included": False,
            "configuration_values_included": False,
            "credentials_included": False,
            "account_identifiers_included": False,
            "raw_payloads_included": False,
            "log_files_included": False,
        },
        "evidence_ceiling": SUPPORT_EVIDENCE_CEILING,
    }
    sanitized = _sanitize_support_value(
        bundle,
        secrets=secrets,
        sensitive_paths=sensitive_paths,
        depth=0,
    )
    _assert_support_privacy(sanitized, secrets=secrets, sensitive_paths=sensitive_paths)
    return sanitized


def write_support_bundle(bundle: Mapping[str, Any], output_path: str | Path) -> Path:
    """Write a new JSON support artifact without overwriting an existing file."""
    if bundle.get("schema") != SUPPORT_BUNDLE_SCHEMA:
        raise ValueError(f"support bundle schema must be {SUPPORT_BUNDLE_SCHEMA}")
    target = Path(output_path)
    if target.suffix.lower() != ".json":
        raise ValueError("support bundle output must use a .json suffix")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise ValueError("support bundle output already exists") from exc
    return target


def inspect_research_artifact(directory: str | Path) -> dict[str, Any]:
    """Inventory and structurally recognize one supported research directory."""
    root = validate_selected_directory(directory)
    inventory = inventory_directory(root)
    available_paths = {record["path"] for record in inventory["files"]}
    available_directories = set(inventory["directories"])
    if (root / "review-receipt.json").is_file():
        artifact = _inspect_demo_lab(root, available_paths, available_directories)
    elif (root / "manifest.json").is_file():
        artifact = _inspect_experiment(root, available_paths, available_directories)
    elif (root / CORPUS_EVENT_FILE).is_file():
        artifact = _inspect_corpus(root, available_paths, available_directories)
    elif (root / "entries").is_dir():
        artifact = _inspect_journal(root, available_paths, available_directories)
    else:
        raise ValueError(
            "unrecognized research artifact directory; supported kinds are: "
            + ", ".join(SUPPORTED_ARTIFACT_KINDS)
        )
    return {
        "schema": PRIVATE_ARTIFACT_INVENTORY_SCHEMA,
        **artifact,
        "content_sha256": inventory["content_sha256"],
        "state_sha256": inventory["state_sha256"],
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
        "latest_mtime_ns": inventory["latest_mtime_ns"],
        "files": inventory["files"],
    }


def validate_selected_directory(directory: str | Path) -> Path:
    """Resolve an explicit directory while refusing traversal and broad targets."""
    raw = Path(directory).expanduser()
    if ".." in raw.parts:
        raise ValueError("research artifact paths must not contain traversal segments")
    if raw.is_symlink():
        raise ValueError("research artifact directory must not be a symlink")
    absolute = raw.absolute()
    _reject_environment_path(absolute)
    if not absolute.parent.is_dir():
        raise ValueError("lifecycle destination parent must be an existing directory")
    _reject_unsupported_symlink_ancestors(absolute.parent)
    try:
        root = absolute.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"research artifact directory not found: {raw}") from exc
    if not root.is_dir():
        raise ValueError("research artifact path must be a directory")
    _reject_broad_path(root)
    _reject_environment_path(root)
    return root


def validate_new_destination(
    destination: str | Path, *, allow_repository_child: bool = False
) -> Path:
    """Validate a not-yet-created lifecycle destination without following it."""
    raw = Path(destination).expanduser()
    if ".." in raw.parts:
        raise ValueError("lifecycle destinations must not contain traversal segments")
    if raw.exists() or raw.is_symlink():
        raise ValueError("lifecycle destination must not already exist")
    absolute = raw.absolute()
    _reject_environment_path(absolute)
    _reject_unsupported_symlink_ancestors(absolute.parent)
    target = absolute.resolve(strict=False)
    _reject_broad_path(target)
    if not allow_repository_child and _is_relative_to(target, _REPOSITORY_ROOT):
        raise ValueError("private lifecycle destinations must be outside the repository")
    _reject_environment_path(target)
    return target


def inventory_directory(directory: str | Path) -> dict[str, Any]:
    """Hash every regular file in a symlink-free directory tree."""
    root = Path(directory)
    records: list[dict[str, Any]] = []
    files, directories = _walk_artifact_tree(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        _validate_relative_path(relative)
        _reject_environment_path(PurePosixPath(relative))
        digest, size, modified_ns = _stable_file_identity(path)
        records.append(
            {
                "path": relative,
                "sha256": digest,
                "bytes": size,
                "modified_ns": modified_ns,
            }
        )
    if not records:
        raise ValueError("research artifact directory contains no files")
    records.sort(key=lambda item: item["path"])
    content_records = [
        {key: item[key] for key in ("path", "sha256", "bytes")}
        for item in records
    ]
    return {
        "files": records,
        "file_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "latest_mtime_ns": max(item["modified_ns"] for item in records),
        "content_sha256": canonical_sha256(content_records),
        "state_sha256": canonical_sha256(records),
        "directories": directories,
    }


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return dict(value)


def validate_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def validate_relative_path(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("artifact file path must be text")
    return _validate_relative_path(value)


def repository_root() -> Path:
    return _REPOSITORY_ROOT


def _build_doctor_report(config: GexConfig) -> Mapping[str, Any]:
    try:
        from gex_terminal.doctor import build_doctor_report
    except ModuleNotFoundError as exc:
        raise ValueError(
            "support bundle requires the offline doctor module or an injected doctor report"
        ) from exc
    return build_doctor_report(config)


def _bounded_doctor_report(
    report: Mapping[str, Any],
    *,
    secrets: Sequence[str],
    sensitive_paths: set[str],
) -> dict[str, Any]:
    if not isinstance(report, Mapping) or report.get("schema") != _DOCTOR_SCHEMA:
        raise ValueError(f"doctor report schema must be {_DOCTOR_SCHEMA}")
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) > _MAX_DOCTOR_CHECKS:
        raise ValueError(f"doctor report checks must be a list of at most {_MAX_DOCTOR_CHECKS}")
    bounded_checks = []
    for check in checks:
        if not isinstance(check, Mapping):
            raise ValueError("doctor report checks must be objects")
        status = _required_choice(
            check.get("status"),
            {"pass", "warning", "fail", "unverified"},
            "doctor check status",
        )
        bounded = {
            "id": _bounded_text(check.get("id"), "doctor check id"),
            "category": _bounded_text(
                check.get("category"), "doctor check category"
            ),
            "status": status,
            "summary": _bounded_text(check.get("summary"), "doctor check summary"),
        }
        if check.get("action") is not None:
            bounded["action"] = _bounded_text(
                check.get("action"), "doctor check action"
            )
        if check.get("details") is not None:
            bounded["details"] = _sanitize_support_value(
                check.get("details"),
                secrets=secrets,
                sensitive_paths=sensitive_paths,
                depth=0,
            )
        bounded_checks.append(bounded)

    application = _required_mapping(report.get("application"), "doctor application")
    execution = _required_mapping(report.get("execution"), "doctor execution")
    summary = _required_mapping(report.get("summary"), "doctor summary")
    counts = _required_mapping(summary.get("counts"), "doctor summary counts")
    if set(counts) != {"pass", "warning", "fail", "unverified"}:
        raise ValueError("doctor summary counts use an unsupported shape")
    normalized_counts = {
        key: _required_integer(counts.get(key), f"doctor count {key}")
        for key in ("pass", "warning", "fail", "unverified")
    }
    if sum(normalized_counts.values()) != len(bounded_checks):
        raise ValueError("doctor summary counts do not match its checks")
    execution_flags = {
        key: _required_bool(execution.get(key), f"doctor execution {key}")
        for key in (
            "network_used",
            "live_adapter_constructed",
            "optional_sdk_imported",
            "persistent_state_created",
            "sensitive_values_included",
        )
    }
    if any(
        execution_flags[key]
        for key in (
            "network_used",
            "live_adapter_constructed",
            "optional_sdk_imported",
            "sensitive_values_included",
        )
    ):
        raise ValueError("support bundles require an offline privacy-safe doctor report")
    return {
        "schema": _DOCTOR_SCHEMA,
        "generated_at": _bounded_text(report.get("generated_at"), "doctor generated_at"),
        "application": {
            "name": _bounded_text(application.get("name"), "doctor application name"),
            "version": _bounded_text(
                application.get("version"), "doctor application version"
            ),
        },
        "execution": execution_flags,
        "checks": bounded_checks,
        "summary": {
            "status": _required_choice(
                summary.get("status"),
                {"pass", "warning", "fail"},
                "doctor summary status",
            ),
            "exit_code": _required_choice_integer(
                summary.get("exit_code"), {0, 1, 2}, "doctor summary exit_code"
            ),
            "counts": normalized_counts,
        },
        "evidence_ceiling": _bounded_text(
            report.get("evidence_ceiling"), "doctor evidence_ceiling"
        ),
    }


def _support_artifact_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": artifact["kind"],
        "id_fingerprint": hashlib.sha256(
            str(artifact["artifact_id"]).encode("utf-8")
        ).hexdigest(),
        "primary_sha256": artifact["primary_sha256"],
        "content_sha256": artifact["content_sha256"],
        "file_count": artifact["file_count"],
        "total_bytes": artifact["total_bytes"],
    }


def _inspect_demo_lab(
    root: Path, available_paths: set[str], available_directories: set[str]
) -> dict[str, Any]:
    verification = _verify_demo_lab_pack(root)
    if verification.get("schema") != "gex-terminal.demo-lab-verification.v1":
        raise ValueError("unsupported Demo Lab verification schema")
    receipt = _required_mapping(
        verification.get("receipt"), "Demo Lab review receipt"
    )
    if receipt.get("schema") != "gex-terminal.demo-lab-review-receipt.v1":
        raise ValueError("unsupported Demo Lab review receipt schema")
    receipt_sha256 = validate_sha256(
        receipt.get("receipt_sha256"), "Demo Lab receipt_sha256"
    )
    pack = _required_mapping(receipt.get("pack"), "Demo Lab pack identity")
    if pack.get("schema") != "gex-terminal.demo-lab.v2":
        raise ValueError("unsupported Demo Lab pack schema")
    pack_sha256 = validate_sha256(
        pack.get("content_sha256"), "Demo Lab pack content_sha256"
    )
    if verification.get("content_sha256") != pack_sha256:
        raise ValueError("Demo Lab verification and receipt identities conflict")
    source = _required_mapping(receipt.get("source"), "Demo Lab source identity")
    source_sha256 = validate_sha256(
        source.get("sha256"), "Demo Lab source sha256"
    )
    model = _required_mapping(receipt.get("model"), "Demo Lab model identity")
    profile_sha256 = validate_sha256(
        model.get("profile_sha256"), "Demo Lab model profile_sha256"
    )
    semantic_content = _required_mapping(
        receipt.get("content"), "Demo Lab semantic content"
    )
    semantic_hashes = {
        str(path): validate_sha256(digest, f"Demo Lab content digest {path}")
        for path, digest in sorted(semantic_content.items(), key=lambda item: str(item[0]))
    }
    if not semantic_hashes:
        raise ValueError("Demo Lab semantic content must not be empty")
    receipt_artifacts = receipt.get("artifacts")
    if not isinstance(receipt_artifacts, list) or not receipt_artifacts:
        raise ValueError("Demo Lab receipt artifact inventory must not be empty")
    owned_paths = {"review-receipt.json"}
    for item in receipt_artifacts:
        artifact = _required_mapping(item, "Demo Lab receipt artifact")
        owned_paths.add(validate_relative_path(artifact.get("path")))
    _require_exact_artifact_paths(
        available_paths,
        available_directories,
        owned_paths,
        "Demo Lab",
    )
    return {
        "kind": "demo_lab",
        "artifact_id": f"demo-lab:{receipt_sha256}",
        "artifact_schema": str(receipt["schema"]),
        "primary_sha256": receipt_sha256,
        "recorded_identities": {
            "receipt_sha256": receipt_sha256,
            "pack_content_sha256": pack_sha256,
            "source_sha256": source_sha256,
            "profile_sha256": profile_sha256,
            "semantic_content": semantic_hashes,
        },
    }


def _verify_demo_lab_pack(root: Path) -> Mapping[str, Any]:
    try:
        from gex_terminal.demo_lab_receipt import verify_demo_lab_pack
    except ModuleNotFoundError as exc:
        if exc.name != "gex_terminal.demo_lab_receipt":
            raise
        raise ValueError(
            "Demo Lab lifecycle support requires the Demo Lab receipt verifier"
        ) from exc
    return verify_demo_lab_pack(root)


def _inspect_experiment(
    root: Path, available_paths: set[str], available_directories: set[str]
) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    manifest = load_json_object(manifest_path, "experiment manifest")
    schema = manifest.get("schema")
    if schema not in {EXPERIMENT_MANIFEST_SCHEMA_V1, EXPERIMENT_MANIFEST_SCHEMA_V2}:
        raise ValueError(f"unsupported experiment manifest schema: {schema}")
    _validate_recorded_manifest(manifest, _file_sha256(manifest_path))
    experiment_id = _required_text(manifest.get("experiment_id"), "experiment_id")
    result = _required_mapping(manifest.get("result"), "experiment result")
    result_digest = validate_sha256(
        result.get("semantic_sha256"), "experiment result semantic_sha256"
    )
    report_reference = validate_relative_path(result.get("path"))
    _require_exact_artifact_paths(
        available_paths,
        available_directories,
        {"manifest.json", report_reference},
        "experiment",
    )
    report_path = root / PurePosixPath(report_reference)
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("experiment report is missing or symlinked")
    report = load_json_object(report_path, "experiment report")
    if semantic_sha256(report) != result_digest:
        raise ValueError("experiment report does not match its semantic result digest")
    input_record = _required_mapping(manifest.get("input"), "experiment input")
    input_digest = validate_sha256(
        input_record.get("sha256"), "experiment input sha256"
    )
    if schema == EXPERIMENT_MANIFEST_SCHEMA_V2:
        identity = _required_mapping(manifest.get("identity"), "experiment identity")
        primary = validate_sha256(
            identity.get("experiment_sha256"), "experiment identity sha256"
        )
        recorded = {
            "experiment_sha256": primary,
            "experiment_spec_sha256": validate_sha256(
                identity.get("experiment_spec_sha256"),
                "experiment spec identity sha256",
            ),
            "profile_sha256": validate_sha256(
                identity.get("profile_sha256"), "experiment profile identity sha256"
            ),
            "input_sha256": input_digest,
            "result_sha256": result_digest,
        }
    else:
        profile_digest = validate_sha256(
            manifest.get("profile_sha256"), "experiment profile_sha256"
        )
        recorded = {
            "profile_sha256": profile_digest,
            "input_sha256": input_digest,
            "result_sha256": result_digest,
        }
        primary = canonical_sha256(recorded)
    return {
        "kind": "experiment",
        "artifact_id": experiment_id,
        "artifact_schema": str(schema),
        "primary_sha256": primary,
        "recorded_identities": recorded,
    }


def _inspect_corpus(
    root: Path, available_paths: set[str], available_directories: set[str]
) -> dict[str, Any]:
    report = verify_corpus(root)
    if not report.get("result", {}).get("passed"):
        raise ValueError("research corpus must pass verification before lifecycle use")
    event_path = root / CORPUS_EVENT_FILE
    events = []
    source_references: set[str] = set()
    for line_number, line in enumerate(
        event_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite_constant,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid corpus event at line {line_number}") from exc
        if not isinstance(event, Mapping) or event.get("schema") != CORPUS_EVENT_SCHEMA:
            raise ValueError(f"unsupported corpus event at line {line_number}")
        events.append(dict(event))
        if event.get("event_type") != "item_registered":
            continue
        payload = _required_mapping(event.get("payload"), "corpus item payload")
        source = _required_mapping(payload.get("source"), "corpus item source")
        try:
            reference = validate_relative_path(source.get("reference"))
        except ValueError as exc:
            raise ValueError(
                "corpus lifecycle requires normalized in-directory regular sources"
            ) from exc
        source_path = root / PurePosixPath(reference)
        if not source_path.is_file() or source_path.is_symlink():
            raise ValueError("corpus lifecycle requires in-directory regular sources")
        source_references.add(reference)
    _require_exact_artifact_paths(
        available_paths,
        available_directories,
        {CORPUS_EVENT_FILE, *source_references},
        "research corpus",
    )
    corpus = _required_mapping(report.get("corpus"), "corpus summary")
    chain = _required_mapping(report.get("chain"), "corpus chain")
    corpus_id = _required_text(corpus.get("corpus_id"), "corpus_id")
    head = validate_sha256(chain.get("head_sha256"), "corpus head_sha256")
    return {
        "kind": "research_corpus",
        "artifact_id": corpus_id,
        "artifact_schema": CORPUS_EVENT_SCHEMA,
        "primary_sha256": head,
        "recorded_identities": {
            "corpus_id": corpus_id,
            "event_count": len(events),
            "item_count": int(corpus.get("item_count", 0)),
            "head_sha256": head,
        },
    }


def _inspect_journal(
    root: Path, available_paths: set[str], available_directories: set[str]
) -> dict[str, Any]:
    entry_paths = sorted((root / "entries").glob("*.json"))
    if not entry_paths:
        raise ValueError("research journal contains no entries")
    _require_exact_artifact_paths(
        available_paths,
        available_directories,
        {path.relative_to(root).as_posix() for path in entry_paths},
        "research journal",
    )
    entry_ids = []
    entry_digests = []
    for path in entry_paths:
        if path.is_symlink():
            raise ValueError("research journal entries must not be symlinks")
        entry = load_json_object(path, "research journal entry")
        if entry.get("schema") != ENTRY_SCHEMA:
            raise ValueError("research journal contains an unsupported entry schema")
        entry_id = _required_text(entry.get("id"), "research journal entry id")
        if entry_id in entry_ids:
            raise ValueError("research journal contains duplicate entry IDs")
        entry_ids.append(entry_id)
        entry_digests.append(
            {
                "id": entry_id,
                "sha256": _file_sha256(path),
            }
        )
    entries_digest = canonical_sha256(entry_digests)
    return {
        "kind": "research_journal",
        "artifact_id": f"journal:{entries_digest}",
        "artifact_schema": ENTRY_SCHEMA,
        "primary_sha256": entries_digest,
        "recorded_identities": {
            "entry_count": len(entry_ids),
            "entry_ids": entry_ids,
            "entries_sha256": entries_digest,
        },
    }


def _walk_artifact_tree(root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    directories: list[str] = []

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise ValueError("research artifact directory cannot be inventoried") from exc
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                raise ValueError("research artifact trees must not contain symlinks")
            if entry.is_dir(follow_symlinks=False):
                directories.append(path.relative_to(root).as_posix())
                visit(path)
            elif entry.is_file(follow_symlinks=False):
                files.append(path)
            else:
                raise ValueError("research artifact trees must contain regular files only")

    visit(root)
    directories.sort()
    return files, directories


def _stable_file_identity(path: Path) -> tuple[str, int, int]:
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("research artifact trees must contain regular files only")
    digest = _file_sha256(path)
    after = path.stat(follow_symlinks=False)
    before_state = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_state = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_state != after_state:
        raise ValueError("research artifact file changed while it was inventoried")
    return digest, int(after.st_size), int(after.st_mtime_ns)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitize_support_value(
    value: Any,
    *,
    secrets: Sequence[str],
    sensitive_paths: set[str],
    depth: int,
) -> Any:
    if depth > _MAX_DETAIL_DEPTH:
        raise ValueError("support diagnostic detail nesting is too deep")
    if isinstance(value, Mapping):
        if len(value) > _MAX_DETAIL_ITEMS:
            raise ValueError("support diagnostic object is too large")
        result = {}
        for key, nested in sorted(value.items(), key=lambda item: str(item[0])):
            name = str(key)[:_MAX_SUPPORT_TEXT]
            if is_sensitive_key(name):
                result[name] = REDACTED
                continue
            result[name] = _sanitize_support_value(
                nested,
                secrets=secrets,
                sensitive_paths=sensitive_paths,
                depth=depth + 1,
            )
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_DETAIL_ITEMS:
            raise ValueError("support diagnostic list is too large")
        return [
            _sanitize_support_value(
                item,
                secrets=secrets,
                sensitive_paths=sensitive_paths,
                depth=depth + 1,
            )
            for item in value
        ]
    if isinstance(value, str):
        return _sanitize_support_text(
            value,
            secrets=secrets,
            sensitive_paths=sensitive_paths,
        )
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("support diagnostics contain an unsupported value type")


def _sanitize_support_text(
    value: str, *, secrets: Sequence[str], sensitive_paths: set[str]
) -> str:
    text = str(value)[:_MAX_SUPPORT_TEXT]
    for path in sorted((item for item in sensitive_paths if item), key=len, reverse=True):
        text = text.replace(path, "[redacted-local-path]")
    text = redact_text(text, secrets=secrets)
    if _WINDOWS_ABSOLUTE_PATH.search(text) or _EMBEDDED_LOCAL_PATH.search(text):
        return "[redacted-local-path]"
    return text


def _assert_support_privacy(
    bundle: Mapping[str, Any], *, secrets: Sequence[str], sensitive_paths: set[str]
) -> None:
    encoded = json.dumps(bundle, sort_keys=True, ensure_ascii=False, allow_nan=False)
    for forbidden in (*secrets, *sensitive_paths):
        if forbidden and forbidden in encoded:
            raise ValueError("support bundle privacy check rejected sensitive content")


def _annotation_shape(annotation: Any) -> str:
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is tuple and arguments and arguments[0] is str:
        return "string_sequence"
    if type(None) in arguments and float in arguments:
        return "number_or_null"
    return "declared"


def _reject_broad_path(path: Path) -> None:
    resolved = path.resolve(strict=False)
    filesystem_root = Path(resolved.anchor)
    if resolved in {filesystem_root, Path.home().resolve(), _REPOSITORY_ROOT}:
        raise ValueError("root, home, and repository directories are not lifecycle targets")


def _reject_unsupported_symlink_ancestors(path: Path) -> None:
    for candidate in (path, *path.parents):
        if not candidate.is_symlink():
            continue
        resolved = candidate.resolve(strict=True)
        if _SYSTEM_PATH_ALIASES.get(candidate) == resolved:
            continue
        raise ValueError("lifecycle destination ancestors must not be symlinks")


def _reject_environment_path(path: Path | PurePosixPath) -> None:
    for part in path.parts:
        lowered = part.lower()
        if lowered == ".env" or lowered.startswith(".env."):
            raise ValueError("environment and credential files are not lifecycle targets")


def _validate_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or value != path.as_posix():
        raise ValueError("artifact file path must be a normalized relative POSIX path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact file path must not contain traversal segments")
    return value


def _require_exact_artifact_paths(
    available: set[str],
    available_directories: set[str],
    expected: set[str],
    label: str,
) -> None:
    expected_directories: set[str] = set()
    for reference in expected:
        path = PurePosixPath(reference)
        for parent in path.parents:
            if parent == PurePosixPath("."):
                break
            expected_directories.add(parent.as_posix())
    if available != expected or available_directories != expected_directories:
        raise ValueError(f"{label} directory contains unsupported or missing files")


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _bounded_text(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if len(text) > _MAX_SUPPORT_TEXT:
        raise ValueError(f"{label} is too long for a support bundle")
    return text


def _required_choice(value: Any, choices: set[str], label: str) -> str:
    text = _required_text(value, label)
    if text not in choices:
        raise ValueError(f"{label} is unsupported: {text}")
    return text


def _required_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _required_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _required_choice_integer(value: Any, choices: set[int], label: str) -> int:
    number = _required_integer(value, label)
    if number not in choices:
        raise ValueError(f"{label} is unsupported: {number}")
    return number


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is unsupported: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON value is unsupported: {value}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

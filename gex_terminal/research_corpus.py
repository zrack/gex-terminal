"""Append-only, hash-chained registry for governed research inputs."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CORPUS_EVENT_SCHEMA = "gex-terminal.research-corpus-event.v1"
CORPUS_ITEM_SCHEMA = "gex-terminal.research-corpus-item.v1"
CORPUS_REPORT_SCHEMA = "gex-terminal.research-corpus-verification.v1"
CORPUS_EVENT_FILE = "events.jsonl"
ZERO_HASH = "0" * 64
SPLITS = {"train", "calibration", "test", "unassigned"}
RIGHTS_STATUSES = {"owned", "licensed", "redistributable", "restricted", "unknown"}
REDACTION_STATUSES = {"not_required", "verified", "required", "unknown"}


def initialize_corpus(directory: str | Path, *, corpus_id: str | None = None) -> Path:
    root = Path(directory)
    event_path = root / CORPUS_EVENT_FILE
    if event_path.exists():
        raise ValueError(f"research corpus already exists: {event_path}")
    root.mkdir(parents=True, exist_ok=True)
    identifier = str(corpus_id or root.name).strip()
    if not identifier:
        raise ValueError("corpus_id must not be empty")
    event = _event(
        sequence=0,
        previous_hash=ZERO_HASH,
        event_type="corpus_initialized",
        payload={"corpus_id": identifier},
    )
    _append_event(event_path, event)
    return event_path


def register_corpus_item(
    directory: str | Path,
    source_path: str | Path,
    metadata_path: str | Path,
) -> dict[str, Any]:
    root = Path(directory)
    event_path = root / CORPUS_EVENT_FILE
    events, base_report = _read_and_verify_events(event_path)
    if not base_report["chain_valid"]:
        raise ValueError("cannot register into a corpus with an invalid event chain")
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if not isinstance(metadata, Mapping):
        raise ValueError("corpus item metadata must be a JSON object")
    item = _validate_item_metadata(metadata)
    source = Path(source_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"corpus source not found: {source}")
    source_digest = _file_digest(source)
    registrations = [
        event["payload"]
        for event in events
        if event.get("event_type") == "item_registered"
        and isinstance(event.get("payload"), Mapping)
    ]
    if any(entry["dataset_id"] == item["dataset_id"] for entry in registrations):
        raise ValueError(f"dataset_id is immutable and already registered: {item['dataset_id']}")
    if any(entry["source"]["sha256"] == source_digest for entry in registrations):
        raise ValueError("source digest is already registered under another dataset_id")
    try:
        reference = str(source.relative_to(root.resolve()))
    except ValueError:
        reference = str(source)
    item["source"] = {
        "reference": reference,
        "sha256": source_digest,
        "bytes": source.stat().st_size,
    }
    event = _event(
        sequence=len(events),
        previous_hash=events[-1]["event_hash"],
        event_type="item_registered",
        payload=item,
    )
    _append_event(event_path, event)
    return event


def verify_corpus(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    events, chain_report = _read_and_verify_events(root / CORPUS_EVENT_FILE)
    items = []
    dataset_ids: set[str] = set()
    source_digests: set[str] = set()
    errors = list(chain_report["errors"])
    split_counts = {name: 0 for name in sorted(SPLITS)}
    for event in events:
        if event.get("event_type") != "item_registered":
            continue
        item = event.get("payload", {})
        if not isinstance(item, Mapping):
            errors.append(f"sequence_{event.get('sequence')}:payload_not_object")
            continue
        dataset_id = str(item.get("dataset_id") or "")
        source = item.get("source", {})
        if not isinstance(source, Mapping):
            source = {}
        reference = str(source.get("reference") or "")
        expected_digest = str(source.get("sha256") or "")
        split = str(item.get("split") or "")
        status = "verified"
        item_errors = []
        if dataset_id in dataset_ids:
            item_errors.append("duplicate_dataset_id")
        dataset_ids.add(dataset_id)
        if expected_digest in source_digests:
            item_errors.append("duplicate_source_digest")
        source_digests.add(expected_digest)
        if split in split_counts:
            split_counts[split] += 1
        else:
            item_errors.append("invalid_split")
        path = Path(reference)
        resolved = path if path.is_absolute() else root / path
        if not resolved.is_file():
            item_errors.append("missing_source")
        elif _file_digest(resolved) != expected_digest:
            item_errors.append("source_digest_changed")
        if item_errors:
            status = "invalid"
            errors.extend(f"{dataset_id}:{error}" for error in item_errors)
        items.append({
            "dataset_id": dataset_id,
            "split": split,
            "status": status,
            "errors": item_errors,
            "source_reference": reference,
            "source_sha256": expected_digest,
            "rights_status": (
                item.get("rights", {}).get("status")
                if isinstance(item.get("rights"), Mapping)
                else None
            ),
            "redaction_status": item.get("redaction_status"),
        })
    return {
        "schema": CORPUS_REPORT_SCHEMA,
        "generated_at": _now(),
        "corpus": {
            "path": str(root),
            "corpus_id": events[0].get("payload", {}).get("corpus_id") if events else None,
            "event_count": len(events),
            "item_count": len(items),
            "split_counts": split_counts,
        },
        "chain": chain_report,
        "items": items,
        "result": {
            "passed": bool(events) and not errors,
            "predictive_validity": "unmeasured",
            "live_provider_certified": False,
        },
        "errors": errors,
        "evidence_ceiling": (
            "corpus identity, rights metadata, split immutability, and source integrity only; "
            "not source accuracy, live coverage, or predictive validity"
        ),
    }


def write_corpus_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {"", ".json"}:
        raise ValueError("corpus verification output must be JSON")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _validate_item_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if metadata.get("schema") != CORPUS_ITEM_SCHEMA:
        raise ValueError(f"corpus item schema must be {CORPUS_ITEM_SCHEMA}")
    dataset_id = str(metadata.get("dataset_id") or "").strip()
    if not dataset_id:
        raise ValueError("corpus item requires dataset_id")
    split = str(metadata.get("split") or "").strip().lower()
    if split not in SPLITS:
        raise ValueError(f"corpus item split must be one of: {', '.join(sorted(SPLITS))}")
    source_kind = str(metadata.get("source_kind") or "").strip()
    if not source_kind:
        raise ValueError("corpus item requires source_kind")
    rights = metadata.get("rights")
    if not isinstance(rights, Mapping):
        raise ValueError("corpus item requires a rights object")
    rights_status = str(rights.get("status") or "").strip().lower()
    if rights_status not in RIGHTS_STATUSES:
        raise ValueError("corpus item rights status is unsupported")
    redistributable = rights.get("redistributable")
    if not isinstance(redistributable, bool):
        raise ValueError("corpus item rights.redistributable must be boolean")
    redaction = str(metadata.get("redaction_status") or "").strip().lower()
    if redaction not in REDACTION_STATUSES:
        raise ValueError("corpus item redaction_status is unsupported")
    outcome = metadata.get("outcome_definition")
    if outcome is not None and not isinstance(outcome, (str, Mapping)):
        raise ValueError("outcome_definition must be a string, object, or null")
    costs = metadata.get("cost_assumptions", {})
    if not isinstance(costs, Mapping):
        raise ValueError("cost_assumptions must be an object")
    as_of = _timezone_aware_timestamp(metadata.get("as_of"), "corpus item as_of")
    return {
        "schema": CORPUS_ITEM_SCHEMA,
        "dataset_id": dataset_id,
        "source_kind": source_kind,
        "split": split,
        "as_of": as_of,
        "rights": {
            "status": rights_status,
            "redistributable": redistributable,
            "notes": rights.get("notes"),
        },
        "redaction_status": redaction,
        "outcome_definition": outcome,
        "cost_assumptions": dict(costs),
        "notes": metadata.get("notes"),
    }


def _read_and_verify_events(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"research corpus not found: {path}")
    events = []
    errors = []
    previous_hash = ZERO_HASH
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line_{line_number}:invalid_json")
            continue
        if not isinstance(event, Mapping):
            errors.append(f"line_{line_number}:event_not_object")
            continue
        event = dict(event)
        if event.get("schema") != CORPUS_EVENT_SCHEMA:
            errors.append(f"line_{line_number}:unsupported_schema")
        event_type = event.get("event_type")
        if event_type not in {"corpus_initialized", "item_registered"}:
            errors.append(f"line_{line_number}:unsupported_event_type")
        if not isinstance(event.get("payload"), Mapping):
            errors.append(f"line_{line_number}:payload_not_object")
        if event_type == "corpus_initialized" and len(events) != 0:
            errors.append(f"line_{line_number}:initialization_not_first")
        if event.get("sequence") != len(events):
            errors.append(f"line_{line_number}:sequence_mismatch")
        if event.get("previous_hash") != previous_hash:
            errors.append(f"line_{line_number}:previous_hash_mismatch")
        expected_hash = _event_hash(event)
        if event.get("event_hash") != expected_hash:
            errors.append(f"line_{line_number}:event_hash_mismatch")
        previous_hash = str(event.get("event_hash") or "")
        events.append(event)
    if not events or events[0].get("event_type") != "corpus_initialized":
        errors.append("missing_initialization_event")
    return events, {
        "chain_valid": not errors,
        "head_sha256": events[-1].get("event_hash") if events else None,
        "errors": errors,
    }


def _event(
    *, sequence: int, previous_hash: str, event_type: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    event = {
        "schema": CORPUS_EVENT_SCHEMA,
        "sequence": sequence,
        "recorded_at": _now(),
        "previous_hash": previous_hash,
        "event_type": event_type,
        "payload": dict(payload),
    }
    event["event_hash"] = _event_hash(event)
    return event


def _event_hash(event: Mapping[str, Any]) -> str:
    value = {key: item for key, item in event.items() if key != "event_hash"}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _append_event(path: Path, event: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timezone_aware_timestamp(value: Any, label: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return text

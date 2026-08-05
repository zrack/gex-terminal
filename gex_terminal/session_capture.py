"""Integrity-checked capture and replay helpers for normalized market sessions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from gex_terminal.contracts import parse_market_datetime
from gex_terminal.market_data_adapter import validate_normalized_message


CAPTURE_SCHEMA = "gex-terminal.captured-session.v1"
NORMALIZED_CONTRACT = "gex-terminal.normalized-message"


class CaptureIntegrityError(ValueError):
    """Raised when a captured session is incomplete or fails integrity checks."""


class CapturedSessionWriter:
    """Append normalized events to a crash-visible ``.partial`` file."""

    def __init__(
        self,
        output_path: str | Path,
        *,
        source: Mapping[str, Any] | str,
        model_inputs: Mapping[str, Any] | None = None,
        label: str | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        self.output_path = Path(output_path)
        self.partial_path = Path(f"{self.output_path}.partial")
        self.source = {"name": source} if isinstance(source, str) else dict(source)
        self.model_inputs = dict(model_inputs or {})
        self.label = label
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic_ns = monotonic_ns or time.monotonic_ns
        self._file = None
        self._lock = asyncio.Lock()
        self._started = False
        self._finalized = False
        self._sequence = 0
        self._started_monotonic_ns = 0
        self._first_event_time: str | None = None
        self._last_event_time: str | None = None
        self._fallback_count = 0
        self._schema_versions: set[int] = set()
        self._message_digest = hashlib.sha256()
        self._records_digest = hashlib.sha256()
        self._content_digest = hashlib.sha256()
        self.header: dict[str, Any] | None = None

    async def start(self) -> "CapturedSessionWriter":
        async with self._lock:
            if self._started:
                raise RuntimeError("captured session writer has already started")
            if self.output_path.exists() or self.partial_path.exists():
                raise FileExistsError(
                    f"capture target already exists: {self.output_path} or {self.partial_path}"
                )
            now = _aware_utc(self.clock())
            session_id = _session_id(now, self.source.get("symbol"), self.label)
            self.header = {
                "schema": CAPTURE_SCHEMA,
                "record_type": "header",
                "session_id": session_id,
                "created_at": _iso_utc(now),
                "label": self.label,
                "source": self.source,
                "model_inputs": self.model_inputs,
                "normalized_contract": NORMALIZED_CONTRACT,
                "time_contract": {
                    "order": "capture_sequence",
                    "event_time": "timezone-bearing ISO-8601",
                    "fallback": "received_time",
                },
            }
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                self.partial_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            self._file = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
            self._write_record(self.header)
            self._content_digest.update(_canonical_bytes(self.header) + b"\n")
            self._file.flush()
            self._started_monotonic_ns = self.monotonic_ns()
            self._started = True
        return self

    async def append(self, message: Mapping[str, Any] | str) -> dict[str, Any]:
        normalized = json.loads(message) if isinstance(message, str) else dict(message)
        validate_normalized_message(normalized)
        async with self._lock:
            self._require_open()
            received_at = _aware_utc(self.clock())
            received_time = _iso_utc(received_at)
            event_time, time_source = _resolve_event_time(normalized, received_time)
            if time_source == "received_time":
                self._fallback_count += 1

            message_bytes = _canonical_bytes(normalized)
            message_hash = hashlib.sha256(message_bytes).hexdigest()
            record_base = {
                "record_type": "event",
                "sequence": self._sequence,
                "event_time": event_time,
                "received_time": received_time,
                "received_offset_ns": max(
                    0, self.monotonic_ns() - self._started_monotonic_ns
                ),
                "time_source": time_source,
                "message_sha256": message_hash,
                "message": normalized,
            }
            record = {
                **record_base,
                "record_sha256": hashlib.sha256(
                    _canonical_bytes(record_base)
                ).hexdigest(),
            }
            record_bytes = _canonical_bytes(record)
            self._write_record(record)
            self._message_digest.update(message_bytes + b"\n")
            self._records_digest.update(record_bytes + b"\n")
            self._content_digest.update(record_bytes + b"\n")
            self._schema_versions.add(int(normalized.get("schema_version", 1)))
            if self._first_event_time is None:
                self._first_event_time = event_time
            self._last_event_time = event_time
            self._sequence += 1
            return record

    async def finalize(
        self,
        *,
        final_snapshot_record_id: str | None = None,
        feed_quality: Mapping[str, Any] | None = None,
    ) -> Path:
        async with self._lock:
            self._require_open()
            ended_at = _iso_utc(_aware_utc(self.clock()))
            records_digest = self._records_digest.hexdigest()
            footer_base = {
                "record_type": "footer",
                "status": "complete",
                "completed": True,
                "ended_at": ended_at,
                "event_count": self._sequence,
                "first_event_time": self._first_event_time,
                "last_event_time": self._last_event_time,
                "normalized_schema_versions": sorted(self._schema_versions),
                "message_sha256": self._message_digest.hexdigest(),
                "records_sha256": records_digest,
                "event_time_fallback_count": self._fallback_count,
                "final_snapshot_record_id": final_snapshot_record_id,
                "feed_quality": dict(feed_quality) if feed_quality is not None else None,
            }
            content_digest = self._content_digest.copy()
            content_digest.update(_canonical_bytes(footer_base) + b"\n")
            footer = {**footer_base, "content_sha256": content_digest.hexdigest()}
            self._write_record(footer)
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._file = None
            if self.output_path.exists():
                raise FileExistsError(f"capture target already exists: {self.output_path}")
            os.replace(self.partial_path, self.output_path)
            self._finalized = True
            return self.output_path

    async def abort(self, reason: str) -> Path:
        """Close an incomplete capture and intentionally retain ``.partial``."""
        async with self._lock:
            if self._file is not None:
                self._write_record({
                    "record_type": "abort",
                    "aborted_at": _iso_utc(_aware_utc(self.clock())),
                    "reason": str(reason)[:240],
                    "event_count": self._sequence,
                })
                self._file.flush()
                os.fsync(self._file.fileno())
                self._file.close()
                self._file = None
            return self.partial_path

    def _write_record(self, record: Mapping[str, Any]) -> None:
        if self._file is None:
            raise RuntimeError("captured session writer is not open")
        self._file.write(_canonical_text(record) + "\n")

    def _require_open(self) -> None:
        if not self._started or self._file is None or self._finalized:
            raise RuntimeError("captured session writer is not open")


class RecordingConsumerProxy:
    """Record validated normalized messages immediately before consumption."""

    def __init__(self, consumer, writer: CapturedSessionWriter) -> None:
        self.consumer = consumer
        self.writer = writer

    async def update_market_state(self, raw_message: str) -> None:
        await self.writer.append(raw_message)
        await self.consumer.update_market_state(raw_message)

    def __getattr__(self, name: str):
        return getattr(self.consumer, name)


def iter_captured_events(
    path: str | Path, *, verify: bool = True
) -> Iterable[dict[str, Any]]:
    """Yield capture event envelopes in canonical sequence order."""
    target = Path(path)
    if verify:
        _, _, events = _verify_capture(target)
        yield from events
        return
    with target.open(encoding="utf-8") as capture_file:
        for line in capture_file:
            if line.strip():
                record = json.loads(line)
                if record.get("record_type") == "event":
                    yield record


def inspect_captured_session(path: str | Path) -> dict[str, Any]:
    """Verify a complete capture and return a compact inventory record."""
    target = Path(path)
    header, footer, _ = _verify_capture(target)
    return _capture_inventory(target, header, footer)


def load_captured_session(
    path: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify once and return metadata plus messages from those same bytes."""
    target = Path(path)
    header, footer, events = _verify_capture(target)
    return (
        _capture_inventory(target, header, footer),
        [dict(event["message"]) for event in events],
    )


def _capture_inventory(
    path: Path,
    header: Mapping[str, Any],
    footer: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": header["schema"],
        "session_id": header["session_id"],
        "path": str(path),
        "label": header.get("label"),
        "source": header.get("source", {}),
        "model_inputs": header.get("model_inputs", {}),
        "event_count": footer["event_count"],
        "first_event_time": footer.get("first_event_time"),
        "last_event_time": footer.get("last_event_time"),
        "completed": bool(footer.get("completed")),
        "integrity_verified": True,
        "content_sha256": footer.get("content_sha256"),
        "event_time_fallback_count": footer.get("event_time_fallback_count", 0),
        "header": header,
        "footer": footer,
    }


def is_captured_session(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists() or target.name.endswith(".partial"):
        return False
    try:
        with target.open(encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    record = json.loads(line)
                    return (
                        record.get("record_type") == "header"
                        and record.get("schema") == CAPTURE_SCHEMA
                    )
    except (OSError, json.JSONDecodeError):
        return False
    return False


def default_capture_path(
    store_dir: str | Path,
    *,
    symbol: str,
    provider: str,
    clock: Callable[[], datetime] | None = None,
) -> Path:
    now = _aware_utc((clock or (lambda: datetime.now(timezone.utc)))())
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    safe_symbol = _slug(symbol) or "symbol"
    safe_provider = _slug(provider) or "provider"
    return Path(store_dir) / "captures" / f"{stamp}_{safe_symbol}_{safe_provider}.gex-session.jsonl"


def _verify_capture(
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    if path.name.endswith(".partial"):
        raise CaptureIntegrityError("incomplete .partial captures cannot be replayed")
    if not path.exists():
        raise FileNotFoundError(f"Captured session not found: {path}")

    header: dict[str, Any] | None = None
    footer: dict[str, Any] | None = None
    expected_sequence = 0
    message_digest = hashlib.sha256()
    records_digest = hashlib.sha256()
    content_digest = hashlib.sha256()
    footer_seen = False
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as capture_file:
        for line_number, line in enumerate(capture_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CaptureIntegrityError(
                    f"invalid capture JSON at line {line_number}"
                ) from exc
            record_type = record.get("record_type")
            if header is None:
                if record_type != "header":
                    raise CaptureIntegrityError("capture header must be the first record")
                if record.get("schema") != CAPTURE_SCHEMA:
                    raise CaptureIntegrityError(
                        f"unsupported captured-session schema: {record.get('schema')}"
                    )
                header = record
                content_digest.update(_canonical_bytes(record) + b"\n")
                continue
            if footer_seen:
                raise CaptureIntegrityError("capture contains records after its footer")
            if record_type == "footer":
                footer = record
                footer_seen = True
                continue
            if record_type != "event":
                raise CaptureIntegrityError(
                    f"unexpected capture record type at line {line_number}: {record_type}"
                )
            if record.get("sequence") != expected_sequence:
                raise CaptureIntegrityError(
                    f"capture sequence mismatch: expected {expected_sequence}, "
                    f"got {record.get('sequence')}"
                )
            message = record.get("message")
            if not isinstance(message, dict):
                raise CaptureIntegrityError("capture event message must be an object")
            try:
                validate_normalized_message(message)
            except (TypeError, ValueError) as exc:
                raise CaptureIntegrityError(
                    f"invalid normalized message at capture sequence {expected_sequence}: {exc}"
                ) from exc
            message_bytes = _canonical_bytes(message)
            expected_message_hash = hashlib.sha256(message_bytes).hexdigest()
            if record.get("message_sha256") != expected_message_hash:
                raise CaptureIntegrityError(
                    f"message hash mismatch at capture sequence {expected_sequence}"
                )
            record_base = dict(record)
            record_hash = record_base.pop("record_sha256", None)
            if record_hash != hashlib.sha256(_canonical_bytes(record_base)).hexdigest():
                raise CaptureIntegrityError(
                    f"record hash mismatch at capture sequence {expected_sequence}"
                )
            message_digest.update(message_bytes + b"\n")
            records_digest.update(_canonical_bytes(record) + b"\n")
            content_digest.update(_canonical_bytes(record) + b"\n")
            events.append(record)
            expected_sequence += 1

    if header is None:
        raise CaptureIntegrityError("capture is empty")
    if footer is None:
        raise CaptureIntegrityError("capture footer is missing")
    if footer.get("status") != "complete" or footer.get("completed") is not True:
        raise CaptureIntegrityError("capture footer does not mark a complete session")
    if footer.get("event_count") != expected_sequence:
        raise CaptureIntegrityError("capture event count does not match its footer")
    if footer.get("message_sha256") != message_digest.hexdigest():
        raise CaptureIntegrityError("capture aggregate message hash mismatch")
    digest = records_digest.hexdigest()
    if footer.get("records_sha256") != digest:
        raise CaptureIntegrityError("capture aggregate record hash mismatch")
    footer_base = dict(footer)
    declared_content_hash = footer_base.pop("content_sha256", None)
    content_digest.update(_canonical_bytes(footer_base) + b"\n")
    if declared_content_hash != content_digest.hexdigest():
        raise CaptureIntegrityError("capture full-content hash mismatch")
    return header, footer, tuple(events)


def _resolve_event_time(message: Mapping[str, Any], received_time: str) -> tuple[str, str]:
    for field in ("event_time", "timestamp"):
        parsed = parse_market_datetime(message.get(field))
        if parsed is not None:
            return _iso_utc(parsed), f"message.{field}"
    return received_time, "received_time"


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("capture clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return _canonical_text(value).encode("utf-8")


def _session_id(now: datetime, symbol: Any, label: Any) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    pieces = [stamp, _slug(symbol)]
    if label:
        pieces.append(_slug(label))
    return "_".join(piece for piece in pieces if piece)


def _slug(value: Any) -> str:
    return "".join(
        char.lower() if char.isalnum() else "_" for char in str(value or "")
    ).strip("_")

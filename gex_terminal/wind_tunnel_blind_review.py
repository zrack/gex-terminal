"""Commit a read of a verified futures flip before evaluating its later outcome."""

from datetime import datetime, timezone
import hashlib
from importlib.resources import files
from typing import Any, Mapping

from . import wind_tunnel as wind
from . import wind_tunnel_saved_investigation as saved
from .wind_tunnel_blind_replay import reveal_outcome, select_flip


OPERATION = "blind-review"
MAX_READ_CHARS = 4_000


class BlindReviewError(ValueError):
    """A path-free blind review input or lifecycle error."""


def calculation_identity() -> dict:
    identity = saved.calculation_identity()
    package = files("gex_terminal")
    for name in ("wind_tunnel_blind_review.py", "wind_tunnel_blind_replay.py"):
        identity["implementation"][name] = hashlib.sha256(package.joinpath(name).read_bytes()).hexdigest()
    return identity


def _read_text(value: Any) -> str:
    if not isinstance(value, str):
        raise BlindReviewError("Enter a read to commit before revealing the outcome.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value or len(value) > MAX_READ_CHARS or any(
        (ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in value
    ):
        raise BlindReviewError(f"Use a read of 1 to {MAX_READ_CHARS:,} characters.")
    return value


def normalize_request(request: Mapping[str, Any], symbol: str) -> dict:
    fields = {"schema", "operation", "capture_sha256", "sequence", "read", "committed_at"}
    if (not isinstance(request, Mapping) or set(request) - fields
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise BlindReviewError(f"Choose a saved {symbol} review with a committed read.")
    try:
        flip = saved._request({"capture_sha256": request.get("capture_sha256"),
                               "sequence": request.get("sequence")}, symbol)
        timestamp = datetime.fromisoformat(request.get("committed_at"))
        if timestamp.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("The commitment timestamp requires UTC")
    except (TypeError, ValueError, OverflowError) as exc:
        raise BlindReviewError(f"Invalid saved {symbol} flip identity or committed-read timestamp.") from exc
    return {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION,
            "capture_sha256": flip["capture_sha256"], "sequence": flip["sequence"],
            "read": _read_text(request.get("read")), "committed_at": timestamp.isoformat()}


async def _result(request: dict, replay, flip: dict) -> dict:
    try:
        outcome = await reveal_outcome(replay, request["sequence"], flip["after"]["as_of"])
    except (ValueError, OSError) as exc:
        raise BlindReviewError("The committed review was preserved. The saved outcome could not be evaluated.") from exc
    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{OPERATION}.v1", "version": wind.VERSION,
        "request": request, "request_sha256": wind._sha(request),
        "calculation": identity, "calculation_fingerprint": wind._sha(identity),
        "flip": flip, "commit": {key: request[key] for key in ("read", "committed_at")},
        "outcome": outcome,
        "limitations": {
            "predictive_validity": "unmeasured", "horizon_minutes": 30,
            "reproduction": f"Requires the original {replay.symbol} capture and a compatible calculation build.",
        },
    }
    result["result_sha256"] = wind._sha(result)
    return result


async def _select(replay, sequence: int | None) -> dict:
    try:
        return await select_flip(replay, sequence)
    except (ValueError, OSError) as exc:
        raise BlindReviewError(f"A valid saved {replay.symbol} flip could not be opened. Check the capture and selected event.") from exc


async def blind_review(request: Mapping[str, Any], replay) -> dict:
    if replay is None:
        raise BlindReviewError("Open the original saved capture to reproduce this review.")
    normalized = normalize_request(request, replay.symbol)
    try:
        await replay.verify_capture(normalized["capture_sha256"])
    except (ValueError, OSError) as exc:
        raise BlindReviewError(f"The original saved {replay.symbol} capture could not be verified for this review.") from exc
    flip = await _select(replay, normalized["sequence"])
    return await _result(normalized, replay, flip)


class BlindReview:
    """One review window, with its read locked before any reveal is evaluated."""

    def __init__(self, replay, sequence: int | None = None):
        if sequence is not None and (type(sequence) is not int or sequence < 1):
            raise BlindReviewError("Choose a valid saved flip sequence.")
        self.replay = replay
        self.sequence = sequence
        self.flip = None
        self.commit = None
        self.result = None
        self.receipt_id = None

    async def status(self) -> dict:
        if self.flip is None:
            self.flip = await _select(self.replay, self.sequence)
        status = {"stage": "blind", "flip": self.flip, "commit": self.commit}
        if self.commit is not None:
            status["stage"] = "committed"
        if self.result is not None:
            status.update(stage="revealed", result=self.result, receipt_sha256=self.receipt_id)
        return status

    async def commit_read(self, read: Any) -> dict:
        text = _read_text(read)
        if self.flip is None:
            await self.status()
        if self.commit is not None:
            if self.commit["read"] != text:
                raise BlindReviewError("The read is already committed for this review.")
            return self.commit
        self.commit = {"read": text, "committed_at": datetime.now(timezone.utc).isoformat()}
        return self.commit

    async def reveal(self) -> dict:
        if self.commit is None:
            raise BlindReviewError("Commit your read before revealing the outcome.")
        if self.result is None:
            selection = self.flip["request"]
            request = normalize_request({"capture_sha256": selection["capture_sha256"],
                                         "sequence": selection["sequence"], **self.commit}, self.replay.symbol)
            self.result = await _result(request, self.replay, self.flip)
        return self.result

    def restore(self, result: dict, receipt_id: str) -> None:
        self.flip = result["flip"]
        self.commit = result["commit"]
        self.result = result
        self.receipt_id = receipt_id

    def close(self) -> None:
        self.replay.close()

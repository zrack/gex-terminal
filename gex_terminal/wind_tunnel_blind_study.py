"""A reproducible cohort of blind ES flip reviews over frozen synthetic captures."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from . import wind_tunnel as wind
from . import wind_tunnel_blind_review as review
from .session_capture import CapturedSessionWriter
from .wind_tunnel_blind_replay import HORIZON_MINUTES, reveal_outcome, select_flip
from .wind_tunnel_saved_replay import SavedReplay


OPERATION = "blind-study"
_PROTOCOL = {
    "id": "es-blind-replay-study-v1",
    "version": 1,
    "title": "ES Blind Replay Study",
    "symbol": "ES",
    "source": "synthetic",
    "horizon_minutes": HORIZON_MINUTES,
    "baseline": "always_holds",
}
_PREDICTIONS = ("holds", "changes")


class BlindStudyError(ValueError):
    """An invalid submission, receipt binding, or study state."""


def calculation_identity() -> dict:
    identity = review.calculation_identity()
    name = "wind_tunnel_blind_study.py"
    module = files("gex_terminal").joinpath(name)
    identity["implementation"][name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def _fixture_events(case: int) -> list[dict]:
    """Build the frozen normalized event sequences in observed capture order."""
    opened = datetime(2026, 10, 11 + case, 15, 30, tzinfo=timezone.utc)
    strike = 5000 + 25 * (case - 1)
    base = {"schema_version": 2, "provider": "synthetic", "symbol": "ES"}
    expiry = (opened + timedelta(days=1)).replace(hour=20, minute=0)

    def tick(seconds: int, price: float) -> dict:
        return {**base, "type": "underlying_tick", "contract_id": "ESZ6",
                "event_time": wind._time(opened + timedelta(seconds=seconds)), "price": price}

    def option(seconds: int, side: str, volume: int) -> dict:
        return {
            **base, "type": "options_volume_tick", "contract_id": f"ESZ6-{expiry:%Y%m%d}-{strike}-{side}",
            "underlying_contract_id": "ESZ6", "option_type": side, "strike": strike, "volume": volume,
            "position_source": "open_interest", "volume_semantics": "cumulative", "instrument_class": "futures_option",
            "expiry": expiry.date().isoformat(), "expiry_timestamp": wind._time(expiry), "iv": .2,
            "iv_source": "provider", "contract_multiplier": 50, "sequence": seconds,
            "event_time": wind._time(opened + timedelta(seconds=seconds)),
        }

    if case == 1:
        return [tick(0, strike), option(1, "P", 10), option(2, "C", 40),
                tick(360, strike + 1.5), tick(720, strike - 2.25), tick(1440, strike + 4),
                tick(1802, strike + 3.5)]
    if case == 2:
        return [tick(0, strike), option(1, "C", 18), option(2, "P", 48),
                tick(360, strike - 2.25), tick(660, strike - 4.5), option(1050, "C", 90),
                tick(1320, strike + 1), tick(1802, strike - 1.5)]
    if case == 3:
        return [tick(0, strike), option(1, "P", 20), option(2, "C", 52),
                tick(300, strike + 2.5), tick(720, strike - 1)]
    return [tick(0, strike), option(1, "P", 35), option(2, "C", 12),
            tick(900, strike + 2), tick(1802, strike + 1)]


async def _write_fixture(path: Path, case: int, label: str) -> None:
    events = _fixture_events(case)
    observed = [datetime.fromisoformat(event["event_time"]) for event in events]
    times = iter([observed[0], *observed, observed[-1]])
    offsets = iter([0, *(int((time - observed[0]).total_seconds()) * 1_000_000_000 for time in observed)])
    writer = CapturedSessionWriter(
        path, source={"provider": "replay", "mode": "replay", "symbol": "ES", "synthetic": True},
        model_inputs={"days_to_expiry": .01, "risk_free_rate": .045,
                      "contract_multiplier": 50, "expiry_filter": "all"},
        label=label, clock=lambda: next(times), monotonic_ns=lambda: next(offsets),
    )
    try:
        await writer.start()
        for event in events:
            await writer.append(event)
        await writer.finalize()
    except BaseException:
        await writer.abort("Synthetic study capture generation interrupted.")
        raise


def _normalize_calls(calls: Mapping, cases: list[dict], symbol: str) -> dict:
    eligible = [case["id"] for case in cases if case["status"] == "ready"]
    if not isinstance(calls, Mapping) or set(calls) != set(eligible):
        raise BlindStudyError(f"Submit one call for each case with an eligible {symbol} flip.")
    normalized = {}
    for case_id in eligible:
        call = calls[case_id]
        if (not isinstance(call, Mapping) or set(call) - {"prediction", "read"}
                or call.get("prediction") not in _PREDICTIONS):
            raise BlindStudyError(f"Choose Holds or Changes for each eligible {symbol} flip.")
        normalized[case_id] = {"prediction": call["prediction"]}
        if "read" in call:
            note = call["read"]
            if isinstance(note, str) and not note.strip():
                continue
            try:
                normalized[case_id]["read"] = review._read_text(note)
            except review.BlindReviewError as exc:
                raise BlindStudyError(f"Use reads of at most {review.MAX_READ_CHARS:,} characters.") from exc
    return normalized


class BlindStudy:
    """Reveal only after all eligible case calls are locked together."""

    operation = OPERATION
    symbol = "ES"
    _protocol = _PROTOCOL
    _reproduction = "Uses the built-in ES study captures and a compatible calculation build."
    _binding_error = "The study receipt does not match the built-in captures and flip sequences."

    def __init__(self) -> None:
        self.result: dict | None = None
        self.receipt_id: str | None = None
        self._request: dict | None = None
        self._closed = False
        self._lock = asyncio.Lock()
        self._cases: list[dict] | None = None
        self._bindings: list[dict] = []
        self._directory: TemporaryDirectory | None = None
        self._replays: dict[str, SavedReplay] = {}

    async def _capture_sources(self) -> list[tuple[Path, str | None]]:
        self._directory = TemporaryDirectory(prefix="gex-es-blind-study-")
        sources = []
        for number in range(1, 5):
            path = Path(self._directory.name) / f"es-{number}.gex-session.jsonl"
            await _write_fixture(path, number, f"Saved ES case {number}")
            sources.append((path, None))
        return sources

    def _calculation_identity(self) -> dict:
        return calculation_identity()

    async def _prepare(self) -> None:
        if self._closed:
            raise BlindStudyError("The blind replay study is closed.")
        if self._cases is not None:
            return
        cases, bindings, replays = [], [], {}
        try:
            sources = await self._capture_sources()
            no_flip = f"The saved {self.symbol} capture has no reproducible net-GEX flip."
            for number, (path, checksum) in enumerate(sources, start=1):
                case_id = f"{self.symbol.lower()}-{number}"
                label = f"Saved {self.symbol} case {number}"
                replay = replays[case_id] = SavedReplay(path, checksum, symbol=self.symbol)
                case = {"id": case_id, "label": label, "status": "ready"}
                if checksum is not None:
                    case["capture_sha256"] = checksum
                try:
                    case["flip"] = await select_flip(replay)
                except (ValueError, OSError) as exc:
                    if str(exc) != no_flip:
                        raise BlindStudyError(f"{label} could not be opened as a verified {self.symbol} capture.") from exc
                    case["status"] = "no_flip"
                    replay.close()
                    replays.pop(case_id)
                sequence = case["flip"]["request"]["sequence"] if "flip" in case else None
                bindings.append({"id": case_id, "sequence": sequence, "capture_sha256": replay.capture_sha256})
                cases.append(case)
            if self._closed:
                raise BlindStudyError("The blind replay study is closed.")
        except BaseException:
            for replay in replays.values():
                replay.close()
            self._cleanup_directory()
            raise
        self._replays, self._cases, self._bindings = replays, cases, bindings

    async def status(self) -> dict:
        if self._cases is None:
            async with self._lock:
                await self._prepare()
        status = {"stage": "blind", "protocol": self._protocol, "cases": self._cases}
        if self.result is not None:
            status.update(stage="revealed", result=self.result, receipt_sha256=self.receipt_id)
        elif self._request is not None:
            status.update(stage="committed", calls=self._request["calls"], submitted_at=self._request["submitted_at"])
        return deepcopy(status)

    def _canonical_request(self, calls: dict, submitted_at: str) -> dict:
        return {
            "schema": wind.REQUEST_SCHEMA, "operation": self.operation, "protocol_sha256": wind._sha(self._protocol),
            "cases": self._bindings, "calls": calls, "submitted_at": submitted_at,
        }

    @classmethod
    def _request_timestamp(cls, request: Mapping) -> str:
        fields = {"schema", "operation", "protocol_sha256", "cases", "calls", "submitted_at"}
        if (not isinstance(request, Mapping) or set(request) != fields or request["schema"] != wind.REQUEST_SCHEMA
                or request["operation"] != cls.operation or request["protocol_sha256"] != wind._sha(cls._protocol)):
            raise BlindStudyError(f"The request does not match this {cls.symbol} blind replay protocol.")
        try:
            timestamp = datetime.fromisoformat(request["submitted_at"])
            if timestamp.utcoffset() != timedelta(0):
                raise ValueError("The submission timestamp requires UTC")
            return timestamp.isoformat()
        except (TypeError, ValueError, OverflowError) as exc:
            raise BlindStudyError("The request contains an invalid submission time.") from exc

    async def _reproduce(self, request: Mapping) -> dict:
        try:
            timestamp = self._request_timestamp(request)
            try:
                case_hash = wind._sha(request["cases"])
            except (TypeError, ValueError, OverflowError) as exc:
                raise BlindStudyError("The request contains an invalid case binding.") from exc
            await self._prepare()
            if case_hash != wind._sha(self._bindings):
                raise BlindStudyError(self._binding_error)
            calls = _normalize_calls(request["calls"], self._cases, self.symbol)
            self._request = self._canonical_request(calls, timestamp)
            return await self._reveal()
        finally:
            self.close()

    async def submit(self, calls: Mapping) -> dict:
        async with self._lock:
            await self._prepare()
            normalized = _normalize_calls(calls, self._cases, self.symbol)
            if self._request is None:
                self._request = self._canonical_request(normalized, datetime.now(timezone.utc).isoformat())
            elif self._request["calls"] != normalized:
                raise BlindStudyError("The calls are already committed for this study.")
            if self.result is None:
                self.result = await self._reveal()
            return deepcopy(self.result)

    async def _reveal(self) -> dict:
        cases = []
        summary = {"total": len(self._cases), "scored": 0, "correct": 0,
                   "baseline_correct": 0, "unscored": 0, "no_flip": 0}
        for case in self._cases:
            if case["status"] == "no_flip":
                summary["no_flip"] += 1
                cases.append(case)
                continue
            case_id, flip = case["id"], case["flip"]
            call = self._request["calls"][case_id]
            try:
                outcome = await reveal_outcome(self._replays[case_id], flip["request"]["sequence"],
                                               flip["after"]["as_of"])
            except (ValueError, OSError) as exc:
                raise BlindStudyError("The submitted calls were preserved. The outcomes could not be evaluated.") from exc
            actual = correct = None
            status = "unscored"
            if outcome["status"] == "available":
                sign = outcome["summary"]["net_sign"]
                actual = "holds" if sign == flip["after"]["summary"]["net_sign"] else "changes"
                correct = call["prediction"] == actual
                status = "scored"
                summary["correct"] += correct
                summary["baseline_correct"] += actual == "holds"
            summary[status] += 1
            cases.append({**case, "status": status, "call": call, "outcome": outcome,
                          "actual": actual, "correct": correct})
        identity = self._calculation_identity()
        result = {
            "schema": f"gex-terminal.wind-tunnel.{self.operation}.v1", "version": wind.VERSION,
            "request": self._request, "request_sha256": wind._sha(self._request),
            "calculation": identity, "calculation_fingerprint": wind._sha(identity),
            "protocol": self._protocol, "cases": cases, "summary": summary,
            "limitations": {"predictive_validity": "unmeasured", "source": self._protocol["source"],
                            "reproduction": self._reproduction},
        }
        result["result_sha256"] = wind._sha(result)
        return result

    def restore(self, result: dict, receipt_id: str) -> None:
        """Restore a result after receipt verification and reproduction."""
        self.result = deepcopy(result)
        self.receipt_id = receipt_id
        self._request = self.result["request"]
        self._bindings = self._request["cases"]
        self._cases = [
            {**{key: case[key] for key in ("id", "label", "flip", "capture_sha256") if key in case},
             "status": "ready" if "flip" in case else "no_flip"}
            for case in self.result["cases"]
        ]

    def close(self) -> None:
        self._closed = True
        for replay in self._replays.values():
            replay.close()
        self._replays.clear()
        self._cleanup_directory()

    def _cleanup_directory(self) -> None:
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None


async def blind_study(request: Mapping) -> dict:
    """Reproduce the exact submitted study using the built-in cohort."""
    return await BlindStudy()._reproduce(request)

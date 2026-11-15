"""Index and reconstruct point-in-time flips from an explicit saved futures capture."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import tempfile
import threading

from . import wind_tunnel as wind
from .consumer import StatefulGexConsumer
from .contracts import parse_market_datetime
from .engine import IntradayGexEngine
from .pricing_assumptions import is_priced_contract
from .saved_workspace import MULTIPLIERS, _assumptions
from .session_capture import verify_captured_session_file
from .wind_tunnel_checkpoint import build_terminal_checkpoint


EXACT_EVENT_LIMIT = 5000
AMERICAN_ROW_EVALUATION_BUDGET = 12_000
MAX_SAMPLED_POINTS = 256
MIN_SAMPLED_POINTS = 12


@dataclass(frozen=True)
class _Point:
    sequence: int
    accepted_sequence: int
    offset: int
    as_of: str | None
    sign: int | None
    net_gex: float | None


def _read_record(stream) -> dict:
    # Complete captures allow blank lines while hashing the exact source bytes.
    while line := stream.readline():
        if line.strip():
            return json.loads(line)
    raise ValueError("The verified capture ended before the requested sequence")


def _verified_source(path: Path, expected: str | None, stopped: threading.Event, symbol: str):
    stream = tempfile.TemporaryFile(mode="w+b", prefix="gex-saved-flips-")
    first = last = None
    has_underlying = False
    american_rows: set[tuple] = set()

    def inspect(event):
        nonlocal first, last, has_underlying
        if stopped.is_set():
            raise ValueError("Saved capture verification cancelled")
        message = event["message"]
        timestamp = parse_market_datetime(message.get("event_time") or message.get("timestamp"))
        if (message.get("symbol") != symbol or timestamp is None or event.get("time_source") == "received_time"
                or parse_market_datetime(event.get("event_time")) != timestamp):
            raise ValueError(f"Saved {symbol} replay requires {symbol} events with authoritative event times")
        first = min(first, timestamp) if first is not None else timestamp
        last = max(last, timestamp) if last is not None else timestamp
        has_underlying = has_underlying or message["type"] == "underlying_tick"
        if message.get("pricing_model") == "american_futures_crr" and is_priced_contract(message):
            american_rows.add((message.get("provider"), message.get("contract_id")))
            if len(american_rows) > 5000:
                raise ValueError("Saved replay exceeds the supported contract limit")

    try:
        header, footer, stats = verify_captured_session_file(path, copy_to=stream, on_event=inspect)
        if expected is not None and stats["sha256"] != expected:
            raise ValueError("The saved capture differs from the requested source")
        source = header.get("source")
        if (header.get("normalized_contract") != "gex-terminal.normalized-message"
                or not isinstance(source, dict) or source.get("symbol") != symbol
                or not isinstance(header.get("model_inputs"), dict) or not has_underlying):
            raise ValueError(f"Choose a completed, normalized {symbol} capture")
        assumptions, _ = _assumptions(header["model_inputs"], symbol)
        stream.seek(0)
        _read_record(stream)
        return stream, assumptions, {
            "capture_sha256": stats["sha256"], "capture_content_sha256": footer["content_sha256"],
            "event_count": stats["event_count"], "first_as_of": wind._time(first), "last_as_of": wind._time(last),
            "american_rows": len(american_rows),
        }
    except BaseException:
        stream.close()
        raise


def _clone(consumer: StatefulGexConsumer) -> StatefulGexConsumer:
    # Only the scanner owns this consumer. Its asyncio lock has no waiters and
    # each bracket probe receives an independent lock and detached market state.
    return copy.deepcopy(consumer, {id(consumer.state_lock): asyncio.Lock()})


class SavedReplay:
    """Own a detached verified copy and a compact in-memory flip index."""

    def __init__(self, path: Path | str, capture_sha256: str | None = None, *, symbol: str = "ES"):
        if symbol not in MULTIPLIERS:
            raise ValueError("Choose an ES or NQ saved replay")
        if capture_sha256 is not None and (not isinstance(capture_sha256, str)
                                           or not re.fullmatch(r"[0-9a-f]{64}", capture_sha256)):
            raise ValueError("Saved capture digest must be a SHA-256 checksum")
        self.symbol = symbol
        self.path = Path(path)
        self.capture_sha256 = capture_sha256
        self._lock = asyncio.Lock()
        self._closed = False
        self._stream = None
        self._settings = None
        self._metadata = None
        self._first_offset = None
        self._timeline = None
        self._last_reconstruction = None

    def close(self) -> None:
        self._closed = True
        self._last_reconstruction = None
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    async def _prepare(self) -> None:
        if self._closed:
            raise ValueError("The saved replay is closed")
        if self._stream is not None:
            return
        stopped = threading.Event()
        preparation = asyncio.create_task(asyncio.to_thread(
            _verified_source, self.path, self.capture_sha256, stopped, self.symbol))
        try:
            stream, values, metadata = await asyncio.shield(preparation)
        except asyncio.CancelledError:
            stopped.set()
            try:
                abandoned, _, _ = await preparation
                abandoned.close()
            except Exception:
                pass
            raise
        if self._closed:
            stream.close()
            raise ValueError("The saved replay is closed")
        self._stream = stream
        self._metadata = metadata
        self.capture_sha256 = metadata["capture_sha256"]
        self._first_offset = stream.tell()
        self._settings = {
            **wind.DEFAULTS, "schema": wind.REQUEST_SCHEMA, "operation": "calculate",
            "session": "terminal-checkpoint", "checkpoint": 0, "model": wind.CHECKPOINT_MODEL,
            "fallback_dte": values["days_to_expiry"], "risk_free_rate": values["risk_free_rate"],
        }
        self._multiplier = values["contract_multiplier"]

    async def verify_capture(self, checksum: str) -> None:
        """Require the exact capture identity before reconstructing any prefix."""
        async with self._lock:
            if self.capture_sha256 is None or self.capture_sha256 == checksum:
                await self._prepare()
            if self.capture_sha256 != checksum:
                raise ValueError("The saved capture differs from the requested source")

    def _consumer(self) -> StatefulGexConsumer:
        instance = StatefulGexConsumer(IntradayGexEngine(self._multiplier), target_underlying=self.symbol,
                                       risk_free_rate=self._settings["risk_free_rate"], data_mode="replay")
        instance.mark_connected()
        return instance

    def _capture_metadata(self) -> dict:
        return {key: value for key, value in self._metadata.items() if key != "american_rows"}

    def _event(self, offset: int) -> tuple[dict, int]:
        if self._stream is None:
            raise ValueError("The saved replay is closed")
        if self._stream.tell() != offset:
            self._stream.seek(offset)
        event = _read_record(self._stream)
        return event, self._stream.tell()

    async def _apply(self, consumer: StatefulGexConsumer, event: dict) -> bool:
        accepted = await consumer.update_market_state(json.dumps(event["message"]))
        if consumer.malformed_message_count:
            raise ValueError("Saved capture contains conflicting market state")
        if event["sequence"] % 256 == 255:
            await asyncio.sleep(0)
        return accepted

    async def _point(self, consumer, sequence, accepted_sequence, offset) -> _Point:
        as_of = consumer.market_time
        sign = net_gex = None
        if consumer.current_spot and as_of is not None:
            frozen = await consumer.capture_wind_tunnel_state()
            mode = frozen["calculation_mode"]
            rows = tuple(sorted(frozen["rows"], key=lambda row: (row["provider"], row["contract_id"], row["position_source"])))
            checkpoint = wind._Checkpoint({}, consumer.current_spot, as_of, rows, mode, self._multiplier)
            try:
                summary = wind._state(checkpoint, self._settings, details=False)["summary"]
            except ValueError:
                # An unevaluable numerical point cannot establish a sign flip.
                summary = None
            if summary is not None:
                sign, net_gex = summary["net_sign"], summary["total_net_gex"]
        return _Point(sequence, accepted_sequence, offset, wind._time(as_of) if as_of else None, sign, net_gex)

    async def _localize(self, left: _Point, right: _Point, left_consumer) -> tuple[_Point, _Point] | None:
        """Find one actual transition inside a sampled opposing-sign bracket."""
        while right.sequence - left.sequence > 1:
            midpoint = (left.sequence + right.sequence) // 2
            probe = _clone(left_consumer)
            accepted_sequence, offset = left.accepted_sequence, left.offset
            for sequence in range(left.sequence + 1, midpoint + 1):
                event, offset = self._event(offset)
                if await self._apply(probe, event):
                    accepted_sequence = sequence
            middle = await self._point(probe, midpoint, accepted_sequence, offset)
            if not middle.sign:
                return None
            if middle.sign == left.sign:
                left, left_consumer = middle, probe
            else:
                right = middle
            await asyncio.sleep(0)
        if right.accepted_sequence != right.sequence:
            raise ValueError("The localized flip has no accepted driving update")
        return left, right

    @staticmethod
    def _marker(before: _Point, after: _Point) -> dict:
        return {"sequence": after.sequence, "before_sequence": before.accepted_sequence,
                "as_of": after.as_of, "before_as_of": before.as_of,
                "before_sign": before.sign, "after_sign": after.sign,
                "before_gex": before.net_gex, "after_gex": after.net_gex}

    async def timeline(self) -> dict:
        async with self._lock:
            await self._prepare()
            if self._timeline is not None:
                return copy.deepcopy(self._timeline)
            count = self._metadata["event_count"]
            american_rows = self._metadata["american_rows"]
            pricing_budget = AMERICAN_ROW_EVALUATION_BUDGET // max(american_rows, 1)
            exact = count <= EXACT_EVENT_LIMIT and count <= max(64, pricing_budget)
            samples = min(MAX_SAMPLED_POINTS, max(MIN_SAMPLED_POINTS, pricing_budget))
            stride = 1 if exact else max(1, (count + samples - 1) // samples)
            markers = []
            unresolved = evaluated = unavailable = zero = 0
            previous = previous_consumer = None
            accepted_sequence = -1
            has_priced_option_update = False
            sampled_first_candidate = False
            offset = self._first_offset
            consumer = self._consumer()
            async with consumer.offline_projection_batch():
                for sequence in range(count):
                    event, offset = self._event(offset)
                    accepted = await self._apply(consumer, event)
                    if accepted:
                        accepted_sequence = sequence
                        message = event["message"]
                        if message["type"] == "options_volume_tick" and message["volume"] > 0:
                            has_priced_option_update = has_priced_option_update or is_priced_contract(message)
                    if exact and not accepted:
                        continue
                    first_ready = (accepted and not sampled_first_candidate and consumer.current_spot
                                   and has_priced_option_update)
                    if not exact and not first_ready and (sequence + 1) % stride and sequence + 1 != count:
                        continue
                    if first_ready:
                        sampled_first_candidate = True
                    current = await self._point(consumer, sequence, accepted_sequence, offset)
                    evaluated += 1
                    unavailable += current.sign is None
                    zero += current.sign == 0
                    if previous is not None and previous.sign and current.sign == -previous.sign:
                        pair = (previous, current) if exact else await self._localize(previous, current, previous_consumer)
                        if pair is None:
                            unresolved += 1
                        else:
                            markers.append(self._marker(*pair))
                    previous = current
                    if not exact and current.sign:
                        previous_consumer = _clone(consumer)
                    await asyncio.sleep(0)
            self._timeline = {**self._capture_metadata(), "method": "every_accepted_event" if exact else "sampled_then_localized",
                              "sample_stride_events": stride, "sampled_points": evaluated,
                              "unavailable_points": unavailable, "zero_points": zero,
                              "unresolved_brackets": unresolved, "markers": markers}
            return copy.deepcopy(self._timeline)

    async def _checkpoint(self, consumer, sequence: int, event_digest: str) -> wind._Checkpoint:
        # Receipt health describes the saved prefix, independent of wall time
        # spent parsing rejected events or a busy disk between accepted events.
        consumer.last_message_at = None
        market = self.symbol.lower()
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=self._settings["fallback_dte"],
                                                  source_label=f"Saved {self.symbol} capture {self.capture_sha256[:12]}")
        checkpoint = await wind._checkpoint({"terminal_checkpoint": artifact})
        source = {**checkpoint.source, **self._capture_metadata(), "session": f"saved-{market}",
                  "source_kind": f"saved_{market}_capture", "source_sha256": self.capture_sha256,
                  "checkpoint": sequence, "sequence": sequence, "event_sha256": event_digest,
                  "later_events_excluded": self._metadata["event_count"] - sequence - 1}
        return replace(checkpoint, source=source)

    async def _reconstruct(self, sequence: int):
        consumer = self._consumer()
        previous = None
        offset = self._first_offset
        async with consumer.offline_projection_batch():
            for _ in range(sequence):
                event, offset = self._event(offset)
                if await self._apply(consumer, event):
                    previous = event
            if previous is None:
                raise ValueError("No accepted market state precedes this saved event")
            before = await self._checkpoint(consumer, previous["sequence"], previous["message_sha256"])
            event, _ = self._event(offset)
            if not await self._apply(consumer, event):
                raise ValueError("The saved driving update was not accepted")
            after = await self._checkpoint(consumer, sequence, event["message_sha256"])
        return sequence, before, after, event

    async def investigation(self, sequence: int, remove_update: bool) -> dict:
        if type(sequence) is not int or sequence < 1 or type(remove_update) is not bool:
            raise ValueError("Choose a saved flip sequence and a boolean removal flag")
        async with self._lock:
            await self._prepare()
            if sequence >= self._metadata["event_count"]:
                raise ValueError("Saved flip sequence is outside the capture")
            if self._last_reconstruction is None or self._last_reconstruction[0] != sequence:
                self._last_reconstruction = await self._reconstruct(sequence)
            _, before, after, event = copy.deepcopy(self._last_reconstruction)
            # Omit the final update while retaining its cutoff for model time.
            # An underlying identity or quote introduced only by that event
            # remains absent. The evaluation at the cutoff can still expire rows.
            counterfactual = replace(before, as_of=after.as_of, source={
                **before.source, "as_of": wind._time(after.as_of), "omitted_sequence": sequence,
            }) if remove_update else None
            details = {key: event["message"][key] for key in
                       ("type", "provider", "contract_id", "strike", "option_type", "volume", "expiry",
                        "expiry_timestamp", "position_source", "volume_semantics", "price", "underlying_contract_id")
                       if key in event["message"]}
            details.update(sequence=sequence, as_of=wind._time(after.as_of), event_time=event["event_time"],
                           event_sha256=event["message_sha256"])
            return {"capture_sha256": self.capture_sha256, "event": details, "before": before, "after": after,
                    "counterfactual": counterfactual, "model_request": dict(self._settings)}


# Existing Python consumers use the ES name. Its default remains ES.
SavedESReplay = SavedReplay

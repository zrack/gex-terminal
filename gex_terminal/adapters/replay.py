import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from gex_terminal.contracts import parse_market_datetime
from gex_terminal.market_data_adapter import MarketDataAdapter, dumps_normalized_message
from gex_terminal.market_data_adapter import AdapterInfo
from gex_terminal.session_capture import (
    is_captured_session, iter_verified_captured_events, iter_verified_capture_stream,
    open_verified_capture,
)
from gex_terminal.package_data import replay_data_path


ADAPTER_INFO = AdapterInfo(
    name="replay",
    label="Replay JSONL",
    status="offline-certified",
    notes="Local normalized JSONL replay adapter for demos, screenshots, and deterministic testing.",
)


class ReplayAdapter(MarketDataAdapter):
    """Feeds normalized JSONL market-data events into the consumer."""

    def __init__(
        self,
        consumer,
        replay_path: str | Path,
        delay_seconds: float = 0.05,
        loop: bool = False,
        *,
        replay_clock: str = "auto",
        replay_speed: float = 1.0,
        max_gap_seconds: float | None = None,
        strict_event_time: bool = False,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.consumer = consumer
        requested_path = Path(replay_path)
        if (
            not requested_path.exists()
            and requested_path.parent.name == "sample_data"
            and replay_data_path(requested_path.name).exists()
        ):
            requested_path = replay_data_path(requested_path.name)
        self.replay_path = requested_path
        self.delay_seconds = delay_seconds
        self.loop = loop
        self.replay_clock = _normalize_replay_clock(replay_clock)
        self.replay_speed = float(replay_speed)
        self.max_gap_seconds = (
            None if max_gap_seconds is None else float(max_gap_seconds)
        )
        self.strict_event_time = bool(strict_event_time)
        self.sleep = sleep
        self.clock_regression_count = 0
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if self.replay_speed <= 0:
            raise ValueError("replay_speed must be positive")
        if self.max_gap_seconds is not None and self.max_gap_seconds < 0:
            raise ValueError("max_gap_seconds must be non-negative")

    async def stream_market_data(self) -> None:
        if not self.replay_path.exists():
            raise FileNotFoundError(f"Replay file not found: {self.replay_path}")

        self.consumer.mark_connected()
        verified_stream = None
        try:
            if is_captured_session(self.replay_path):
                # Full local sessions may be hundreds of MB. Verify before the
                # first event, off the UI loop, and replay the detached disk copy.
                verification_cancelled = threading.Event()
                preparation = asyncio.create_task(asyncio.to_thread(
                    open_verified_capture, self.replay_path, cancelled=verification_cancelled.is_set,
                ))
                try:
                    verified_stream = await asyncio.shield(preparation)
                except asyncio.CancelledError:
                    verification_cancelled.set()
                    # The worker owns a temporary file; settle and close it even
                    # when the UI is closed during its verification pass.
                    try:
                        abandoned = await preparation
                        abandoned.close()
                    except Exception:
                        pass
                    raise
            while True:
                resolved_clock = ("event" if verified_stream is not None and self.replay_clock == "auto"
                                  else self._resolved_clock())
                previous_event_time: datetime | None = None
                for index, (message, event_time) in enumerate(self._load_replay_items(verified_stream)):
                    if resolved_clock == "event":
                        current_event_time = parse_market_datetime(event_time)
                        if current_event_time is None:
                            if self.strict_event_time:
                                raise ValueError(
                                    "event-time replay requires timezone-bearing event times"
                                )
                            delay = 0.0
                        elif previous_event_time is None:
                            delay = 0.0
                        else:
                            source_gap = (
                                current_event_time - previous_event_time
                            ).total_seconds()
                            if source_gap < 0:
                                self.clock_regression_count += 1
                                if self.strict_event_time:
                                    raise ValueError(
                                        "captured event time regressed while sequence remained ordered"
                                    )
                                self._record_clock_regression_note()
                                source_gap = 0.0
                            if self.max_gap_seconds is not None:
                                source_gap = min(source_gap, self.max_gap_seconds)
                            delay = source_gap / self.replay_speed
                        if delay:
                            await self.sleep(delay)
                        if current_event_time is not None:
                            previous_event_time = current_event_time

                    await self.consumer.update_market_state(dumps_normalized_message(message))
                    if resolved_clock == "fixed":
                        await self.sleep(self.delay_seconds)
                    elif index % 500 == 499:
                        # Fast loading must still permit drawing and quitting.
                        await asyncio.sleep(0)

                if not self.loop:
                    break
        finally:
            if verified_stream is not None:
                verified_stream.close()
            self.consumer.mark_disconnected()

    def _load_messages(self) -> Iterable[dict]:
        """Compatibility wrapper returning normalized messages only."""
        for message, _ in self._load_replay_items():
            yield message

    def _load_replay_items(self, verified_stream=None) -> Iterable[tuple[dict, str | None]]:
        if verified_stream is not None:
            for event in iter_verified_capture_stream(verified_stream):
                yield event["message"], event.get("event_time")
            return
        if is_captured_session(self.replay_path):
            for event in iter_verified_captured_events(self.replay_path):
                yield event["message"], event.get("event_time")
            return

        with self.replay_path.open(encoding="utf-8") as replay_file:
            for line_number, line in enumerate(replay_file, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    message = json.loads(line)
                    yield message, message.get("event_time") or message.get("timestamp")
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in replay file {self.replay_path} at line {line_number}"
                    ) from exc

    def _resolved_clock(self) -> str:
        if self.replay_clock != "auto":
            return self.replay_clock
        return "event" if is_captured_session(self.replay_path) else "fixed"

    def _record_clock_regression_note(self) -> None:
        method = getattr(self.consumer, "record_quality_note", None)
        if method:
            method(
                f"Replay preserved capture sequence across {self.clock_regression_count} "
                "event-time regression(s)"
            )


def _normalize_replay_clock(value: str) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "fixed": "fixed",
        "event": "event",
        "event_time": "event",
        "none": "none",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            "replay_clock must be one of: auto, fixed, event, event_time, none"
        ) from exc

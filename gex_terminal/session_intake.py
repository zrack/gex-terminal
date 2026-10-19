"""Ephemeral, bounded local-session intake for the offline Wind Tunnel.

Captured bytes are verified before any input is projected into a public result.
Only normalized calculation fields survive; paths, labels, account metadata,
and arbitrary capture extensions are never copied to browser responses.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import math
import re
import secrets
from typing import Any

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.contracts import parse_market_datetime
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.session_capture import CaptureIntegrityError, NORMALIZED_CONTRACT, verify_captured_session_bytes
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, checkpoint_transport

MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 5000
MAX_INTAKES = 4
MAX_CHECKPOINT_CHOICES = 200
_PROVIDERS = {"databento", "tradovate", "yfinance", "replay", "synthetic", "demo", "legacy"}
_MODES = {"live", "replay", "demo"}
_MULTIPLIERS = {"ES": 50, "MES": 5, "NQ": 20, "MNQ": 2}
_MESSAGE_FIELDS = {
    "schema_version", "type", "provider", "contract_id", "underlying_contract_id", "symbol",
    "price", "strike", "option_type", "volume", "iv", "iv_source", "expiry", "expiry_timestamp",
    "days_to_expiry", "instrument_class", "pricing_model", "volume_semantics", "position_source",
    "open_interest", "open_interest_reference_date", "open_interest_update_action", "aggressor_side",
    "direction_source", "contract_multiplier", "contract_multiplier_source", "event_time", "timestamp",
    "sequence", "provider_trade_event_id", "iv_provenance",
    "exercise_style", "exercise_style_source", "provider_cfi",
}
_IV_FIELDS = {
    "method", "status", "option_price", "option_price_source", "underlying_price",
    "underlying_price_source", "underlying_price_age_ms", "maximum_underlying_age_ms", "risk_free_rate",
    "time_to_expiry_years", "iterations", "absolute_price_error",
}
_QUALITY_COUNTERS = {
    "message_count", "malformed_count", "dropped_count", "duplicate_message_count",
    "cumulative_reset_count", "fallback_iv_tick_count",
}


def _recorded_quality(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"available": False, "scope": "recorded_end_of_session"}
    if not isinstance(value, dict):
        return result
    status, health = value.get("status"), value.get("health")
    if isinstance(status, str) and status in {"SIM", "REPLAY", "CONNECTED", "LIVE", "STALE", "DISCONNECTED"}:
        result["status"] = status
    if isinstance(health, str) and health in {"healthy", "degraded", "down", "stale", "entitlement", "simulated"}:
        result["health"] = health
    for name in _QUALITY_COUNTERS:
        number = value.get(name)
        if type(number) is int and 0 <= number <= 10**12:
            result[name] = number
    result["available"] = len(result) > 2
    return result


class IntakeError(ValueError):
    """A fixed, safe intake explanation suitable for the local browser."""


@dataclass(frozen=True)
class _Session:
    messages: tuple[str, ...]
    symbol: str
    model_inputs: dict[str, Any]
    synthetic: bool
    content_sha256: str


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IntakeError(f"Captured {name} must be a finite number.")
    try:
        parsed = float(value)
    except (OverflowError, ValueError):
        raise IntakeError(f"Captured {name} must be a finite number.") from None
    if not math.isfinite(parsed) or not low <= parsed <= high:
        raise IntakeError(f"Captured {name} is outside supported bounds.")
    return parsed


def _symbol(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9.\-]{1,16}", value):
        raise IntakeError("Capture requires one bounded uppercase underlying symbol.")
    return value


def _safe_message(message: dict[str, Any]) -> dict[str, Any]:
    """Project only calculation fields after full raw capture verification."""
    result = {key: value for key, value in message.items() if key in _MESSAGE_FIELDS}
    if isinstance(result.get("iv_provenance"), dict):
        result["iv_provenance"] = {key: value for key, value in result["iv_provenance"].items() if key in _IV_FIELDS}
    # Provider namespace has identity meaning, so an unknown namespace gets a
    # deterministic opaque alias rather than being collapsed into one provider.
    provider = result.get("provider")
    if provider is not None:
        if not isinstance(provider, str):
            raise IntakeError("Normalized provider identifiers must be text.")
        provider = provider.lower()
        result["provider"] = provider if provider in _PROVIDERS else "local-" + hashlib.sha256(provider.encode()).hexdigest()[:20]
    for name in ("contract_id", "underlying_contract_id"):
        if name in result:
            result[name] = "contract-" + hashlib.sha256(str(result[name]).strip().encode()).hexdigest()
    return result


class SessionIntake:
    """Own at most four verified captures in memory until discard or shutdown.

    A failed inspection never replaces a previously verified intake. Once full,
    callers must explicitly discard an intake rather than silently evicting it.
    Captures are not source-authenticated and confer no redistribution rights.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}

    def inspect(self, data: bytes) -> dict[str, Any]:
        if not isinstance(data, bytes) or not data or len(data) > MAX_CAPTURE_BYTES:
            raise IntakeError("Choose a nonempty complete captured session no larger than 4 MiB.")
        try:
            header, footer, events = verify_captured_session_bytes(
                data, max_bytes=MAX_CAPTURE_BYTES, max_events=MAX_EVENTS,
            )
        except (CaptureIntegrityError, ValueError, TypeError, OverflowError, RecursionError):
            raise IntakeError("Capture verification failed. Use a complete, unchanged supported .gex-session.jsonl capture.") from None
        if not events:
            raise IntakeError("Capture contains no market events.")
        if header.get("normalized_contract") != NORMALIZED_CONTRACT:
            raise IntakeError("Capture declares an unsupported normalized message contract.")
        if type(footer.get("event_count")) is not int or any(type(event.get("sequence")) is not int for event in events):
            raise IntakeError("Capture event counts and sequences must be integers.")
        source = header.get("source")
        inputs = header.get("model_inputs")
        if not isinstance(source, dict) or not isinstance(inputs, dict):
            raise IntakeError("Capture source and model inputs must be objects.")
        underlying_symbols = {
            _symbol(event["message"].get("symbol")) for event in events
            if event["message"]["type"] == "underlying_tick"
        }
        if len(underlying_symbols) != 1:
            raise IntakeError("Capture requires exactly one underlying symbol and its spot events.")
        symbol = next(iter(underlying_symbols))
        for supplied in (source.get("symbol"), inputs.get("symbol")):
            if supplied is not None and supplied != symbol:
                raise IntakeError("Captured source symbol disagrees with its market events.")
        if any(event["message"].get("symbol", symbol) != symbol for event in events):
            raise IntakeError("Choose a capture containing only one underlying symbol.")
        warnings = [
            "Integrity verifies captured bytes, not authenticity or redistribution rights.",
            "Only calculation fields are retained; private labels and capture extensions are excluded.",
            "Source contract labels are replaced with stable opaque IDs; the capture hash and event number trace them to your original file.",
        ]
        if "contract_multiplier" not in inputs and symbol not in _MULTIPLIERS:
            raise IntakeError("Capture must declare a contract multiplier for this symbol.")
        effective = {
            "days_to_expiry": _number(inputs.get("days_to_expiry", .01), "fallback DTE", .000001, 30),
            "risk_free_rate": _number(inputs.get("risk_free_rate", .045), "risk-free rate", -.1, 1),
            "contract_multiplier": _number(inputs.get("contract_multiplier", _MULTIPLIERS.get(symbol)), "contract multiplier", 1e-12, 1e9),
            "expiry_filter": inputs.get("expiry_filter", "all"),
        }
        expiry_filter = effective["expiry_filter"]
        if not isinstance(expiry_filter, str) or not (
            expiry_filter in {"all", "0dte"} or re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry_filter)
        ):
            raise IntakeError("Captured expiry filter must be all, 0dte, or an ISO expiry date.")
        for name in effective:
            if name not in inputs:
                warnings.append(f"Capture omitted {name}; the displayed default is used.")
        versions = {int(event["message"].get("schema_version", 1)) for event in events if event["message"]["type"] == "options_volume_tick"}
        if len(versions) > 1:
            raise IntakeError("Mixed legacy and v2 option events cannot form one research checkpoint.")
        if versions == {1}:
            warnings.append("Legacy option events use strike aggregates, Black-Scholes, and fallback DTE where needed.")
        fallback_count = 0
        safe_messages, choices = [], []
        retained_bytes = 0
        latest = None
        first_time = None
        out_of_order = False
        sampled = set(range(len(events))) if len(events) <= MAX_CHECKPOINT_CHOICES else {
            index * (len(events) - 1) // (MAX_CHECKPOINT_CHOICES - 1) for index in range(MAX_CHECKPOINT_CHOICES)
        }
        for index, event in enumerate(events):
            message = event["message"]
            event_time = parse_market_datetime(message.get("event_time") or message.get("timestamp"))
            if event_time is None or event.get("time_source") == "received_time":
                raise IntakeError("Research checkpoints require genuine timezone-bearing message event times; receipt-time fallback is not accepted.")
            if parse_market_datetime(event.get("event_time")) != event_time:
                raise IntakeError("Capture envelope time disagrees with its market message.")
            first_time = first_time or event_time
            out_of_order = out_of_order or (latest is not None and event_time < latest)
            latest = max(latest, event_time) if latest is not None else event_time
            if message.get("iv_source") == "configured_default" or (message["type"] == "options_volume_tick" and message.get("iv") in (None, "")):
                fallback_count += 1
            encoded = json.dumps(_safe_message(message), sort_keys=True, separators=(",", ":"), allow_nan=False)
            retained_bytes += len(encoded.encode("utf-8"))
            if retained_bytes > MAX_CAPTURE_BYTES:
                raise IntakeError("Normalized calculation fields exceed the 4 MiB in-memory limit.")
            safe_messages.append(encoded)
            if index in sampled:
                choices.append({"sequence": index, "event_time": latest.isoformat().replace("+00:00", "Z"),
                                "as_of": latest.isoformat().replace("+00:00", "Z"), "event_type": message["type"]})
        if fallback_count:
            warnings.append(f"{fallback_count} option event(s) use fallback IV; inspect the checkpoint quality before interpreting it.")
        if out_of_order:
            warnings.append("Events arrive out of market-time order; each checkpoint cutoff is the latest included market time.")
        synthetic = source.get("synthetic") is True or source.get("source_kind") == "synthetic_fixture"
        mode = source.get("mode")
        mode = mode if isinstance(mode, str) and mode in _MODES else "unknown"
        provider = source.get("provider")
        provider = provider if isinstance(provider, str) and provider in _PROVIDERS else "unknown"
        if not synthetic:
            warnings.append("Historical capture replay does not certify a live provider or grant permission to share market data.")
        else:
            warnings.append("Synthetic classification is declared by the capture; integrity does not authenticate that claim.")
        if len(self._sessions) >= MAX_INTAKES:
            raise IntakeError("Four captures are already held in memory. Discard an intake before opening another.")
        intake_id = secrets.token_urlsafe(24)
        digest = footer["content_sha256"]
        self._sessions[intake_id] = _Session(tuple(safe_messages), symbol, dict(effective), synthetic, digest)
        return {"intake_id": intake_id, "content_sha256": digest, "symbol": symbol,
                "source_kind": "synthetic_fixture" if synthetic else "captured_session", "synthetic": synthetic,
                "source": {"provider": provider, "mode": mode}, "event_count": len(events),
                "first_event_time": first_time.isoformat().replace("+00:00", "Z"),
                "last_event_time": latest.isoformat().replace("+00:00", "Z"),
                "model_inputs": effective, "warnings": warnings, "event_time_fallback_count": 0,
                "quality": _recorded_quality(footer.get("feed_quality")),
                "checkpoints": choices, "default_sequence": len(events) - 1}

    async def checkpoint(self, intake_id: str, sequence: int) -> str:
        session = self._sessions.get(intake_id) if isinstance(intake_id, str) else None
        if session is None:
            raise IntakeError("This intake is unavailable. Inspect the local capture again.")
        if type(sequence) is not int or not 0 <= sequence < len(session.messages):
            raise IntakeError("Choose an event sequence within the verified capture.")
        inputs = session.model_inputs
        consumer = StatefulGexConsumer(
            IntradayGexEngine(inputs["contract_multiplier"]), target_underlying=session.symbol,
            risk_free_rate=inputs["risk_free_rate"], expiry_filter=inputs["expiry_filter"],
            data_mode="demo" if session.synthetic else "replay",
        )
        for index, message in enumerate(session.messages[:sequence + 1]):
            await consumer.update_market_state(message)
            if index % 100 == 0:
                await asyncio.sleep(0)
        if consumer.malformed_message_count:
            raise IntakeError("The selected prefix contains conflicting contract state. Choose a compatible capture.")
        try:
            artifact = await build_terminal_checkpoint(
                consumer, fallback_dte=inputs["days_to_expiry"],
                source_label=f"Local capture {session.content_sha256} · event {sequence + 1}",
            )
            return checkpoint_transport(artifact)
        except (ValueError, TypeError, OverflowError):
            raise IntakeError("This event cannot form a research checkpoint. Choose a later event with spot and active option quantity.") from None

    def discard(self, intake_id: str) -> None:
        if isinstance(intake_id, str):
            self._sessions.pop(intake_id, None)

    def clear(self) -> None:
        self._sessions.clear()

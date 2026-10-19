"""Prepare a bounded local capture for a paired, offline research workspace.

The private copy and frozen final checkpoint are derived from the same verified
bytes. Nothing in this module downloads market data or selects a live adapter.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sys

from .adapters.replay import ReplayAdapter
from .config import GexConfig
from .consumer import StatefulGexConsumer
from .contracts import parse_market_datetime
from .engine import IntradayGexEngine
from .session_capture import (
    LOCAL_CAPTURE_MAX_BYTES, LOCAL_CAPTURE_MAX_EVENTS, LOCAL_CAPTURE_MAX_LINE_BYTES,
    verify_captured_session_file,
)
from .wind_tunnel_checkpoint import build_terminal_checkpoint, write_checkpoint


MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_EVENTS = 5000
# The browser's small upload contract above is unchanged. Explicit local files
# use a streaming path and separate limits suitable for complete sessions.
MAX_LOCAL_CAPTURE_BYTES = LOCAL_CAPTURE_MAX_BYTES
MAX_LOCAL_CAPTURE_EVENTS = LOCAL_CAPTURE_MAX_EVENTS
MAX_LOCAL_CAPTURE_LINE_BYTES = LOCAL_CAPTURE_MAX_LINE_BYTES
MULTIPLIERS = {"ES": 50, "NQ": 20}


def restrict_network_to_loopback() -> None:
    """Block remote DNS and IP traffic in this process and its Python threads.

    Install in each child process before loading the application. Local browser
    services and Unix sockets remain available; no global machine setting changes.
    """
    def loopback(host) -> bool:
        if isinstance(host, bytes):
            try:
                host = host.decode("ascii")
            except UnicodeError:
                return False
        if not isinstance(host, str):
            return False
        if host.lower() in {"localhost", "localhost."}:
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def audit(event, arguments):
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
            host = arguments[0]
            # None requests local bind addresses, not remote name resolution.
            if host is not None and not loopback(host):
                raise PermissionError("Saved-data mode permits loopback networking only.")
        elif event == "socket.getnameinfo":
            if not loopback(arguments[0][0]):
                raise PermissionError("Saved-data mode permits loopback networking only.")
        elif event in {"socket.connect", "socket.sendto"}:
            connection = arguments[0]
            address = arguments[-1]
            if connection.family in {socket.AF_INET, socket.AF_INET6} and (
                not isinstance(address, tuple) or not address or not loopback(address[0])
            ):
                raise PermissionError("Saved-data mode permits loopback networking only.")

    sys.addaudithook(audit)


def _freeze_capture(capture: Path, frozen: Path, symbol: str) -> tuple[dict, dict, dict]:
    first_time = last_time = None
    has_underlying = False
    count = 0

    def inspect_event(event):
        nonlocal first_time, last_time, has_underlying, count
        message = event["message"]
        if message.get("symbol") != symbol:
            raise ValueError("Saved capture contains events for another or missing symbol.")
        event_time = parse_market_datetime(message.get("event_time") or message.get("timestamp"))
        if (event_time is None or event.get("time_source") == "received_time"
                or parse_market_datetime(event.get("event_time")) != event_time):
            raise ValueError("Saved capture requires matching authoritative message and envelope event times.")
        first_time = min(first_time, event_time) if first_time is not None else event_time
        last_time = max(last_time, event_time) if last_time is not None else event_time
        has_underlying = has_underlying or message["type"] == "underlying_tick"
        count += 1
        if count % 100_000 == 0:
            print(f"Verified {count:,} saved {symbol} events...", file=sys.stderr, flush=True)

    print(f"Verifying and freezing saved {symbol} data...", file=sys.stderr, flush=True)
    descriptor = os.open(frozen, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        header, footer, stats = verify_captured_session_file(
            capture, copy_to=stream, on_event=inspect_event,
            max_bytes=MAX_LOCAL_CAPTURE_BYTES, max_events=MAX_LOCAL_CAPTURE_EVENTS,
            max_line_bytes=MAX_LOCAL_CAPTURE_LINE_BYTES,
        )
        stream.flush()
        os.fsync(stream.fileno())
    if not count or not has_underlying:
        raise ValueError("Saved capture requires underlying market events.")
    stats.update(first_event_time=first_time.isoformat().replace("+00:00", "Z"),
                 last_event_time=last_time.isoformat().replace("+00:00", "Z"),
                 duration_seconds=(last_time - first_time).total_seconds())
    frozen.chmod(0o400)
    return header, footer, stats


def _assumptions(inputs: dict, symbol: str) -> tuple[dict, dict]:
    defaults = {"contract_multiplier": MULTIPLIERS[symbol], "risk_free_rate": .045,
                "days_to_expiry": .25}
    values, sources = {}, {}
    for name, default in defaults.items():
        value = inputs.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Captured {name} must be a finite number.")
        if name == "contract_multiplier":
            if type(value) is not int or not 1 <= value <= 10**9:
                raise ValueError("Captured contract_multiplier must be a positive integer no larger than 1000000000.")
        elif name == "risk_free_rate" and not -.1 <= value <= 1:
            raise ValueError("Captured risk_free_rate must be between -0.1 and 1.")
        elif name == "days_to_expiry" and not .000001 <= value <= 30:
            raise ValueError("Captured days_to_expiry must be between 0.000001 and 30.")
        values[name] = value
        sources[name] = "capture" if name in inputs else "default"
    supplied_filter = inputs.get("expiry_filter", "all")
    if not isinstance(supplied_filter, str):
        raise ValueError("Captured expiry_filter must be text.")
    if inputs.get("symbol", symbol) != symbol:
        raise ValueError("Captured model symbol does not match the selected symbol.")
    return values, {"sources": sources, "defaults_applied": [key for key in sources if sources[key] == "default"],
                    "captured_expiry_filter": supplied_filter, "effective_expiry_filter": "all"}


async def _checkpoint(config: GexConfig, content_hash: str) -> dict:
    consumer = StatefulGexConsumer(
        IntradayGexEngine(config.contract_multiplier), target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate, data_mode="replay", expiry_filter="all",
    )
    replay = ReplayAdapter(consumer, config.replay_path, delay_seconds=0, replay_clock="none")
    await replay.stream_market_data()
    if consumer.malformed_message_count:
        raise ValueError("Saved capture contains conflicting contract state.")
    return await build_terminal_checkpoint(
        consumer, fallback_dte=config.days_to_expiry,
        source_label=f"Saved {config.symbol} capture {content_hash[:16]} · final event",
    )


def prepare_saved_workspace(capture: Path, symbol: str, destination: Path) -> dict:
    """Freeze one verified ES/NQ capture and its final offline checkpoint.

    Missing numeric assumptions receive recorded defaults. An invalid supplied
    assumption is never replaced with a default. Destination must be new.
    """
    if symbol not in MULTIPLIERS:
        raise ValueError("Choose ES or NQ for the saved-data workspace.")
    destination = Path(destination).absolute()
    destination.mkdir(mode=0o700, exist_ok=False)
    try:
        frozen = destination / "capture.gex-session.jsonl"
        header, footer, stats = _freeze_capture(Path(capture), frozen, symbol)
        if header.get("normalized_contract") != "gex-terminal.normalized-message":
            raise ValueError("Saved capture declares an unsupported normalized message contract.")
        source, inputs = header.get("source"), header.get("model_inputs")
        if not isinstance(source, dict) or source.get("symbol") != symbol:
            raise ValueError("Saved capture source symbol does not match the selected symbol.")
        if not isinstance(inputs, dict):
            raise ValueError("Saved capture model_inputs must be an object.")
        values, assumptions = _assumptions(inputs, symbol)
        fast_load = stats["event_count"] > 5000 or stats["duration_seconds"] > 15 * 60
        clock = "none" if fast_load else "event"
        config = GexConfig(
            symbol=symbol, symbols=(symbol,), data_mode="replay", data_provider="replay",
            contract_multiplier=values["contract_multiplier"], risk_free_rate=values["risk_free_rate"],
            days_to_expiry=values["days_to_expiry"], refresh_interval_seconds=.5,
            stale_after_seconds=10, replay_path=str(frozen), replay_delay_seconds=0,
            tradovate_environment="demo", expiry_filter="all", replay_clock=clock, replay_speed=60,
        )
        capture_hash = stats["sha256"]
        print(f"Preparing final {symbol} checkpoint from {stats['event_count']:,} verified events...",
              file=sys.stderr, flush=True)
        checkpoint = asyncio.run(_checkpoint(config, capture_hash))
        checkpoint_path = destination / "checkpoint.json"
        write_checkpoint(checkpoint_path, checkpoint)
        return {
            "capture_path": str(frozen), "checkpoint_path": str(checkpoint_path), "symbol": symbol,
            "contract_multiplier": values["contract_multiplier"], "risk_free_rate": values["risk_free_rate"],
            "fallback_dte": values["days_to_expiry"], "capture_sha256": capture_hash,
            "capture_content_sha256": footer["content_sha256"], "assumptions": assumptions,
            "event_count": stats["event_count"], "capture_bytes": stats["bytes"],
            "first_event_time": stats["first_event_time"], "last_event_time": stats["last_event_time"],
            "duration_seconds": stats["duration_seconds"],
            "replay_policy": "fast_load" if fast_load else "event_time_60x",
            "terminal_args": ["--mode", "replay", "--captured-session", str(frozen), "--symbol", symbol,
                              "--multiplier", str(values["contract_multiplier"]), "--expiry-filter", "all",
                              "--replay-clock", clock, "--replay-speed", "60", "--refresh", "0.5"],
        }
    except BaseException:
        shutil.rmtree(destination)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("symbol", choices=tuple(MULTIPLIERS))
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    restrict_network_to_loopback()
    try:
        result = prepare_saved_workspace(args.capture, args.symbol, args.destination)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        print(f"Saved-data setup: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

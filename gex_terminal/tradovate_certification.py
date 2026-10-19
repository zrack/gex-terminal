"""Explicit, redacted certification probe for the Tradovate adapter."""

from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gex_terminal.adapters.tradovate import TradovateAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


CERTIFICATION_SCHEMA = "gex-terminal.tradovate-certification.v1"


async def build_tradovate_certification_report(
    *,
    symbol: str,
    environment: str,
    contract_multiplier: float,
    duration_seconds: float = 10.0,
    max_option_contracts: int = 12,
    ack_live_network: bool = False,
) -> dict[str, Any]:
    """Run a bounded read-only transport probe and return redacted evidence.

    The acknowledgement is deliberately mandatory because this operation uses
    credentialed external network access. The probe subscribes to market data;
    it never places, changes, or cancels orders.
    """
    if not ack_live_network:
        raise ValueError(
            "Tradovate certification requires --ack-live-network; the probe uses "
            "credentials and opens read-only external market-data connections"
        )
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)):
        raise ValueError("duration_seconds must be finite and positive")
    try:
        duration_seconds = float(duration_seconds)
    except (OverflowError, ValueError):
        raise ValueError("duration_seconds must be finite and positive") from None
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("duration_seconds must be finite and positive")

    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=contract_multiplier),
        target_underlying=symbol.upper(),
        data_mode="live",
    )
    adapter = TradovateAdapter(
        consumer,
        target_underlying=symbol,
        environment=environment,
        max_option_contracts=max_option_contracts,
        contract_multiplier=contract_multiplier,
        max_reconnect_attempts=0,
    )
    errors: list[str] = []
    authenticated = False
    task: asyncio.Task | None = None
    try:
        authenticated = await adapter.authenticate()
        if authenticated:
            task = asyncio.create_task(adapter.stream_market_data())
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=duration_seconds)
            except TimeoutError:
                # A provider task can raise TimeoutError itself. Only an
                # unfinished task represents our normal probe-window deadline.
                if task.done():
                    raise
    except Exception as exc:
        # Provider/library exception messages can contain unlabelled credentials
        # or payload fragments. Export a type and fixed reason, never their text.
        errors.append(f"{type(exc).__name__}: probe_failed")
    finally:
        # Read the run-window connection state before our own cancellation
        # disconnects a healthy socket. A stream that already failed/disconnected
        # must not pass merely because earlier subscriptions/messages existed.
        connection_state_at_probe_end = consumer.connection_state
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: cleanup_failed")
        # Failed background tasks can become visible only while cleanup awaits
        # them. Their final error/subscription counters still gate the result.
        quality = consumer.feed_quality_snapshot()
    unique_contract_ids = {
        str(metadata.get("contract_id"))
        for metadata in adapter.contract_metadata.values()
        if metadata.get("contract_id") not in (None, "")
        and metadata.get("instrument_class") != "future"
    }
    normalized_option_contracts = len({key[:2] for key in consumer.contract_state})
    transport_certified = bool(
        authenticated
        and adapter._connected_once
        and connection_state_at_probe_end == "CONNECTED"
        and not errors
        and quality.get("entitlement_error_count", 0) == 0
        and quality.get("subscription_status") == "subscribed"
        and quality.get("frame_count", 0) > 0
        and consumer.message_count > 0
    )
    # These acceptance counters have no public feed-quality projection. Reuse
    # the consumer's checkpoint/pricing eligibility evidence without changing
    # serialized feed-quality receipts solely for this provider probe.
    legacy_option_tick_count = consumer._v1_option_count
    untimed_market_event_count = consumer._untimed_market_event_count
    quantitative_gex_certified = bool(
        transport_certified
        and consumer.current_spot > 0
        and consumer.contract_state
        and legacy_option_tick_count == 0
        and untimed_market_event_count == 0
        and adapter._iv_fallback_count == 0
        and adapter._receipt_time_fallback_count == 0
        and quality.get("parse_error_count", 0) == 0
        and quality.get("dropped_count", 0) == 0
        and quality.get("malformed_count", 0) == 0
    )

    return {
        "schema": CERTIFICATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe": {
            "read_only": True,
            "orders_touched": False,
            "duration_seconds": float(duration_seconds),
            "max_option_contracts": int(max_option_contracts),
        },
        "target": {
            "environment": adapter.environment,
            "symbol": adapter.target_underlying,
        },
        "authentication": {
            "passed": authenticated,
            "failure_reason": _safe_auth_failure_reason(adapter.auth_failure_reason),
            "has_live": adapter.auth_capabilities.get("has_live"),
            "has_market_data": adapter.auth_capabilities.get("has_market_data"),
            "market_data_token_present": bool(adapter.md_access_token),
        },
        "transport": {
            "websocket_authorized": adapter._connected_once,
            "connection_state_at_probe_end": connection_state_at_probe_end,
            "subscription_status": quality.get("subscription_status"),
            "subscribed_symbols": quality.get("subscribed_symbol_count", 0),
            "provider_frames": quality.get("frame_count", 0),
            "normalized_messages": consumer.message_count,
            "normalized_option_contracts": normalized_option_contracts,
            "discovered_option_contracts": len(unique_contract_ids),
            "entitlement_errors": quality.get("entitlement_error_count", 0),
            "parse_errors": quality.get("parse_error_count", 0),
            "dropped_messages": quality.get("dropped_count", 0),
        },
        "model_inputs": {
            "native_implied_volatility_observed": bool(
                consumer.contract_state and adapter._iv_fallback_count == 0
            ),
            "fallback_iv_tick_count": adapter._iv_fallback_count,
            "receipt_time_fallback_tick_count": adapter._receipt_time_fallback_count,
            "legacy_option_tick_count": legacy_option_tick_count,
            "untimed_market_event_count": untimed_market_event_count,
        },
        "result": {
            "transport_certified": transport_certified,
            "quantitative_gex_certified": quantitative_gex_certified,
            "adapter_registry_status": "scaffold",
        },
        "evidence_ceiling": {
            "transport": "measured only for this credential, environment, and run window",
            "model": (
                "requires accepted underlying and schema-v2 option messages with event "
                "clocks, no legacy option ticks, no configured-IV or receipt-time "
                "fallbacks, and no recorded parse/drop errors; "
                "transport alone does not establish option-payload coverage"
            ),
            "predictive_market_validity": "unmeasured",
        },
        "errors": errors,
    }


def write_tradovate_certification_report(
    report: dict[str, Any], output_path: str | Path
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".json":
        content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    elif target.suffix.lower() in {".md", ".markdown"}:
        content = _format_markdown(report)
    else:
        raise ValueError("Tradovate certification output must end in .json or .md")
    target.write_text(content, encoding="utf-8")
    return target


def _format_markdown(report: dict[str, Any]) -> str:
    authentication = report["authentication"]
    transport = report["transport"]
    model_inputs = report["model_inputs"]
    result = report["result"]
    lines = [
        "# Tradovate Certification",
        "",
        f"Generated: {report['generated_at']}",
        f"Environment: {report['target']['environment']}",
        f"Symbol: {report['target']['symbol']}",
        "",
        "## Result",
        "",
        f"- Transport certified: **{str(result['transport_certified']).lower()}**",
        f"- Quantitative GEX certified: **{str(result['quantitative_gex_certified']).lower()}**",
        f"- Adapter registry status: `{result['adapter_registry_status']}`",
        "",
        "## Evidence",
        "",
        f"- Authentication passed: {authentication['passed']}",
        f"- Authentication failure reason: {authentication['failure_reason']}",
        f"- Market-data entitlement reported: {authentication['has_market_data']}",
        f"- WebSocket authorized: {transport['websocket_authorized']}",
        f"- Connection state at probe end: {transport.get('connection_state_at_probe_end', 'unreported')}",
        f"- Subscription status: {transport['subscription_status']}",
        f"- Subscribed symbols: {transport['subscribed_symbols']}",
        f"- Provider frames: {transport['provider_frames']}",
        f"- Normalized messages: {transport['normalized_messages']}",
        f"- Normalized option contracts: {transport['normalized_option_contracts']}",
        f"- Native implied volatility observed: {model_inputs['native_implied_volatility_observed']}",
        f"- Fallback-IV ticks: {model_inputs['fallback_iv_tick_count']}",
        f"- Receipt-time fallback ticks: {model_inputs.get('receipt_time_fallback_tick_count', 'unreported')}",
        f"- Legacy option ticks: {model_inputs.get('legacy_option_tick_count', 'unreported')}",
        f"- Untimed market events: {model_inputs.get('untimed_market_event_count', 'unreported')}",
        "",
        "## Evidence ceiling",
        "",
        f"- Transport: {report['evidence_ceiling']['transport']}",
        f"- Model: {report['evidence_ceiling']['model']}",
        f"- Predictive market validity: {report['evidence_ceiling']['predictive_market_validity']}",
    ]
    if report["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {error}" for error in report["errors"])
    return "\n".join(lines) + "\n"


def _safe_auth_failure_reason(reason: str | None) -> str | None:
    """Retain adapter reason enums without exporting arbitrary provider text."""
    if reason is None or reason in {"challenge_required", "no_access_token"}:
        return reason
    if isinstance(reason, str) and re.fullmatch(r"http_[1-5][0-9]{2}", reason):
        return reason
    return "authentication_failed"

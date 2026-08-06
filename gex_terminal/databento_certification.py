"""Explicit, redacted certification probe for Databento live ingestion."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gex_terminal.adapters.databento import ADAPTER_INFO, DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


CERTIFICATION_SCHEMA = "gex-terminal.databento-certification.v1"


async def build_databento_certification_report(
    *,
    symbol: str,
    contract_multiplier: float,
    risk_free_rate: float,
    duration_seconds: float = 10.0,
    ack_live_network: bool = False,
) -> dict[str, Any]:
    """Run a bounded read-only Databento live-data probe."""
    if not ack_live_network:
        raise ValueError(
            "Databento certification requires --ack-live-network; the probe uses "
            "credentials and opens read-only external market-data subscriptions"
        )
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")

    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=contract_multiplier),
        target_underlying=symbol.upper(),
        data_mode="live",
    )
    adapter = DatabentoAdapter(
        consumer,
        target_underlying=symbol,
        risk_free_rate=risk_free_rate,
    )
    errors: list[str] = []
    task: asyncio.Task | None = None
    try:
        task = asyncio.create_task(adapter.stream_market_data())
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=duration_seconds)
        except TimeoutError:
            pass
    except Exception as exc:
        errors.append(_redacted_error(exc, adapter.api_key))
    finally:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        elif task and task.done():
            try:
                task.result()
            except Exception as exc:
                errors.append(_redacted_error(exc, adapter.api_key))

    quality = consumer.feed_quality_snapshot()
    iv_sources = {
        str(state.get("iv_source") or "unknown")
        for state in consumer.contract_state.values()
    }
    transport_certified = bool(
        adapter._connected_once
        and quality.get("subscription_status") == "subscribed"
        and quality.get("frame_count", 0) > 0
    )
    chain_ingestion_certified = bool(
        transport_certified
        and adapter._definition_count > 0
        and adapter._underlying_quote_count > 0
        and adapter._option_trade_count > 0
        and consumer.contract_state
    )
    quantitative_gex_input_certified = bool(
        chain_ingestion_certified
        and adapter._inverted_iv_count > 0
        and adapter._iv_fallback_count == 0
        and iv_sources == {"black_76_inverted"}
    )

    return {
        "schema": CERTIFICATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe": {
            "read_only": True,
            "orders_touched": False,
            "duration_seconds": float(duration_seconds),
        },
        "target": {
            "dataset": adapter.dataset,
            "symbol": adapter.target_underlying,
            "option_parent": f"{adapter.target_underlying}.OPT",
            "underlying_continuous": f"{adapter.target_underlying}.v.0",
        },
        "authentication": {
            "api_key_present": bool(adapter.api_key),
            "sdk_version": adapter._sdk_version,
            "challenge_response_session_started": adapter._connected_once,
        },
        "transport": {
            "subscription_status": quality.get("subscription_status"),
            "subscription_ids_observed": len(adapter.subscription_ids),
            "provider_frames": quality.get("frame_count", 0),
            "parse_errors": quality.get("parse_error_count", 0),
            "dropped_messages": quality.get("dropped_count", 0),
            "entitlement_errors": quality.get("entitlement_error_count", 0),
        },
        "chain": {
            "definitions_observed": adapter._definition_count,
            "underlying_quotes_observed": adapter._underlying_quote_count,
            "option_trades_observed": adapter._option_trade_count,
            "normalized_option_states": len(consumer.contract_state),
            "trades_before_definition": adapter._dropped_before_definition_count,
            "trades_before_underlying": adapter._dropped_before_underlying_count,
            "underlying_contract_mismatches": adapter._dropped_underlying_mismatch_count,
        },
        "model_inputs": {
            "iv_sources_observed": sorted(iv_sources),
            "black_76_inverted_ticks": adapter._inverted_iv_count,
            "fallback_iv_ticks": adapter._iv_fallback_count,
            "risk_free_rate": float(risk_free_rate),
            "pricing_model": "black_76",
        },
        "result": {
            "transport_certified": transport_certified,
            "chain_ingestion_certified": chain_ingestion_certified,
            "quantitative_gex_input_certified": quantitative_gex_input_certified,
            "adapter_registry_status": ADAPTER_INFO.status,
        },
        "evidence_ceiling": {
            "transport": "measured only for this credential, dataset, symbol, and run window",
            "iv": "trade-price inversion against the latest observed futures midpoint; not a synchronized executable option quote",
            "positioning": "trade volume and aggressor side do not reveal dealer inventory",
            "predictive_market_validity": "unmeasured",
        },
        "errors": list(dict.fromkeys(errors)),
    }


def write_databento_certification_report(
    report: dict[str, Any], output_path: str | Path
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".json":
        content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    elif target.suffix.lower() in {".md", ".markdown"}:
        content = _format_markdown(report)
    else:
        raise ValueError("Databento certification output must end in .json or .md")
    target.write_text(content, encoding="utf-8")
    return target


def _format_markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    transport = report["transport"]
    chain = report["chain"]
    model = report["model_inputs"]
    lines = [
        "# Databento Certification",
        "",
        f"Generated: {report['generated_at']}",
        f"Dataset: {report['target']['dataset']}",
        f"Symbol: {report['target']['symbol']}",
        "",
        "## Result",
        "",
        f"- Transport certified: **{str(result['transport_certified']).lower()}**",
        f"- Chain ingestion certified: **{str(result['chain_ingestion_certified']).lower()}**",
        f"- Quantitative GEX input certified: **{str(result['quantitative_gex_input_certified']).lower()}**",
        f"- Adapter registry status: `{result['adapter_registry_status']}`",
        "",
        "## Evidence",
        "",
        f"- Subscription status: {transport['subscription_status']}",
        f"- Provider frames: {transport['provider_frames']}",
        f"- Definitions observed: {chain['definitions_observed']}",
        f"- Underlying quotes observed: {chain['underlying_quotes_observed']}",
        f"- Option trades observed: {chain['option_trades_observed']}",
        f"- Black-76 inverted ticks: {model['black_76_inverted_ticks']}",
        f"- Fallback-IV ticks: {model['fallback_iv_ticks']}",
        "",
        "## Evidence ceiling",
        "",
        f"- Transport: {report['evidence_ceiling']['transport']}",
        f"- IV: {report['evidence_ceiling']['iv']}",
        f"- Positioning: {report['evidence_ceiling']['positioning']}",
        f"- Predictive market validity: {report['evidence_ceiling']['predictive_market_validity']}",
    ]
    if report["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {error}" for error in report["errors"])
    return "\n".join(lines) + "\n"


def _redacted_error(exc: Exception, api_key: str | None) -> str:
    message = str(exc)
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return f"{type(exc).__name__}: {message[:500]}"

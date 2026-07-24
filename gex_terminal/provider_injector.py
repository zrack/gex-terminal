"""Offline raw-provider fixture injection for adapter-path trust tests."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.adapters.tradovate import TradovateAdapter
from gex_terminal.adapters.yfinance_adapter import YfinanceAdapter
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import dumps_normalized_message
from gex_terminal.snapshot import build_snapshot


INJECTION_FORMATS = (
    "auto",
    "tradovate",
    "databento",
    "yfinance",
    "cboe-option-quotes",
)


async def inject_provider_fixture(
    *,
    provider: str,
    fixture_path: str | Path,
    config: GexConfig,
    fixture_format: str = "auto",
    metadata_path: str | Path | None = None,
    underlying_path: str | Path | None = None,
) -> dict[str, Any]:
    """Inject a raw provider fixture through the same consumer/engine path as live data."""
    fixture = Path(fixture_path)
    if not fixture.exists():
        raise FileNotFoundError(f"Provider fixture not found: {fixture}")

    resolved_format = _resolve_fixture_format(provider, fixture, fixture_format)
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode="live",
        stale_after_seconds=config.stale_after_seconds,
    )
    consumer.mark_connected()

    if resolved_format == "tradovate":
        await _inject_tradovate(consumer, config, fixture, metadata_path)
    elif resolved_format == "databento":
        await _inject_databento(consumer, config, fixture, metadata_path, underlying_path)
    elif resolved_format == "yfinance":
        await _inject_yfinance(consumer, fixture)
    elif resolved_format == "cboe-option-quotes":
        await _inject_cboe_option_quotes(consumer, fixture)
    else:
        raise ValueError(f"Unsupported provider fixture format: {resolved_format}")

    data = await consumer.process_latest_snapshot(days_to_expiry=config.days_to_expiry)
    if "error" in data:
        raise ValueError(f"Injected fixture did not produce a computable snapshot: {data['error']}")

    breakdown = await consumer.process_expiry_breakdown(days_to_expiry=config.days_to_expiry)
    snapshot = build_snapshot(
        symbol=consumer.target_underlying,
        spot=consumer.current_spot,
        session_open=consumer.session_open,
        days_to_expiry=config.days_to_expiry,
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        data=data,
        chain_state=consumer.chain_state,
        expiry_breakdown=breakdown,
    )
    snapshot["provider_injection"] = {
        "provider": provider,
        "fixture_format": resolved_format,
        "fixture": str(fixture),
        "metadata": str(metadata_path) if metadata_path else None,
        "underlying_fixture": str(underlying_path) if underlying_path else None,
        "normalized_messages": consumer.message_count,
    }
    snapshot["feed_quality"] = consumer.feed_quality_snapshot()
    return snapshot


def provider_injection_summary(snapshot: Mapping[str, Any]) -> str:
    """Render a compact operator summary for CLI fixture injection."""
    injection = snapshot.get("provider_injection", {})
    quality = snapshot.get("feed_quality", {})
    metrics = snapshot.get("metrics", {})
    return "\n".join((
        f"Injected {injection.get('fixture_format', 'provider')} fixture: {injection.get('fixture')}",
        f"Symbol: {snapshot.get('symbol')}  Spot: {float(snapshot.get('spot', 0.0)):,.2f}",
        (
            f"Gamma wall: {float(metrics.get('gamma_wall', 0.0)):,.2f}  "
            f"Zero gamma: {float(metrics.get('zero_gamma', 0.0)):,.2f}"
        ),
        (
            f"Messages: {injection.get('normalized_messages', 0)}  "
            f"Frames: {quality.get('frame_count', 0)}  "
            f"Parse errors: {quality.get('parse_error_count', 0)}  "
            f"Dropped: {quality.get('dropped_count', 0)}"
        ),
        (
            f"Subscription: {quality.get('subscription_status', 'unknown')}  "
            f"Subscribed symbols: {quality.get('subscribed_symbol_count', 0)}  "
            f"Health: {quality.get('health', 'unknown')}"
        ),
    ))


async def _inject_tradovate(
    consumer: StatefulGexConsumer,
    config: GexConfig,
    fixture: Path,
    metadata_path: str | Path | None,
) -> None:
    adapter = TradovateAdapter(
        consumer=consumer,
        target_underlying=config.symbol,
        environment=config.tradovate_environment,
    )
    if metadata_path:
        adapter.contract_metadata = _tradovate_contract_metadata(Path(metadata_path))

    frames = list(_tradovate_frames(fixture))
    consumer.mark_subscribed(
        len(adapter.contract_metadata) or _count_tradovate_quote_symbols(frames)
    )
    for frame in frames:
        await adapter._parse_and_route(frame)


async def _inject_databento(
    consumer: StatefulGexConsumer,
    config: GexConfig,
    fixture: Path,
    metadata_path: str | Path | None,
    underlying_path: str | Path | None,
) -> None:
    if not metadata_path:
        raise ValueError("Databento injection requires --metadata with definition records.")

    adapter = DatabentoAdapter(consumer=consumer, target_underlying=config.symbol)
    metadata_by_id = _databento_metadata_by_id(Path(metadata_path))
    consumer.mark_subscribed(len(metadata_by_id))

    if underlying_path:
        for record in _json_records(Path(underlying_path)):
            consumer.record_provider_frame()
            message = adapter._normalize_underlying_quote(record)
            await _emit_normalized(consumer, message)

    for record in _json_records(fixture):
        consumer.record_provider_frame()
        message = DatabentoAdapter._normalize_option_trade_record(record, metadata_by_id)
        if not await _emit_normalized(consumer, message):
            consumer.record_dropped_message()


async def _inject_yfinance(consumer: StatefulGexConsumer, fixture: Path) -> None:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    expiry = str(payload.get("expiry") or "")
    quote = payload.get("quote", {})
    price = _first_float(
        quote,
        "last_price",
        "lastPrice",
        "regular_market_price",
        "regularMarketPrice",
        "close",
    )
    if price is None:
        price = _first_float(payload, "underlying_price", "underlyingPrice", "price")
    await _emit_normalized(consumer, {
        "type": "underlying_tick",
        "symbol": str(payload.get("symbol") or consumer.target_underlying).upper(),
        "price": price,
    })

    adapter = YfinanceAdapter(consumer=consumer, target_underlying=consumer.target_underlying)
    rows = [
        *adapter._normalized_option_rows(payload.get("calls", ()), "C", expiry),
        *adapter._normalized_option_rows(payload.get("puts", ()), "P", expiry),
    ]
    consumer.mark_subscribed(len(rows))
    consumer.record_provider_frame()
    for row in rows:
        await _emit_normalized(consumer, row)


async def _inject_cboe_option_quotes(consumer: StatefulGexConsumer, fixture: Path) -> None:
    rows = list(_csv_dicts(fixture))
    option_rows = 0
    for row in rows:
        consumer.record_provider_frame()
        symbol = _csv_value(row, "underlying_symbol", "Underlying Symbol", "symbol")
        symbol = (symbol or consumer.target_underlying).upper()
        price = _csv_float(
            row,
            "active_underlying_price",
            "underlying_price",
            "Underlying Price",
        )
        if price is None:
            bid = _csv_float(row, "underlying_bid", "Underlying Bid")
            ask = _csv_float(row, "underlying_ask", "Underlying Ask")
            if bid is not None and ask is not None:
                price = (bid + ask) / 2
        if price is not None:
            await _emit_normalized(consumer, {
                "type": "underlying_tick",
                "symbol": symbol,
                "price": price,
            })

        volume = _csv_int(row, "trade_volume", "Trade Volume", "volume", "open_interest")
        message = {
            "type": "options_volume_tick",
            "strike": _csv_float(row, "strike", "Strike"),
            "option_type": _csv_value(row, "option_type", "Option Type", "call_put"),
            "volume": volume,
            "iv": _csv_float(row, "implied_volatility", "Implied Volatility", "iv") or 0.20,
            "expiry": _csv_value(row, "expiration", "Expiration", "expiry"),
        }
        if await _emit_normalized(consumer, message):
            option_rows += 1
        else:
            consumer.record_dropped_message()

    consumer.mark_subscribed(option_rows)


async def _emit_normalized(consumer: StatefulGexConsumer, message: Mapping[str, Any] | None) -> bool:
    if not message:
        return False
    try:
        await consumer.update_market_state(dumps_normalized_message(dict(message)))
    except (TypeError, ValueError):
        consumer.record_provider_parse_error()
        return False
    return True


def _resolve_fixture_format(provider: str, fixture: Path, fixture_format: str) -> str:
    requested = fixture_format.lower()
    if requested != "auto":
        if requested not in INJECTION_FORMATS:
            raise ValueError(
                f"Unsupported fixture format '{fixture_format}'. Expected one of: "
                f"{', '.join(INJECTION_FORMATS)}"
            )
        return requested

    provider = provider.lower()
    if fixture.suffix.lower() == ".csv":
        return "cboe-option-quotes"
    if provider in {"tradovate", "databento", "yfinance"}:
        return provider
    raise ValueError(
        "Could not infer provider fixture format. Pass --fixture-format explicitly."
    )


def _tradovate_contract_metadata(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = {}
    for contract in TradovateAdapter._extract_contract_list(payload):
        if not TradovateAdapter._looks_like_option_contract(contract):
            continue
        symbol = TradovateAdapter._contract_symbol(contract)
        if symbol:
            metadata[symbol] = TradovateAdapter._option_metadata(contract)
    return metadata


def _tradovate_frames(path: Path) -> Iterable[str]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ()
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        return (f"a{json.dumps(payload)}",)

    frames = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped[0] in {"a", "m"}:
            frames.append(stripped)
        else:
            json.loads(stripped)
            frames.append(f"a{stripped}")
    return tuple(frames)


def _count_tradovate_quote_symbols(frames: Iterable[str]) -> int:
    symbols = set()
    for frame in frames:
        if not frame or frame[0] not in {"a", "m"}:
            continue
        try:
            payloads = json.loads(frame[1:])
        except json.JSONDecodeError:
            continue
        for event in payloads if isinstance(payloads, list) else ():
            quotes = event.get("d", {}).get("quotes", ()) if isinstance(event, dict) else ()
            for quote in quotes:
                if isinstance(quote, dict) and quote.get("symbol"):
                    symbols.add(str(quote["symbol"]))
    return len(symbols)


def _databento_metadata_by_id(path: Path) -> dict[int, dict[str, Any]]:
    metadata_by_id = {}
    for record in _json_records(path):
        metadata = DatabentoAdapter._normalize_definition_record(record)
        if not metadata:
            continue
        instrument_id = metadata.get("instrument_id")
        if instrument_id is not None:
            metadata_by_id[int(instrument_id)] = metadata
    return metadata_by_id


def _json_records(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, dict):
        if isinstance(payload.get("records"), list):
            return [item for item in payload["records"] if isinstance(item, Mapping)]
        if isinstance(payload.get("record"), Mapping):
            return [payload["record"]]
        return [payload]
    return []


def _csv_dicts(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        yield from csv.DictReader(csv_file)


def _csv_value(row: Mapping[str, Any], *fields: str) -> str | None:
    normalized = {_normalize_field_name(key): value for key, value in row.items()}
    for field in fields:
        value = normalized.get(_normalize_field_name(field))
        if value not in (None, ""):
            return str(value).strip()
    return None


def _csv_float(row: Mapping[str, Any], *fields: str) -> float | None:
    return _safe_float(_csv_value(row, *fields))


def _csv_int(row: Mapping[str, Any], *fields: str) -> int | None:
    value = _safe_float(_csv_value(row, *fields))
    if value is None:
        return None
    return int(value)


def _first_float(mapping: Mapping[str, Any], *fields: str) -> float | None:
    for field in fields:
        value = mapping.get(field)
        result = _safe_float(value)
        if result is not None:
            return result
    return None


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())

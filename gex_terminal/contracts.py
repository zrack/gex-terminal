"""Versioned option-contract metadata and market-time helpers.

Schema v1 is the historical, strike-level replay contract. Schema v2 adds the
identity and timing needed to keep same-strike contracts from different
expirations separate. The v2 path is additive: callers that omit
``schema_version`` continue to use the original Black-Scholes calculation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping


NORMALIZED_SCHEMA_VERSION = 2
INSTRUMENT_CLASSES = {"equity_option", "futures_option", "index_option"}
PRICING_MODELS = {"black_scholes", "black_76"}
VOLUME_SEMANTICS = {"incremental", "cumulative"}
POSITION_SOURCES = {"trade_volume", "open_interest"}
IV_SOURCES = {"provider", "configured_default"}

FUTURES_OPTION_ROOTS = {"ES", "MES", "NQ", "MNQ"}
INDEX_OPTION_ROOTS = {"SPX"}


def infer_instrument_class(symbol: str) -> str:
    """Return the default option class for a supported root symbol."""
    root = symbol.strip().upper()
    if root in FUTURES_OPTION_ROOTS:
        return "futures_option"
    if root in INDEX_OPTION_ROOTS:
        return "index_option"
    return "equity_option"


def pricing_model_for_instrument(instrument_class: str) -> str:
    """Map an instrument class to the project's documented gamma model."""
    if instrument_class == "futures_option":
        return "black_76"
    return "black_scholes"


def canonical_option_contract(
    message: Mapping[str, Any],
    *,
    target_underlying: str,
) -> dict[str, Any]:
    """Return stable contract metadata for a validated normalized message."""
    schema_version = int(message.get("schema_version", 1))
    symbol = str(message.get("symbol") or target_underlying).upper()
    option_type = str(message["option_type"]).upper()[0]
    strike = float(message["strike"])
    expiry = str(message.get("expiry") or "session")
    provider = str(message.get("provider") or "legacy").lower()
    contract_id = str(
        message.get("contract_id")
        or f"{symbol}|{expiry}|{option_type}|{strike:g}"
    )
    position_source = str(
        message.get("position_source") or "trade_volume"
    ).lower()

    if schema_version >= NORMALIZED_SCHEMA_VERSION:
        instrument_class = str(
            message.get("instrument_class") or infer_instrument_class(symbol)
        ).lower()
        pricing_model = pricing_model_for_instrument(instrument_class)
    else:
        instrument_class = "legacy_option"
        pricing_model = "black_scholes"

    return {
        "schema_version": schema_version,
        "provider": provider,
        "contract_id": contract_id,
        "contract_symbol": message.get("contract_symbol"),
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "expiry": expiry,
        "expiry_timestamp": message.get("expiry_timestamp"),
        "days_to_expiry": _optional_positive_float(message.get("days_to_expiry")),
        "instrument_class": instrument_class,
        "pricing_model": pricing_model,
        "volume_semantics": str(
            message.get("volume_semantics") or "incremental"
        ).lower(),
        "position_source": position_source,
        "contract_multiplier": _optional_positive_float(
            message.get("contract_multiplier")
        ),
        "iv_source": (
            str(message["iv_source"]).lower()
            if message.get("iv_source") not in (None, "")
            else None
        ),
        "event_time": message.get("event_time") or message.get("timestamp"),
        "received_time": message.get("received_time"),
        "sequence": _optional_int(message.get("sequence")),
    }


def contract_storage_key(contract: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return a provider-scoped mutable position key."""
    return (
        str(contract.get("provider") or "legacy"),
        str(contract["contract_id"]),
        str(contract.get("position_source") or "trade_volume"),
    )


def parse_market_datetime(value: Any) -> datetime | None:
    """Parse an RFC3339/ISO-8601 timestamp with an explicit timezone."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def expiry_datetime(value: Any) -> datetime | None:
    """Parse only an authoritative timezone-bearing expiry instant."""
    return parse_market_datetime(value)


def expiry_date(value: Any) -> date | None:
    """Return the calendar date from an expiry label or timestamp."""
    if value in (None, "", "session"):
        return None
    if str(value).upper() == "0DTE":
        return None
    timestamp = parse_market_datetime(value)
    if timestamp is not None:
        return timestamp.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def days_until_expiry(expiry_value: Any, as_of: datetime) -> float | None:
    """Return fractional days to an authoritative expiry instant.

    Date-only labels intentionally return ``None``. Without an exchange-specific
    settlement time, the configured DTE remains the honest fallback.
    """
    expiry = expiry_datetime(expiry_value)
    if expiry is None:
        return None
    reference = _as_utc(as_of)
    return (expiry - reference).total_seconds() / 86_400.0


def is_zero_dte(expiry_value: Any, as_of: datetime) -> bool:
    """Return whether an expiry label/timestamp is on the reference UTC date."""
    if str(expiry_value).upper() == "0DTE":
        return True
    resolved = expiry_date(expiry_value)
    return resolved == _as_utc(as_of).date() if resolved is not None else False


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    return value.astimezone(timezone.utc)


def _optional_positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    return number if number > 0 else None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)

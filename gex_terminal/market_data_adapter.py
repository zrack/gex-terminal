import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from gex_terminal.contracts import (
    AGGRESSOR_SIDES,
    DIRECTION_SOURCES,
    INSTRUMENT_CLASSES,
    IV_SOURCES,
    NORMALIZED_SCHEMA_VERSION,
    POSITION_SOURCES,
    PRICING_MODELS,
    VOLUME_SEMANTICS,
    expiry_date,
    pricing_model_for_instrument,
    parse_market_datetime,
)


NormalizedMessage = dict[str, Any]

OPTION_TYPES = {"C", "P"}


class MarketDataAdapter(ABC):
    """Common async contract for live and replay market-data adapters."""

    @abstractmethod
    async def stream_market_data(self) -> None:
        """Stream normalized market-data messages into a consumer."""


class AdapterConfigurationError(RuntimeError):
    """Raised when a selected adapter cannot start with the current setup."""


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    label: str
    status: str
    notes: str


def validate_normalized_message(message: NormalizedMessage) -> None:
    schema_version = _schema_version(message)
    message_type = message.get("type")

    if message_type == "underlying_tick":
        _require_fields(message, ("symbol", "price"))
        _require_positive_number(message, "price")
        if schema_version >= NORMALIZED_SCHEMA_VERSION:
            _require_fields(message, ("provider", "event_time"))
            _require_aware_timestamp(message, "event_time")
            if message.get("received_time") not in (None, ""):
                _require_aware_timestamp(message, "received_time")
        return

    if message_type == "options_volume_tick":
        _require_fields(message, ("strike", "option_type", "volume"))
        _require_positive_number(message, "strike")
        option_type = str(message["option_type"]).upper()
        if option_type not in OPTION_TYPES:
            raise ValueError(f"Unsupported option_type: {message['option_type']}")
        if "iv" in message and message["iv"] not in (None, ""):
            _require_positive_number(message, "iv")
        if "days_to_expiry" in message and message["days_to_expiry"] not in (None, ""):
            _require_positive_number(message, "days_to_expiry")
        if "open_interest" in message and message["open_interest"] not in (None, ""):
            _require_non_negative_int(message, "open_interest")
        if "sequence" in message and message["sequence"] not in (None, ""):
            _require_non_negative_int(message, "sequence")

        if schema_version >= NORMALIZED_SCHEMA_VERSION:
            _validate_v2_option_contract(message)
        else:
            _require_positive_int(message, "volume")
        return

    raise ValueError(f"Unsupported normalized message type: {message_type}")


def dumps_normalized_message(message: NormalizedMessage) -> str:
    validate_normalized_message(message)
    return json.dumps(message)


def _require_fields(message: NormalizedMessage, fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if message.get(field) in (None, "")]
    if missing:
        raise ValueError(
            f"Missing required field(s) for {message.get('type')}: {', '.join(missing)}"
        )


def _require_positive_number(message: NormalizedMessage, field: str) -> None:
    try:
        value = float(message[field])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_positive_int(message: NormalizedMessage, field: str) -> None:
    try:
        value = int(message[field])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if isinstance(message[field], float) and not message[field].is_integer():
        raise ValueError(f"{field} must be an integer")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_non_negative_int(message: NormalizedMessage, field: str) -> None:
    try:
        value = int(message[field])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if isinstance(message[field], float) and not message[field].is_integer():
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")


def _schema_version(message: NormalizedMessage) -> int:
    try:
        version = int(message.get("schema_version", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("schema_version must be an integer") from exc
    if version < 1 or version > NORMALIZED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported normalized schema_version: {version}; "
            f"latest is {NORMALIZED_SCHEMA_VERSION}"
        )
    return version


def _validate_v2_option_contract(message: NormalizedMessage) -> None:
    _require_fields(
        message,
        (
            "provider",
            "contract_id",
            "symbol",
            "expiry",
            "instrument_class",
            "volume_semantics",
            "position_source",
            "iv",
            "iv_source",
            "event_time",
        ),
    )

    instrument_class = str(message["instrument_class"]).lower()
    if instrument_class not in INSTRUMENT_CLASSES:
        raise ValueError(f"Unsupported instrument_class: {message['instrument_class']}")

    volume_semantics = str(message["volume_semantics"]).lower()
    if volume_semantics not in VOLUME_SEMANTICS:
        raise ValueError(f"Unsupported volume_semantics: {message['volume_semantics']}")
    if volume_semantics == "incremental":
        _require_positive_int(message, "volume")
    else:
        _require_non_negative_int(message, "volume")

    position_source = str(message.get("position_source") or "trade_volume").lower()
    if position_source not in POSITION_SOURCES:
        raise ValueError(f"Unsupported position_source: {message['position_source']}")

    aggressor_side = str(message.get("aggressor_side") or "unknown").lower()
    direction_source = str(message.get("direction_source") or "unknown").lower()
    if aggressor_side not in AGGRESSOR_SIDES:
        raise ValueError(f"Unsupported aggressor_side: {message['aggressor_side']}")
    if direction_source not in DIRECTION_SOURCES:
        raise ValueError(f"Unsupported direction_source: {message['direction_source']}")
    if aggressor_side != "unknown":
        if position_source != "trade_volume":
            raise ValueError("aggressor_side requires position_source=trade_volume")
        if volume_semantics != "incremental":
            raise ValueError("aggressor_side requires incremental volume semantics")
        if direction_source == "unknown":
            raise ValueError("known aggressor_side requires direction_source provenance")
    elif direction_source != "unknown":
        raise ValueError("direction_source requires a known aggressor_side")

    iv_source = str(message["iv_source"]).lower()
    if iv_source not in IV_SOURCES:
        raise ValueError(f"Unsupported iv_source: {message['iv_source']}")
    if iv_source == "black_76_inverted":
        provenance = message.get("iv_provenance")
        if not isinstance(provenance, dict):
            raise ValueError("black_76_inverted IV requires iv_provenance")
        _require_fields(
            provenance,
            (
                "method",
                "status",
                "option_price",
                "option_price_source",
                "underlying_price",
                "underlying_price_source",
                "risk_free_rate",
                "time_to_expiry_years",
                "iterations",
                "absolute_price_error",
            ),
        )
        if provenance["method"] != "black_76_bisection":
            raise ValueError("Unsupported IV inversion method")
        if provenance["status"] != "converged":
            raise ValueError("black_76_inverted IV requires converged provenance")
        for field in ("option_price", "underlying_price", "time_to_expiry_years"):
            _require_positive_number(provenance, field)
        _require_non_negative_int(provenance, "iterations")
        try:
            error = float(provenance["absolute_price_error"])
            rate = float(provenance["risk_free_rate"])
        except (TypeError, ValueError) as exc:
            raise ValueError("IV inversion error and risk-free rate must be numeric") from exc
        if not math.isfinite(error) or error < 0 or not math.isfinite(rate):
            raise ValueError("IV inversion error and risk-free rate must be finite")

    pricing_model = str(
        message.get("pricing_model")
        or pricing_model_for_instrument(instrument_class)
    ).lower()
    if pricing_model not in PRICING_MODELS:
        raise ValueError(f"Unsupported pricing_model: {pricing_model}")
    expected_model = pricing_model_for_instrument(instrument_class)
    if pricing_model != expected_model:
        raise ValueError(
            f"pricing_model {pricing_model} conflicts with {instrument_class}; "
            f"expected {expected_model}"
        )

    if expiry_date(message["expiry"]) is None:
        raise ValueError("expiry must be an ISO-8601 date or timestamp")
    _require_aware_timestamp(message, "event_time")
    if message.get("received_time") not in (None, ""):
        _require_aware_timestamp(message, "received_time")
    if message.get("expiry_timestamp") not in (None, ""):
        _require_aware_timestamp(message, "expiry_timestamp")
    if message.get("contract_multiplier") not in (None, ""):
        _require_positive_number(message, "contract_multiplier")


def _require_aware_timestamp(message: NormalizedMessage, field: str) -> None:
    if parse_market_datetime(message.get(field)) is None:
        raise ValueError(f"{field} must be a timezone-bearing ISO-8601 timestamp")

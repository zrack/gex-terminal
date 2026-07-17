import os
import re
from collections.abc import Mapping
from typing import Any

from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
)


DEFAULT_DATABENTO_DATASET = "GLBX.MDP3"
DATABENTO_SCHEMAS = {
    "definitions": "definition",
    "option_trades": "trades",
    "underlying_quotes": "mbp-1",
    "open_interest": "statistics",
}

ADAPTER_INFO = AdapterInfo(
    name="databento",
    label="Databento",
    status="fixture-design",
    notes=(
        "Databento futures-options fixture mapping is documented and tested; "
        "live streaming still requires SDK ingestion work."
    ),
)

_RAW_OPTION_SYMBOL_PATTERN = re.compile(r"(?:^|\s)([CP])\s*\d", re.IGNORECASE)


def databento_option_parent_symbol(underlying: str) -> str:
    """Return the Databento parent symbol used for a futures option chain."""
    symbol = underlying.strip().upper()
    if symbol.endswith(".OPT"):
        return symbol
    return f"{symbol}.OPT"


class DatabentoAdapter(MarketDataAdapter):
    def __init__(self, consumer, target_underlying: str = "ES", dataset: str | None = None):
        self.consumer = consumer
        self.target_underlying = target_underlying.upper()
        self.dataset = dataset or os.getenv("DATABENTO_DATASET", DEFAULT_DATABENTO_DATASET)
        self.api_key = os.getenv("DATABENTO_API_KEY")

    def validate(self) -> None:
        if not self.api_key:
            raise AdapterConfigurationError("missing Databento credential: DATABENTO_API_KEY")
        raise AdapterConfigurationError(
            "Databento adapter is registered but not implemented yet. "
            "The fixture mapping is documented; the next step is adding databento-python "
            "ingestion for definition, trades, mbp-1, and statistics records."
        )

    async def stream_market_data(self) -> None:
        self.validate()

    @staticmethod
    def _normalize_definition_record(record: Mapping[str, Any]) -> dict[str, Any] | None:
        """Normalize one Databento definition row into option metadata."""
        raw_symbol = _text(
            _lookup(record, "raw_symbol", "rawSymbol", "symbol", "stype_symbol")
        )
        strike = _safe_float(_lookup(record, "strike_price", "strikePrice", "strike"))
        option_type = _option_type(record)

        if strike is None or option_type is None:
            return None

        return {
            "instrument_id": _safe_int(_lookup(record, "instrument_id", "instrumentId")),
            "raw_symbol": raw_symbol,
            "underlying": _text(_lookup(record, "underlying", "asset", "product")),
            "strike": strike,
            "option_type": option_type,
            "expiry": _text(_lookup(record, "expiration", "expiration_date", "expiry")),
            "iv": _safe_float(_lookup(record, "iv", "implied_volatility", "impliedVolatility")),
            "min_price_increment": _safe_float(
                _lookup(record, "min_price_increment", "minPriceIncrement")
            ),
        }

    def _normalize_underlying_quote(self, record: Mapping[str, Any]) -> dict[str, Any] | None:
        """Normalize a Databento underlying trade/quote row into an underlying tick."""
        price = _safe_float(
            _lookup(record, "price", "close", "last_px", "last_price", "lastPrice")
        )
        if price is None:
            bid = _safe_float(_lookup(record, "bid_px_00", "bid_price", "bidPrice", "bid"))
            ask = _safe_float(_lookup(record, "ask_px_00", "ask_price", "askPrice", "ask"))
            if bid is not None and ask is not None:
                price = (bid + ask) / 2

        if price is None:
            return None

        return {
            "type": "underlying_tick",
            "symbol": self.target_underlying,
            "price": price,
        }

    @staticmethod
    def _normalize_option_trade_record(
        record: Mapping[str, Any],
        metadata_by_instrument_id: Mapping[int | str, Mapping[str, Any]],
    ) -> dict[str, Any] | None:
        """Join a Databento trade row to definition metadata and normalize volume."""
        instrument_id = _safe_int(_lookup(record, "instrument_id", "instrumentId"))
        metadata = _metadata_for_instrument(instrument_id, metadata_by_instrument_id)
        if not metadata:
            return None

        volume = _safe_int(_lookup(record, "size", "quantity", "volume"))
        if volume is None or volume <= 0:
            return None

        strike = _safe_float(metadata.get("strike"))
        option_type = _text(metadata.get("option_type")).upper()
        if strike is None or option_type not in {"C", "P"}:
            return None

        message = {
            "type": "options_volume_tick",
            "strike": strike,
            "option_type": option_type,
            "volume": volume,
        }
        iv = _safe_float(_lookup(record, "iv", "implied_volatility", "impliedVolatility"))
        if iv is None:
            iv = _safe_float(metadata.get("iv"))
        if iv is not None:
            message["iv"] = iv
        expiry = _text(metadata.get("expiry"))
        if expiry:
            message["expiry"] = expiry
        return message

    @staticmethod
    def _open_interest_from_statistics(
        record: Mapping[str, Any],
    ) -> tuple[int | None, int] | None:
        """Extract open interest from a Databento statistics row when present."""
        stat_type = _text(_lookup(record, "stat_type", "statType", "type")).lower()
        if stat_type and "open_interest" not in stat_type and stat_type not in {"oi", "openinterest"}:
            return None

        open_interest = _safe_int(
            _lookup(record, "open_interest", "openInterest", "quantity", "value")
        )
        if open_interest is None:
            return None

        instrument_id = _safe_int(_lookup(record, "instrument_id", "instrumentId"))
        return instrument_id, open_interest


def _lookup(record: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        value = record.get(field)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _option_type(record: Mapping[str, Any]) -> str | None:
    value = _lookup(record, "option_type", "optionType", "put_call", "call_put", "instrument_class")
    if value not in (None, ""):
        value_text = str(value).strip().upper()
        if value_text.startswith("C"):
            return "C"
        if value_text.startswith("P"):
            return "P"

    raw_symbol = _text(_lookup(record, "raw_symbol", "rawSymbol", "symbol", "stype_symbol"))
    match = _RAW_OPTION_SYMBOL_PATTERN.search(raw_symbol)
    if match:
        return match.group(1).upper()
    return None


def _metadata_for_instrument(
    instrument_id: int | None,
    metadata_by_instrument_id: Mapping[int | str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if instrument_id is None:
        return None
    return (
        metadata_by_instrument_id.get(instrument_id)
        or metadata_by_instrument_id.get(str(instrument_id))
    )

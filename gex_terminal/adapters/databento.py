import os
import re
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from gex_terminal.contracts import days_until_expiry, parse_market_datetime
from gex_terminal.implied_volatility import invert_black_76_iv
from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
    dumps_normalized_message,
)


DEFAULT_DATABENTO_DATASET = "GLBX.MDP3"
DEFAULT_DATABENTO_IV = 0.15
DEFAULT_MAX_UNDERLYING_AGE_SECONDS = 2.0
DATABENTO_SCHEMAS = {
    "definitions": "definition",
    "option_trades": "trades",
    "underlying_quotes": "mbp-1",
    "open_interest": "statistics",
}

ADAPTER_INFO = AdapterInfo(
    name="databento",
    label="Databento",
    status="live-implemented-uncertified",
    notes=(
        "Databento mixed-schema live ingestion and Black-76 IV inversion are "
        "implemented; an explicit credentialed certification run is still required."
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
    def __init__(
        self,
        consumer,
        target_underlying: str = "ES",
        dataset: str | None = None,
        *,
        risk_free_rate: float = 0.045,
        default_iv: float = DEFAULT_DATABENTO_IV,
        max_underlying_age_seconds: float = DEFAULT_MAX_UNDERLYING_AGE_SECONDS,
        live_client_factory=None,
    ):
        self.consumer = consumer
        self.target_underlying = target_underlying.upper()
        self.dataset = dataset or os.getenv("DATABENTO_DATASET", DEFAULT_DATABENTO_DATASET)
        self.api_key = os.getenv("DATABENTO_API_KEY")
        self.risk_free_rate = float(risk_free_rate)
        self.default_iv = float(default_iv)
        self.max_underlying_age_seconds = float(max_underlying_age_seconds)
        self.live_client_factory = live_client_factory
        self.live_client = None
        self.contract_metadata: dict[int, dict[str, Any]] = {}
        self.latest_underlying_price: float | None = None
        self.latest_underlying_event_time: str | None = None
        self.latest_underlying_instrument_id: int | None = None
        self.subscription_ids: list[int] = []
        self._connected_once = False
        self._definition_count = 0
        self._underlying_quote_count = 0
        self._option_trade_count = 0
        self._open_interest_count = 0
        self._inverted_iv_count = 0
        self._iv_fallback_count = 0
        self._dropped_before_definition_count = 0
        self._dropped_before_underlying_count = 0
        self._dropped_underlying_mismatch_count = 0
        self._stale_underlying_count = 0
        self._future_underlying_count = 0
        self._missing_underlying_time_count = 0
        self._crossed_underlying_book_count = 0
        self._incomplete_underlying_book_count = 0
        self._sdk_version = _databento_sdk_version()

    def validate(self) -> None:
        if not self.api_key:
            raise AdapterConfigurationError("missing Databento credential: DATABENTO_API_KEY")
        if self.target_underlying not in {"ES", "NQ"}:
            raise AdapterConfigurationError(
                "Databento live futures-option ingestion currently supports ES or NQ"
            )
        if not math.isfinite(self.risk_free_rate):
            raise AdapterConfigurationError("risk_free_rate must be finite")
        if (
            not math.isfinite(self.max_underlying_age_seconds)
            or self.max_underlying_age_seconds < 0
        ):
            raise AdapterConfigurationError(
                "max_underlying_age_seconds must be finite and non-negative"
            )
        if self.live_client_factory is None:
            try:
                _load_databento_sdk()
            except ModuleNotFoundError as exc:
                raise AdapterConfigurationError(
                    'Databento live mode requires the optional SDK: pip install -e ".[databento]"'
                ) from exc

    async def stream_market_data(self) -> None:
        self.validate()
        client_factory = self.live_client_factory or _load_databento_sdk().Live
        self.live_client = client_factory(
            key=self.api_key,
            reconnect_policy="reconnect",
        )
        option_parent = databento_option_parent_symbol(self.target_underlying)
        future_parent = f"{self.target_underlying}.FUT"
        continuous_future = f"{self.target_underlying}.v.0"
        try:
            self.subscription_ids = [
                self.live_client.subscribe(
                    dataset=self.dataset,
                    schema="definition",
                    symbols=(option_parent, future_parent),
                    stype_in="parent",
                    start=0,
                ),
                self.live_client.subscribe(
                    dataset=self.dataset,
                    schema="mbp-1",
                    symbols=continuous_future,
                    stype_in="continuous",
                    snapshot=True,
                ),
                self.live_client.subscribe(
                    dataset=self.dataset,
                    schema="trades",
                    symbols=option_parent,
                    stype_in="parent",
                ),
            ]
            self._connected_once = True
            self._record_consumer("mark_connected")
            self._record_consumer("mark_subscribed", 3)
            async for record in self.live_client:
                self._record_consumer("record_provider_frame")
                try:
                    await self._handle_live_record(record)
                except (TypeError, ValueError):
                    self._record_consumer("record_provider_parse_error")
        except Exception as exc:
            self._record_consumer("mark_subscription_error")
            if _looks_like_entitlement_error(exc):
                self._record_consumer("record_entitlement_error")
            raise
        finally:
            if self.live_client is not None:
                stop = getattr(self.live_client, "stop", None)
                if callable(stop):
                    stop()
            self._record_consumer("mark_disconnected")

    async def _handle_live_record(self, record: Any) -> None:
        kind = _record_kind(record)
        if kind == "error":
            raise RuntimeError("Databento live gateway returned an error record")
        values = _record_mapping(record, kind)
        if kind == "definition":
            metadata = self._normalize_definition_record(values)
            if metadata and metadata.get("instrument_id") is not None:
                underlying = str(metadata.get("underlying") or "").upper()
                if underlying in {"", self.target_underlying}:
                    self.contract_metadata[int(metadata["instrument_id"])] = metadata
                    self._definition_count += 1
            return
        if kind == "underlying_quote":
            book_status = _underlying_book_status(values)
            message = self._normalize_underlying_quote(values)
            if message is None:
                if book_status == "crossed":
                    self._crossed_underlying_book_count += 1
                elif book_status == "incomplete":
                    self._incomplete_underlying_book_count += 1
                self._record_consumer("record_dropped_message")
                return
            self.latest_underlying_price = float(message["price"])
            self.latest_underlying_event_time = str(message["event_time"])
            self.latest_underlying_instrument_id = _safe_int(
                _lookup(values, "instrument_id", "instrumentId")
            )
            self._underlying_quote_count += 1
            await self.consumer.update_market_state(dumps_normalized_message(message))
            return
        if kind == "option_trade":
            instrument_id = _safe_int(_lookup(values, "instrument_id", "instrumentId"))
            if not _metadata_for_instrument(instrument_id, self.contract_metadata):
                self._dropped_before_definition_count += 1
                self._record_consumer("record_dropped_message")
                return
            metadata = _metadata_for_instrument(instrument_id, self.contract_metadata) or {}
            option_underlying_id = _safe_int(metadata.get("underlying_id"))
            if (
                option_underlying_id is not None
                and self.latest_underlying_instrument_id is not None
                and option_underlying_id != self.latest_underlying_instrument_id
            ):
                self._dropped_underlying_mismatch_count += 1
                self._record_consumer("record_dropped_message")
                return
            if self.latest_underlying_price is None:
                self._dropped_before_underlying_count += 1
            timing = underlying_timing_status(
                option_event_time=_lookup(
                    values, "ts_event", "tsEvent", "event_time", "timestamp"
                ),
                underlying_event_time=self.latest_underlying_event_time,
                maximum_age_seconds=self.max_underlying_age_seconds,
            )
            if timing["status"] == "stale_underlying_price":
                self._stale_underlying_count += 1
            elif timing["status"] == "future_underlying_price":
                self._future_underlying_count += 1
            elif timing["status"] == "missing_event_time":
                self._missing_underlying_time_count += 1
            message = self._normalize_option_trade_record(
                values,
                self.contract_metadata,
                underlying_price=self.latest_underlying_price,
                underlying_event_time=self.latest_underlying_event_time,
                underlying_instrument_id=self.latest_underlying_instrument_id,
                risk_free_rate=self.risk_free_rate,
                default_iv=self.default_iv,
                max_underlying_age_seconds=self.max_underlying_age_seconds,
            )
            if message is None:
                self._record_consumer("record_dropped_message")
                return
            self._option_trade_count += 1
            if message["iv_source"] == "black_76_inverted":
                self._inverted_iv_count += 1
            else:
                self._iv_fallback_count += 1
            await self.consumer.update_market_state(dumps_normalized_message(message))
            return
        if kind == "statistics":
            message = self._normalize_statistics_record(
                values, self.contract_metadata, default_iv=self.default_iv
            )
            if message is None:
                self._record_consumer("record_dropped_message")
                return
            self._open_interest_count += 1
            await self.consumer.update_market_state(dumps_normalized_message(message))

    def _record_consumer(self, method_name: str, *args) -> None:
        method = getattr(self.consumer, method_name, None)
        if callable(method):
            method(*args)

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

        expiry_value = _lookup(
            record,
            "expiration_time",
            "expirationTime",
            "expiration",
            "expiration_date",
            "expiry",
        )
        expiry_text = _timestamp_text(expiry_value)
        expiry_timestamp = (
            expiry_text if parse_market_datetime(expiry_text) is not None else ""
        )
        return {
            "instrument_id": _safe_int(_lookup(record, "instrument_id", "instrumentId")),
            "raw_symbol": raw_symbol,
            "underlying": _text(_lookup(record, "asset", "underlying", "product")),
            "underlying_id": _safe_int(
                _lookup(record, "underlying_id", "underlyingId")
            ),
            "strike": strike,
            "option_type": option_type,
            "expiry": _date_label(expiry_text or expiry_value),
            "expiry_timestamp": expiry_timestamp,
            "iv": _safe_float(_lookup(record, "iv", "implied_volatility", "impliedVolatility")),
            "min_price_increment": _safe_float(
                _lookup(record, "min_price_increment", "minPriceIncrement")
            ),
            "contract_multiplier": _safe_float(
                _lookup(record, "contract_multiplier", "contractMultiplier")
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
                if ask < bid:
                    return None
                price = (bid + ask) / 2

        if price is None:
            return None

        return {
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "databento",
            "symbol": self.target_underlying,
            "price": price,
            "event_time": _timestamp_text(
                _lookup(record, "ts_event", "tsEvent", "event_time", "timestamp")
            ),
        }

    @staticmethod
    def _normalize_option_trade_record(
        record: Mapping[str, Any],
        metadata_by_instrument_id: Mapping[int | str, Mapping[str, Any]],
        *,
        underlying_price: float | None = None,
        underlying_event_time: str | None = None,
        underlying_instrument_id: int | None = None,
        risk_free_rate: float = 0.045,
        default_iv: float = DEFAULT_DATABENTO_IV,
        max_underlying_age_seconds: float = DEFAULT_MAX_UNDERLYING_AGE_SECONDS,
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

        event_time = _timestamp_text(
            _lookup(record, "ts_event", "tsEvent", "event_time", "timestamp")
        )
        message = {
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "databento",
            "contract_id": str(instrument_id),
            "contract_symbol": _text(metadata.get("raw_symbol")),
            "symbol": _text(metadata.get("underlying")).upper(),
            "strike": strike,
            "option_type": option_type,
            "volume": volume,
            "instrument_class": "futures_option",
            "volume_semantics": "incremental",
            "position_source": "trade_volume",
            "pricing_model": "black_76",
            "event_time": event_time,
        }
        aggressor_side = _aggressor_side(_lookup(record, "side", "aggressor_side"))
        message["aggressor_side"] = aggressor_side
        message["direction_source"] = (
            "provider" if aggressor_side != "unknown" else "unknown"
        )
        sequence = _safe_int(_lookup(record, "sequence", "seq"))
        if sequence is not None:
            message["sequence"] = sequence
        received_time = _timestamp_text(
            _lookup(record, "ts_recv", "received_time", "receivedTime")
        )
        if received_time:
            message["received_time"] = received_time
        iv = _safe_float(_lookup(record, "iv", "implied_volatility", "impliedVolatility"))
        if iv is None:
            iv = _safe_float(metadata.get("iv"))
        iv_provenance: dict[str, Any] | None = None
        if iv is None:
            option_price = _safe_float(
                _lookup(record, "price", "trade_price", "last_price", "lastPrice")
            )
            expiry_timestamp = _timestamp_text(metadata.get("expiry_timestamp"))
            as_of = parse_market_datetime(event_time)
            timing = underlying_timing_status(
                option_event_time=event_time,
                underlying_event_time=underlying_event_time,
                maximum_age_seconds=max_underlying_age_seconds,
            )
            remaining_days = (
                days_until_expiry(expiry_timestamp, as_of)
                if expiry_timestamp and as_of is not None
                else None
            )
            inversion = None
            if (
                option_price is not None
                and underlying_price is not None
                and remaining_days is not None
                and remaining_days > 0
                and timing["status"] == "aligned"
            ):
                inversion = invert_black_76_iv(
                    option_price=option_price,
                    futures_price=float(underlying_price),
                    strike=strike,
                    time_to_expiry_years=remaining_days / 365.0,
                    risk_free_rate=float(risk_free_rate),
                    option_type=option_type,
                )
            if inversion is not None and inversion.status == "converged" and inversion.iv:
                iv = inversion.iv
                iv_source = "black_76_inverted"
                iv_provenance = {
                    "method": "black_76_bisection",
                    "status": inversion.status,
                    "option_price": option_price,
                    "option_price_source": "databento_trade",
                    "underlying_price": float(underlying_price),
                    "underlying_price_source": "databento_mbp1_midpoint",
                    "underlying_event_time": underlying_event_time,
                    "underlying_instrument_id": underlying_instrument_id,
                    "underlying_price_age_ms": timing["age_ms"],
                    "maximum_underlying_age_ms": timing["maximum_age_ms"],
                    "risk_free_rate": float(risk_free_rate),
                    "time_to_expiry_years": remaining_days / 365.0,
                    "iterations": inversion.iterations,
                    "absolute_price_error": inversion.absolute_price_error,
                }
            else:
                iv = float(default_iv)
                iv_source = "configured_default"
                iv_provenance = {
                    "method": "black_76_bisection",
                    "status": (
                        inversion.status
                        if inversion is not None
                        else timing["status"]
                        if timing["status"] != "aligned"
                        else "missing_inversion_input"
                    ),
                    "option_price_source": "databento_trade" if option_price is not None else "missing",
                    "underlying_price_source": (
                        "databento_mbp1_midpoint" if underlying_price is not None else "missing"
                    ),
                    "underlying_price_age_ms": timing["age_ms"],
                    "maximum_underlying_age_ms": timing["maximum_age_ms"],
                }
        else:
            iv_source = "provider"
        message["iv"] = iv
        message["iv_source"] = iv_source
        if iv_provenance is not None:
            message["iv_provenance"] = iv_provenance
        expiry = _text(metadata.get("expiry"))
        if expiry:
            message["expiry"] = expiry
        expiry_timestamp = _timestamp_text(metadata.get("expiry_timestamp"))
        if expiry_timestamp:
            message["expiry_timestamp"] = expiry_timestamp
        multiplier = _safe_float(metadata.get("contract_multiplier"))
        if multiplier is not None and multiplier > 0:
            message["contract_multiplier"] = multiplier
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

    @classmethod
    def _normalize_statistics_record(
        cls,
        record: Mapping[str, Any],
        metadata_by_instrument_id: Mapping[int | str, Mapping[str, Any]],
        *,
        default_iv: float = DEFAULT_DATABENTO_IV,
    ) -> dict[str, Any] | None:
        extracted = cls._open_interest_from_statistics(record)
        if extracted is None:
            return None
        instrument_id, open_interest = extracted
        metadata = _metadata_for_instrument(instrument_id, metadata_by_instrument_id)
        if not metadata or open_interest < 0:
            return None
        strike = _safe_float(metadata.get("strike"))
        option_type = _text(metadata.get("option_type")).upper()
        if strike is None or option_type not in {"C", "P"}:
            return None
        iv = _safe_float(metadata.get("iv"))
        event_time = _timestamp_text(
            _lookup(record, "ts_event", "tsEvent", "event_time", "timestamp")
        )
        if parse_market_datetime(event_time) is None:
            return None
        message = {
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "databento",
            "contract_id": str(instrument_id),
            "contract_symbol": _text(metadata.get("raw_symbol")),
            "symbol": _text(metadata.get("underlying")).upper(),
            "strike": strike,
            "option_type": option_type,
            "volume": open_interest,
            "instrument_class": "futures_option",
            "volume_semantics": "cumulative",
            "position_source": "open_interest",
            "pricing_model": "black_76",
            "iv": iv if iv is not None else float(default_iv),
            "iv_source": "provider" if iv is not None else "configured_default",
            "aggressor_side": "unknown",
            "direction_source": "unknown",
            "event_time": event_time,
        }
        for field in ("expiry", "expiry_timestamp", "contract_multiplier"):
            value = metadata.get(field)
            if value not in (None, ""):
                message[field] = value
        return message


def _lookup(record: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        value = record.get(field)
        if value not in (None, ""):
            return value
    return None


def _aggressor_side(value: Any) -> str:
    """Normalize Databento trade-side codes without inventing missing direction."""
    text = _text(value).strip().lower()
    if text in {"b", "bid", "buy"}:
        return "buy"
    if text in {"a", "ask", "s", "sell"}:
        return "sell"
    return "unknown"


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
        if value_text.startswith("C") or "CALL" in value_text:
            return "C"
        if value_text.startswith("P") or "PUT" in value_text:
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


def _load_databento_sdk():
    import databento

    return databento


def _databento_sdk_version() -> str | None:
    try:
        return version("databento")
    except PackageNotFoundError:
        return None


def _record_kind(record: Any) -> str:
    if isinstance(record, Mapping):
        explicit = _text(record.get("record_type") or record.get("schema")).lower()
    else:
        explicit = type(record).__name__.lower()
    if "instrumentdef" in explicit or explicit in {"definition", "definitions"}:
        return "definition"
    if "mbp1" in explicit or explicit in {"mbp-1", "underlying_quote"}:
        return "underlying_quote"
    if "trademsg" in explicit or explicit in {"trade", "trades", "option_trade"}:
        return "option_trade"
    if "statistics" in explicit or "statmsg" in explicit or explicit in {"stat", "stats"}:
        return "statistics"
    if "errormsg" in explicit or explicit == "error":
        return "error"
    return "control"


def _record_mapping(record: Any, kind: str) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)

    common = (
        "instrument_id",
        "raw_symbol",
        "asset",
        "underlying",
        "underlying_id",
        "instrument_class",
        "contract_multiplier",
        "side",
        "size",
        "sequence",
    )
    values = {
        field: getattr(record, field)
        for field in common
        if getattr(record, field, None) not in (None, "")
    }
    values["ts_event"] = _first_record_value(record, "pretty_ts_event", "ts_event")
    values["received_time"] = _first_record_value(record, "pretty_ts_recv", "ts_recv")
    if kind == "definition":
        values["strike_price"] = _first_record_value(
            record, "pretty_strike_price", "strike_price"
        )
        values["expiration"] = _first_record_value(
            record, "pretty_expiration", "expiration"
        )
        values["min_price_increment"] = _first_record_value(
            record, "pretty_min_price_increment", "min_price_increment"
        )
    elif kind == "underlying_quote":
        values["bid_px_00"] = _first_record_value(record, "pretty_bid_px_00", "bid_px_00")
        values["ask_px_00"] = _first_record_value(record, "pretty_ask_px_00", "ask_px_00")
    elif kind == "option_trade":
        values["price"] = _first_record_value(record, "pretty_price", "price")
    elif kind == "statistics":
        values["stat_type"] = _first_record_value(record, "stat_type")
        values["quantity"] = _first_record_value(record, "quantity")
    return values


def _first_record_value(record: Any, *fields: str) -> Any:
    for field in fields:
        value = getattr(record, field, None)
        if value not in (None, ""):
            return value
    return None


def _timestamp_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, int):
        return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    text = str(value).strip()
    parsed = parse_market_datetime(text)
    if parsed is not None:
        return text
    return text


def _date_label(value: Any) -> str:
    timestamp = _timestamp_text(value)
    return timestamp[:10] if len(timestamp) >= 10 else timestamp


def _looks_like_entitlement_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("auth", "credential", "entitlement", "license", "permission"))


def _underlying_book_status(record: Mapping[str, Any]) -> str:
    direct = _safe_float(
        _lookup(record, "price", "close", "last_px", "last_price", "lastPrice")
    )
    if direct is not None:
        return "direct_price"
    bid = _safe_float(_lookup(record, "bid_px_00", "bid_price", "bidPrice", "bid"))
    ask = _safe_float(_lookup(record, "ask_px_00", "ask_price", "askPrice", "ask"))
    if bid is None or ask is None:
        return "incomplete"
    return "crossed" if ask < bid else "locked" if ask == bid else "valid"


def underlying_timing_status(
    *,
    option_event_time: Any,
    underlying_event_time: Any,
    maximum_age_seconds: float = DEFAULT_MAX_UNDERLYING_AGE_SECONDS,
) -> dict[str, Any]:
    """Classify whether an underlying quote is safe for option-price inversion."""
    option_time = parse_market_datetime(_timestamp_text(option_event_time))
    underlying_time = parse_market_datetime(_timestamp_text(underlying_event_time))
    maximum_age_ms = float(maximum_age_seconds) * 1000.0
    if option_time is None or underlying_time is None:
        return {
            "status": "missing_event_time",
            "age_ms": None,
            "maximum_age_ms": maximum_age_ms,
        }
    age_ms = (option_time - underlying_time).total_seconds() * 1000.0
    if age_ms < 0:
        status = "future_underlying_price"
    elif age_ms > maximum_age_ms:
        status = "stale_underlying_price"
    else:
        status = "aligned"
    return {
        "status": status,
        "age_ms": age_ms,
        "maximum_age_ms": maximum_age_ms,
    }

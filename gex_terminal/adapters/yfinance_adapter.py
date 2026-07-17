from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
    dumps_normalized_message,
)


ADAPTER_INFO = AdapterInfo(
    name="yfinance",
    label="Yahoo Finance / yfinance",
    status="delayed",
    notes="Delayed equity/ETF options snapshot adapter for SPY/QQQ-style research. Not suitable for ES/NQ futures options.",
)


class YfinanceAdapter(MarketDataAdapter):
    def __init__(self, consumer, target_underlying: str = "SPY"):
        self.consumer = consumer
        self.target_underlying = target_underlying.upper()
        self._yfinance = None

    def validate(self) -> None:
        if self.target_underlying in {"ES", "MES", "NQ", "MNQ"}:
            raise AdapterConfigurationError(
                "yfinance only supports delayed equity/ETF option chains such as SPY or QQQ; "
                "use a futures-capable provider for ES/NQ."
            )
        try:
            import yfinance
        except ModuleNotFoundError as exc:
            raise AdapterConfigurationError(
                'yfinance adapter requires yfinance. Install with: pip install -e ".[yfinance]"'
            ) from exc
        self._yfinance = yfinance

    async def stream_market_data(self) -> None:
        self.validate()
        self.consumer.mark_connected()
        try:
            ticker = self._yfinance.Ticker(self.target_underlying)
            price = self._quote_price(ticker)
            await self.consumer.update_market_state(dumps_normalized_message({
                "type": "underlying_tick",
                "symbol": self.target_underlying,
                "price": price,
            }))

            expiry = self._select_expiry(ticker)
            chain = ticker.option_chain(expiry)
            for row in self._normalized_option_rows(chain.calls, "C", expiry):
                await self.consumer.update_market_state(dumps_normalized_message(row))
            for row in self._normalized_option_rows(chain.puts, "P", expiry):
                await self.consumer.update_market_state(dumps_normalized_message(row))
        finally:
            self.consumer.mark_disconnected()

    @staticmethod
    def _records(table) -> list[dict]:
        if hasattr(table, "to_dict"):
            return list(table.to_dict("records"))
        return list(table)

    def _normalized_option_rows(self, table, option_type: str, expiry: str) -> list[dict]:
        rows = []
        for row in self._records(table):
            strike = _safe_float(row.get("strike"))
            if strike is None:
                continue
            volume = _safe_int(row.get("volume"))
            if volume <= 0:
                volume = _safe_int(row.get("openInterest"))
            if volume <= 0:
                continue
            iv = _safe_float(row.get("impliedVolatility")) or 0.20
            rows.append({
                "type": "options_volume_tick",
                "strike": strike,
                "option_type": option_type,
                "volume": volume,
                "iv": iv,
                "expiry": expiry,
            })
        return rows

    def _select_expiry(self, ticker) -> str:
        options = tuple(getattr(ticker, "options", ()) or ())
        if not options:
            raise AdapterConfigurationError(
                f"No option expirations returned by yfinance for {self.target_underlying}"
            )
        return str(options[0])

    def _quote_price(self, ticker) -> float:
        fast_info = getattr(ticker, "fast_info", {}) or {}
        for key in ("last_price", "lastPrice", "regular_market_price", "regularMarketPrice"):
            price = _safe_float(_lookup(fast_info, key))
            if price and price > 0:
                return price

        history = ticker.history(period="1d")
        if hasattr(history, "empty") and history.empty:
            raise AdapterConfigurationError(
                f"No quote history returned by yfinance for {self.target_underlying}"
            )
        close_series = history["Close"] if hasattr(history, "__getitem__") else []
        if hasattr(close_series, "dropna"):
            close_series = close_series.dropna()
        if hasattr(close_series, "iloc"):
            price = _safe_float(close_series.iloc[-1])
        else:
            values = list(close_series)
            price = _safe_float(values[-1] if values else None)
        if price is None or price <= 0:
            raise AdapterConfigurationError(
                f"No usable quote price returned by yfinance for {self.target_underlying}"
            )
        return price


def _lookup(mapping, key: str):
    if isinstance(mapping, dict):
        return mapping.get(key)
    return getattr(mapping, key, None)


def _safe_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _safe_int(value) -> int:
    number = _safe_float(value)
    if number is None:
        return 0
    return max(0, int(number))

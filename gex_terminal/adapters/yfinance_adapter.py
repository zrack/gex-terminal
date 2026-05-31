from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
)


ADAPTER_INFO = AdapterInfo(
    name="yfinance",
    label="Yahoo Finance / yfinance",
    status="scaffold",
    notes="Delayed equity/ETF options snapshot adapter scaffold. Not suitable for ES/NQ futures options.",
)


class YfinanceAdapter(MarketDataAdapter):
    def __init__(self, consumer, target_underlying: str = "SPY"):
        self.consumer = consumer
        self.target_underlying = target_underlying

    def validate(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ModuleNotFoundError as exc:
            raise AdapterConfigurationError(
                "yfinance adapter requires yfinance. Install it separately with: pip install yfinance"
            ) from exc
        raise AdapterConfigurationError(
            "yfinance adapter is registered but not implemented yet. "
            "Add snapshot polling and normalize option-chain rows into the shared adapter contract."
        )

    async def stream_market_data(self) -> None:
        self.validate()

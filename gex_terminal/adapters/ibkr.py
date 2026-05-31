import os

from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
)


ADAPTER_INFO = AdapterInfo(
    name="ibkr",
    label="Interactive Brokers",
    status="scaffold",
    notes="IBKR/TWS adapter scaffold. Requires TWS or IB Gateway plus a client library such as ib_insync.",
)


class IbkrAdapter(MarketDataAdapter):
    def __init__(self, consumer, target_underlying: str = "ES"):
        self.consumer = consumer
        self.target_underlying = target_underlying
        self.host = os.getenv("IBKR_HOST", "127.0.0.1")
        self.port = int(os.getenv("IBKR_PORT", "7497"))
        self.client_id = int(os.getenv("IBKR_CLIENT_ID", "17"))

    def validate(self) -> None:
        try:
            import ib_insync  # noqa: F401
        except ModuleNotFoundError as exc:
            raise AdapterConfigurationError(
                "IBKR adapter requires ib_insync. Install it separately with: pip install ib_insync"
            ) from exc
        raise AdapterConfigurationError(
            "IBKR adapter is registered but not implemented yet. "
            "Connect TWS/Gateway, request contracts, and normalize ticks into the shared adapter contract."
        )

    async def stream_market_data(self) -> None:
        self.validate()

import os

from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
)


ADAPTER_INFO = AdapterInfo(
    name="databento",
    label="Databento",
    status="scaffold",
    notes="Futures/options market-data adapter scaffold. Requires Databento credentials and payload validation.",
)


class DatabentoAdapter(MarketDataAdapter):
    def __init__(self, consumer, target_underlying: str = "ES", dataset: str | None = None):
        self.consumer = consumer
        self.target_underlying = target_underlying
        self.dataset = dataset or os.getenv("DATABENTO_DATASET", "GLBX.MDP3")
        self.api_key = os.getenv("DATABENTO_API_KEY")

    def validate(self) -> None:
        if not self.api_key:
            raise AdapterConfigurationError("missing Databento credential: DATABENTO_API_KEY")
        raise AdapterConfigurationError(
            "Databento adapter is registered but not implemented yet. "
            "Add databento-python ingestion and normalize records into the shared adapter contract."
        )

    async def stream_market_data(self) -> None:
        self.validate()

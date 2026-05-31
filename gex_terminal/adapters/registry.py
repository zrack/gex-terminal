from collections.abc import Callable

from gex_terminal.adapters.databento import ADAPTER_INFO as DATABENTO_INFO
from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.adapters.ibkr import ADAPTER_INFO as IBKR_INFO
from gex_terminal.adapters.ibkr import IbkrAdapter
from gex_terminal.adapters.replay import ADAPTER_INFO as REPLAY_INFO
from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.adapters.tradovate import ADAPTER_INFO as TRADOVATE_INFO
from gex_terminal.adapters.tradovate import TradovateAdapter, validate_tradovate_credentials
from gex_terminal.adapters.yfinance_adapter import ADAPTER_INFO as YFINANCE_INFO
from gex_terminal.adapters.yfinance_adapter import YfinanceAdapter
from gex_terminal.config import GexConfig
from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    AdapterInfo,
    MarketDataAdapter,
)


AdapterBuilder = Callable[[object, GexConfig], MarketDataAdapter]


def _build_replay(consumer, config: GexConfig) -> MarketDataAdapter:
    return ReplayAdapter(
        consumer,
        replay_path=config.replay_path,
        delay_seconds=config.replay_delay_seconds,
    )


def _build_tradovate(consumer, config: GexConfig) -> MarketDataAdapter:
    validate_tradovate_credentials()
    return TradovateAdapter(
        consumer,
        target_underlying=config.symbol,
        environment=config.tradovate_environment,
    )


def _build_databento(consumer, config: GexConfig) -> MarketDataAdapter:
    return DatabentoAdapter(consumer, target_underlying=config.symbol)


def _build_ibkr(consumer, config: GexConfig) -> MarketDataAdapter:
    return IbkrAdapter(consumer, target_underlying=config.symbol)


def _build_yfinance(consumer, config: GexConfig) -> MarketDataAdapter:
    return YfinanceAdapter(consumer, target_underlying=config.symbol)


ADAPTERS: dict[str, AdapterBuilder] = {
    "replay": _build_replay,
    "tradovate": _build_tradovate,
    "databento": _build_databento,
    "ibkr": _build_ibkr,
    "yfinance": _build_yfinance,
}

ADAPTER_INFOS: dict[str, AdapterInfo] = {
    info.name: info
    for info in (
        REPLAY_INFO,
        TRADOVATE_INFO,
        DATABENTO_INFO,
        IBKR_INFO,
        YFINANCE_INFO,
    )
}


def available_provider_names() -> tuple[str, ...]:
    return tuple(sorted(ADAPTERS))


def adapter_info(provider: str) -> AdapterInfo:
    return ADAPTER_INFOS[provider]


def build_market_data_adapter(
    consumer, config: GexConfig, *, validate: bool = True
) -> MarketDataAdapter:
    provider = effective_provider(config)
    try:
        adapter = ADAPTERS[provider](consumer, config)
    except KeyError as exc:
        raise AdapterConfigurationError(
            f"Unsupported provider '{provider}'. Expected one of: {', '.join(available_provider_names())}"
        ) from exc
    if validate:
        validate_market_data_adapter(adapter)
    return adapter


def effective_provider(config: GexConfig) -> str:
    if config.data_mode == "replay":
        return "replay"
    return config.data_provider


def validate_market_data_adapter(adapter: MarketDataAdapter) -> None:
    validate = getattr(adapter, "validate", None)
    if callable(validate):
        validate()

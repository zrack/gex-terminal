import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return _load_dotenv_fallback()

@dataclass(frozen=True)
class GexConfig:
    symbol: str
    symbols: tuple[str, ...]
    data_mode: str
    contract_multiplier: int
    risk_free_rate: float
    days_to_expiry: float
    refresh_interval_seconds: float
    stale_after_seconds: float
    replay_path: str
    replay_delay_seconds: float
    tradovate_environment: str

    @classmethod
    def from_env(cls) -> "GexConfig":
        symbol = _env_str("GEX_SYMBOL", "ES").upper()
        symbols = _env_symbols("GEX_SYMBOLS", ("ES", "NQ", "SPX", "QQQ"), symbol)
        return cls(
            symbol=symbol,
            symbols=symbols,
            data_mode=_env_str("GEX_DATA_MODE", "demo").lower(),
            contract_multiplier=_env_int("GEX_CONTRACT_MULTIPLIER", 50),
            risk_free_rate=_env_float("GEX_RISK_FREE_RATE", 0.045),
            days_to_expiry=_env_float("GEX_DAYS_TO_EXPIRY", 0.01),
            refresh_interval_seconds=_env_float("GEX_REFRESH_INTERVAL_SECONDS", 1.0),
            stale_after_seconds=_env_float("GEX_STALE_AFTER_SECONDS", 10.0),
            replay_path=_env_str("GEX_REPLAY_PATH", "sample_data/demo_replay.jsonl"),
            replay_delay_seconds=_env_float("GEX_REPLAY_DELAY_SECONDS", 0.05),
            tradovate_environment=_env_str("TRADOVATE_ENV", "demo").lower(),
        )


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_symbols(name: str, default: tuple[str, ...], target_symbol: str) -> tuple[str, ...]:
    raw_symbols = os.getenv(name)
    symbols = tuple(
        symbol.strip().upper()
        for symbol in (raw_symbols.split(",") if raw_symbols else default)
        if symbol.strip()
    )
    if target_symbol not in symbols:
        symbols = (target_symbol, *symbols)
    return symbols[:4]


def _load_dotenv_fallback(path: str = ".env") -> bool:
    if not os.path.exists(path):
        return False

    loaded = False
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
                loaded = True
    return loaded


load_dotenv()

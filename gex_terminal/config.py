import os
from dataclasses import dataclass
from pathlib import Path

from gex_terminal.package_data import replay_data_path

try:
    from dotenv import load_dotenv as _python_dotenv_load
except ModuleNotFoundError:
    _python_dotenv_load = None

@dataclass(frozen=True)
class GexConfig:
    symbol: str
    symbols: tuple[str, ...]
    data_mode: str
    data_provider: str
    contract_multiplier: int
    risk_free_rate: float
    days_to_expiry: float
    refresh_interval_seconds: float
    stale_after_seconds: float
    replay_path: str
    replay_delay_seconds: float
    tradovate_environment: str
    expiry_filter: str = "all"
    replay_clock: str = "auto"
    replay_speed: float = 1.0
    replay_max_gap_seconds: float | None = None
    strict_event_time: bool = False

    @classmethod
    def from_env(cls) -> "GexConfig":
        symbol = _env_str("GEX_SYMBOL", "ES").upper()
        symbols = _env_symbols("GEX_SYMBOLS", ("ES", "NQ", "SPX", "QQQ"), symbol)
        return cls(
            symbol=symbol,
            symbols=symbols,
            data_mode=_env_str("GEX_DATA_MODE", "demo").lower(),
            data_provider=_env_str("GEX_DATA_PROVIDER", "tradovate").lower(),
            contract_multiplier=_env_int("GEX_CONTRACT_MULTIPLIER", 50),
            risk_free_rate=_env_float("GEX_RISK_FREE_RATE", 0.045),
            days_to_expiry=_env_float("GEX_DAYS_TO_EXPIRY", 0.25),
            refresh_interval_seconds=_env_float("GEX_REFRESH_INTERVAL_SECONDS", 1.0),
            stale_after_seconds=_env_float("GEX_STALE_AFTER_SECONDS", 10.0),
            replay_path=_env_str(
                "GEX_REPLAY_PATH", str(replay_data_path("demo_replay.jsonl"))
            ),
            replay_delay_seconds=_env_float("GEX_REPLAY_DELAY_SECONDS", 0.05),
            tradovate_environment=_env_str("TRADOVATE_ENV", "demo").lower(),
            expiry_filter=_env_str("GEX_EXPIRY_FILTER", "all"),
            replay_clock=_env_str("GEX_REPLAY_CLOCK", "auto").lower(),
            replay_speed=_env_float("GEX_REPLAY_SPEED", 1.0),
            replay_max_gap_seconds=_env_optional_float("GEX_REPLAY_MAX_GAP_SECONDS"),
            strict_event_time=_env_bool("GEX_STRICT_EVENT_TIME", False),
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


def _env_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
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


def _load_dotenv_fallback(path: str | os.PathLike[str] = ".env") -> bool:
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


def _load_working_directory_dotenv() -> bool:
    """Load only the caller's current-working-directory ``.env`` file."""
    dotenv_path = Path.cwd() / ".env"
    if _python_dotenv_load is not None:
        return bool(_python_dotenv_load(dotenv_path=dotenv_path, override=False))
    return _load_dotenv_fallback(dotenv_path)


_load_working_directory_dotenv()

"""Bundled replay-session catalog for no-credential research workflows."""

from dataclasses import dataclass, replace
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.package_data import replay_data_path


@dataclass(frozen=True)
class ReplaySession:
    name: str
    path: str
    label: str
    description: str
    public_ref: str | None = None
    symbol: str = "ES"
    contract_multiplier: int = 50

    @property
    def source_ref(self) -> str:
        """Stable public identity; ``path`` remains the internal I/O location."""
        return self.public_ref or f"bundled:{self.name}"


REPLAY_SESSIONS: tuple[ReplaySession, ...] = (
    ReplaySession(
        name="demo",
        path=str(replay_data_path("demo_replay.jsonl")),
        label="Compact Demo",
        description="Small seeded fixture used for screenshots and smoke tests.",
    ),
    ReplaySession(
        name="full-session",
        path=str(replay_data_path("es_synthetic_full_session.jsonl")),
        label="Synthetic Full Session",
        description="Open, mid-session, and late-session ES 0DTE flow.",
    ),
    ReplaySession(
        name="trend-day",
        path=str(replay_data_path("es_trend_day.jsonl")),
        label="Trend Day",
        description="Uptrend with call-side accumulation and rising spot.",
    ),
    ReplaySession(
        name="chop-day",
        path=str(replay_data_path("es_chop_day.jsonl")),
        label="Chop Day",
        description="Range-bound session with balanced call and put flow.",
    ),
    ReplaySession(
        name="volatility-spike",
        path=str(replay_data_path("es_volatility_spike.jsonl")),
        label="Volatility Spike",
        description="Fast downside move with higher IV and put-heavy flow.",
    ),
    ReplaySession(
        name="gap-fade",
        path=str(replay_data_path("es_gap_fade.jsonl")),
        label="Gap And Fade",
        description="Gap-up open that rejects higher call walls and rotates into put-heavy fade flow.",
    ),
    ReplaySession(
        name="call-wall-breakout",
        path=str(replay_data_path("es_call_wall_breakout.jsonl")),
        label="Call Wall Breakout",
        description="Upside breakout that walks the call wall higher across the session.",
    ),
    ReplaySession(
        name="zero-gamma-flip",
        path=str(replay_data_path("es_zero_gamma_flip.jsonl")),
        label="Zero-Gamma Flip",
        description="Flow rotates across the zero-gamma boundary.",
    ),
    ReplaySession(
        name="expiration-compression",
        path=str(replay_data_path("es_expiration_compression.jsonl")),
        label="Expiration Compression",
        description="Late 0DTE pinning flow around the gamma wall.",
    ),
    ReplaySession(
        name="quality-stress",
        path=str(replay_data_path("es_quality_stress.jsonl")),
        label="Quality Stress",
        description="Valid replay fixture with off-symbol drops and partial chain coverage.",
    ),
)


def bundled_replay_sessions() -> tuple[ReplaySession, ...]:
    return REPLAY_SESSIONS


def replay_session_names() -> tuple[str, ...]:
    return tuple(session.name for session in REPLAY_SESSIONS)


def replay_session_for_name(name: str) -> ReplaySession:
    normalized = name.strip().lower()
    for session in REPLAY_SESSIONS:
        if session.name == normalized:
            return session
    expected = ", ".join(replay_session_names())
    raise KeyError(f"Unknown replay session '{name}'. Expected one of: {expected}")


def config_for_replay_session(
    config: GexConfig,
    session: ReplaySession,
    *,
    explicit_symbol: str | None = None,
    explicit_multiplier: int | None = None,
) -> GexConfig:
    """Apply catalog-owned replay identity and reject explicit conflicts.

    Environment defaults may describe another workflow, so the selected catalog
    session owns its symbol and multiplier.  A symbol or multiplier supplied
    explicitly for the same invocation is different: accepting a conflict would
    silently mislabel the replay, so it fails before any state is built.
    """
    symbol = str(session.symbol).strip().upper()
    multiplier = session.contract_multiplier
    if not symbol:
        raise ValueError(f"Replay session '{session.name}' has no catalog symbol")
    if type(multiplier) is not int or multiplier <= 0:
        raise ValueError(
            f"Replay session '{session.name}' has an invalid catalog multiplier"
        )

    if explicit_symbol is not None:
        requested_symbol = str(explicit_symbol).strip().upper()
        if requested_symbol != symbol:
            raise ValueError(
                f"Replay session '{session.name}' requires symbol {symbol}; "
                "the explicit symbol override conflicts with its catalog identity"
            )
    if explicit_multiplier is not None:
        if type(explicit_multiplier) is not int or explicit_multiplier != multiplier:
            raise ValueError(
                f"Replay session '{session.name}' requires contract multiplier {multiplier}; "
                "the explicit multiplier override conflicts with its catalog identity"
            )

    symbols = (symbol, *(candidate for candidate in config.symbols if candidate != symbol))
    return replace(
        config,
        symbol=symbol,
        symbols=tuple(symbols[:4]),
        data_mode="replay",
        data_provider="replay",
        contract_multiplier=multiplier,
        replay_path=session.path,
    )


def replay_session_path(name: str) -> Path:
    return Path(replay_session_for_name(name).path)

"""Bundled replay-session catalog for no-credential research workflows."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReplaySession:
    name: str
    path: str
    label: str
    description: str


REPLAY_SESSIONS: tuple[ReplaySession, ...] = (
    ReplaySession(
        name="demo",
        path="sample_data/demo_replay.jsonl",
        label="Compact Demo",
        description="Small seeded fixture used for screenshots and smoke tests.",
    ),
    ReplaySession(
        name="full-session",
        path="sample_data/es_synthetic_full_session.jsonl",
        label="Synthetic Full Session",
        description="Open, mid-session, and late-session ES 0DTE flow.",
    ),
    ReplaySession(
        name="trend-day",
        path="sample_data/es_trend_day.jsonl",
        label="Trend Day",
        description="Uptrend with call-side accumulation and rising spot.",
    ),
    ReplaySession(
        name="chop-day",
        path="sample_data/es_chop_day.jsonl",
        label="Chop Day",
        description="Range-bound session with balanced call and put flow.",
    ),
    ReplaySession(
        name="volatility-spike",
        path="sample_data/es_volatility_spike.jsonl",
        label="Volatility Spike",
        description="Fast downside move with higher IV and put-heavy flow.",
    ),
    ReplaySession(
        name="gap-fade",
        path="sample_data/es_gap_fade.jsonl",
        label="Gap And Fade",
        description="Gap-up open that rejects higher call walls and rotates into put-heavy fade flow.",
    ),
    ReplaySession(
        name="call-wall-breakout",
        path="sample_data/es_call_wall_breakout.jsonl",
        label="Call Wall Breakout",
        description="Upside breakout that walks the call wall higher across the session.",
    ),
    ReplaySession(
        name="zero-gamma-flip",
        path="sample_data/es_zero_gamma_flip.jsonl",
        label="Zero-Gamma Flip",
        description="Flow rotates across the zero-gamma boundary.",
    ),
    ReplaySession(
        name="expiration-compression",
        path="sample_data/es_expiration_compression.jsonl",
        label="Expiration Compression",
        description="Late 0DTE pinning flow around the gamma wall.",
    ),
    ReplaySession(
        name="quality-stress",
        path="sample_data/es_quality_stress.jsonl",
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


def replay_session_path(name: str) -> Path:
    return Path(replay_session_for_name(name).path)

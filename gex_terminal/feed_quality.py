"""Provider feed-quality summaries for the terminal and tests."""

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FeedQualitySnapshot:
    """Serializable health summary for live, replay, and demo feeds."""

    status: str
    data_mode: str
    connection_state: str
    health: str
    message_count: int
    malformed_count: int
    dropped_count: int
    entitlement_error_count: int
    frame_count: int
    parse_error_count: int
    reconnect_count: int
    subscribed_symbol_count: int
    subscription_status: str
    last_message_age_seconds: float | None
    last_snapshot_age_seconds: float | None
    stale_after_seconds: float
    stale: bool
    latency_ms: float
    p95_latency_ms: float
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data


def build_feed_quality_snapshot(
    *,
    status: str,
    data_mode: str,
    connection_state: str,
    message_count: int,
    malformed_count: int,
    dropped_count: int,
    entitlement_error_count: int,
    last_message_age_seconds: float | None,
    last_snapshot_age_seconds: float | None,
    stale_after_seconds: float,
    frame_count: int = 0,
    parse_error_count: int = 0,
    reconnect_count: int = 0,
    subscribed_symbol_count: int = 0,
    subscription_status: str = "unknown",
    latency_ms: float = 0.0,
    p95_latency_ms: float = 0.0,
) -> FeedQualitySnapshot:
    """Build a consistent feed-health snapshot from runtime counters."""
    try:
        stale_threshold = float(stale_after_seconds)
    except (OverflowError, TypeError, ValueError):
        raise ValueError("stale_after_seconds must be numeric") from None
    if not math.isfinite(stale_threshold) or stale_threshold <= 0:
        raise ValueError("stale_after_seconds must be finite and greater than 0")

    stale = status == "STALE" or (
        last_message_age_seconds is not None
        and last_message_age_seconds > stale_threshold
        and data_mode not in {"DEMO"}
    )
    notes: list[str] = []

    if data_mode in {"DEMO", "REPLAY"}:
        notes.append("simulated local feed")
    if stale:
        notes.append("last message exceeded stale threshold")
    if status == "DISCONNECTED":
        notes.append("provider connection is down")
    if entitlement_error_count:
        notes.append("provider entitlement errors recorded")
    if parse_error_count:
        notes.append("provider frame parse errors recorded")
    if malformed_count:
        notes.append("malformed payloads recorded")
    if dropped_count:
        notes.append("unsupported or off-symbol payloads dropped")
    if reconnect_count:
        notes.append("provider reconnects recorded")
    if subscription_status not in {"unknown", "subscribed"}:
        notes.append(f"subscription status: {subscription_status}")
    if not notes:
        notes.append("feed checks clean")

    if status == "DISCONNECTED":
        health = "down"
    elif entitlement_error_count:
        health = "entitlement"
    elif stale:
        health = "stale"
    elif parse_error_count or malformed_count or dropped_count:
        health = "degraded"
    elif data_mode in {"DEMO", "REPLAY"}:
        health = "simulated"
    else:
        health = "healthy"

    return FeedQualitySnapshot(
        status=status,
        data_mode=data_mode,
        connection_state=connection_state,
        health=health,
        message_count=int(message_count),
        malformed_count=int(malformed_count),
        dropped_count=int(dropped_count),
        entitlement_error_count=int(entitlement_error_count),
        frame_count=int(frame_count),
        parse_error_count=int(parse_error_count),
        reconnect_count=int(reconnect_count),
        subscribed_symbol_count=int(subscribed_symbol_count),
        subscription_status=subscription_status,
        last_message_age_seconds=last_message_age_seconds,
        last_snapshot_age_seconds=last_snapshot_age_seconds,
        stale_after_seconds=stale_threshold,
        stale=bool(stale),
        latency_ms=float(latency_ms),
        p95_latency_ms=float(p95_latency_ms),
        notes=tuple(notes),
    )

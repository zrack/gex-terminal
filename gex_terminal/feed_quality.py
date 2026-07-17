"""Provider feed-quality summaries for the terminal and tests."""

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
    latency_ms: float = 0.0,
    p95_latency_ms: float = 0.0,
) -> FeedQualitySnapshot:
    """Build a consistent feed-health snapshot from runtime counters."""
    stale = status == "STALE" or (
        last_message_age_seconds is not None
        and last_message_age_seconds > stale_after_seconds
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
    if malformed_count:
        notes.append("malformed payloads recorded")
    if dropped_count:
        notes.append("unsupported or off-symbol payloads dropped")
    if not notes:
        notes.append("feed checks clean")

    if status == "DISCONNECTED":
        health = "down"
    elif entitlement_error_count:
        health = "entitlement"
    elif stale:
        health = "stale"
    elif malformed_count or dropped_count:
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
        last_message_age_seconds=last_message_age_seconds,
        last_snapshot_age_seconds=last_snapshot_age_seconds,
        stale_after_seconds=float(stale_after_seconds),
        stale=bool(stale),
        latency_ms=float(latency_ms),
        p95_latency_ms=float(p95_latency_ms),
        notes=tuple(notes),
    )

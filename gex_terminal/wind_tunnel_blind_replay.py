"""Point-in-time market input and observed 30-minute outcomes for blind review."""

from datetime import datetime, timedelta

from . import wind_tunnel as wind
from .contracts import market_timestamp_order_key, parse_market_datetime
from .wind_tunnel_saved_investigation import investigate_saved
from .wind_tunnel_saved_replay import SavedReplay


HORIZON_MINUTES = 30
MAX_PRICE_PATH_POINTS = 4096
_FUTURE_SOURCE_FIELDS = {"first_as_of", "last_as_of", "event_count", "later_events_excluded"}
TimeKey = tuple[datetime, int]


def _event_time(message: dict) -> TimeKey:
    key = market_timestamp_order_key(message.get("event_time") or message.get("timestamp"))
    if key is None:
        raise ValueError("Blind review requires an authoritative event time for every update.")
    return key


def _timestamp(key: TimeKey) -> str:
    stamp, remainder = key
    if remainder:
        return f"{stamp:%Y-%m-%dT%H:%M:%S}.{stamp.microsecond:06d}{remainder:03d}Z"
    return wind._time(stamp)


def _seconds(start: TimeKey, end: TimeKey) -> float:
    return (end[0] - start[0]).total_seconds() + (end[1] - start[1]) / 1_000_000_000


def _underlying(message: dict) -> tuple[str, str | None]:
    provider = str(message.get("provider") or "legacy").lower()
    contract_id = message.get("contract_id") if message.get("schema_version", 1) >= 2 else None
    return provider, str(contract_id).strip() if contract_id is not None else None


class _PricePath:
    """Keep small paths exact and bound dense paths using observed extrema."""

    def __init__(self, cutoff: TimeKey, sequence: int, price: float):
        self.cutoff = self.last_time = cutoff
        self.max_gap = 0.0
        self.observed = 0
        self.anchor = {"as_of": _timestamp(cutoff), "sequence": sequence, "price": price}
        self.points = [self.anchor]
        self.minutes = {}

    def add(self, as_of: TimeKey, sequence: int, price: float) -> None:
        self.observed += 1
        self.max_gap = max(self.max_gap, _seconds(self.last_time, as_of))
        self.last_time = max(self.last_time, as_of)
        point = {"as_of": _timestamp(as_of), "sequence": sequence, "price": price}
        if len(self.points) < MAX_PRICE_PATH_POINTS:
            self.points.append(point)

        minute = int(_seconds(self.cutoff, as_of) // 60)
        first, low, high, _ = self.minutes.get(minute, (point,) * 4)
        self.minutes[minute] = (first, point if price < low["price"] else low,
                                point if price > high["price"] else high, point)

    def output(self) -> tuple[list[dict], str]:
        if self.observed + 1 <= MAX_PRICE_PATH_POINTS:
            return self.points, "all_matching_updates"
        points = {point["sequence"]: point for minute in self.minutes.values() for point in minute}
        return [self.anchor, *(points[sequence] for sequence in sorted(points))], "observed_minute_extrema"


async def _first_flip(replay: SavedReplay) -> int:
    """Search in capture order and stop without evaluating a later update."""
    consumer = replay._consumer()
    previous_sign = None
    offset = replay._first_offset
    async with consumer.offline_projection_batch():
        for sequence in range(replay._metadata["event_count"]):
            event, offset = replay._event(offset)
            if not await replay._apply(consumer, event):
                continue
            point = await replay._point(consumer, sequence, sequence, offset)
            if previous_sign and point.sign == -previous_sign:
                return sequence
            previous_sign = point.sign
    raise ValueError(f"The saved {replay.symbol} capture has no reproducible net-GEX flip.")


async def select_flip(replay: SavedReplay, sequence: int | None = None) -> dict:
    """Expose a verified flip and remove metadata computed from later events."""
    if sequence is not None and (type(sequence) is not int or sequence < 1):
        raise ValueError(f"Choose the sequence of a saved {replay.symbol} flip.")

    async with replay._lock:
        await replay._prepare()
        if sequence is None:
            sequence = await _first_flip(replay)

    report = await investigate_saved({"capture_sha256": replay.capture_sha256, "sequence": sequence,
                                      "remove_update": True}, replay)
    for point in (report, report["before"], report["after"], report["counterfactual"]):
        if point is not None:
            for field in _FUTURE_SOURCE_FIELDS:
                point["source"].pop(field, None)
    report.pop("result_sha256")
    report["result_sha256"] = wind._sha(report)
    return report


async def reveal_outcome(replay: SavedReplay, sequence: int, cutoff_as_of: str) -> dict:
    """Evaluate the original observed branch at the cutoff plus 30 minutes."""
    cutoff = parse_market_datetime(cutoff_as_of)
    if type(sequence) is not int or sequence < 1 or cutoff is None:
        raise ValueError(f"Choose the exact cutoff of a saved {replay.symbol} flip.")

    async with replay._lock:
        await replay._prepare()
        count = replay._metadata["event_count"]
        if sequence >= count:
            raise ValueError("The blind review flip is outside the saved capture.")
        consumer = replay._consumer()
        offset = replay._first_offset
        last_accepted = last_quote = None
        accepted_sequence = None
        original_underlying = None
        matched_underlying = True
        reached_target = False
        excluded_prices = 0
        async with consumer.offline_projection_batch():
            for _ in range(sequence + 1):
                event, offset = replay._event(offset)
                if not await replay._apply(consumer, event):
                    continue
                message = event["message"]
                key = _event_time(message)
                last_accepted = key if last_accepted is None else max(last_accepted, key)
                accepted_sequence = event["sequence"]
                if message["type"] == "underlying_tick":
                    original_underlying = _underlying(message)
                    last_quote = key

            if (accepted_sequence != sequence or last_accepted is None or last_accepted[0] != cutoff
                    or original_underlying is None):
                raise ValueError("The saved capture did not match the committed flip cutoff.")

            anchor = last_accepted
            target = (cutoff + timedelta(minutes=HORIZON_MINUTES), anchor[1])
            price_path = _PricePath(anchor, sequence, consumer.current_spot)
            for _ in range(sequence + 1, count):
                event, offset = replay._event(offset)
                message = event["message"]
                key = _event_time(message)
                if key >= target:
                    reached_target = True
                if key > target:
                    # A later capture entry can carry an earlier market time.
                    # Stop at this boundary so it cannot enter the reviewed prefix.
                    break
                if message["type"] == "underlying_tick" and key < max(anchor, last_quote):
                    # A stale quote must not update the spot used to value the
                    # horizon even when the consumer can accept its payload.
                    excluded_prices += 1
                    continue
                if not await replay._apply(consumer, event):
                    continue
                last_accepted = max(last_accepted, key)
                accepted_sequence = event["sequence"]
                if message["type"] != "underlying_tick":
                    continue
                if _underlying(message) != original_underlying:
                    matched_underlying = False
                    excluded_prices += 1
                    continue
                last_quote = key
                price_path.add(key, accepted_sequence, consumer.current_spot)

            status = "unavailable"
            reason = None
            summary = pricing_coverage = valuation_as_of = None
            if not reached_target:
                reason = "The saved capture ends before the 30-minute target."
            elif not matched_underlying:
                reason = "The underlying futures identity changed before the 30-minute target."
            else:
                frozen = await consumer.capture_wind_tunnel_state()
                rows = tuple(sorted(frozen["rows"], key=lambda row: (row["provider"], row["contract_id"], row["position_source"])))
                checkpoint = wind._Checkpoint({}, frozen["spot"], frozen["as_of"], rows,
                                               frozen["calculation_mode"], replay._multiplier)
                advance = (target[0] - frozen["as_of"]).total_seconds() / 60
                state = wind._state(checkpoint, {**replay._settings, "time_advance": advance}, details=False)
                pricing_coverage = state.get("pricing_coverage")
                if state["summary"] is None:
                    reason = state.get("reason") or "There is no usable linked exposure at the target."
                else:
                    status = "available"
                    valuation_as_of = _timestamp(target)
                    summary = {field: state["summary"][field] for field in
                               ("total_net_gex", "net_sign", "gamma_wall", "units")}

    points, sampling = price_path.output()
    observed_end = target if reached_target else last_accepted
    return {
        "horizon_minutes": HORIZON_MINUTES,
        "target_as_of": _timestamp(target), "as_of": _timestamp(last_accepted),
        "valuation_as_of": valuation_as_of, "status": status, "reason": reason, "summary": summary,
        "price_path": points, "pricing_coverage": pricing_coverage,
        "coverage": {
            "capture_reaches_target": reached_target, "last_accepted_sequence": accepted_sequence,
            "checkpoint_age_seconds": _seconds(last_accepted, target),
            "last_price_as_of": _timestamp(last_quote), "price_age_seconds": _seconds(last_quote, target),
            "observed_price_count": price_path.observed, "shown_price_points": len(points),
            "price_sampling": sampling, "excluded_prices": excluded_prices,
            "largest_price_gap_seconds": max(price_path.max_gap, _seconds(price_path.last_time, observed_end)),
            "underlying_provider": original_underlying[0], "underlying_contract_id": original_underlying[1],
            "same_underlying": matched_underlying,
        },
    }

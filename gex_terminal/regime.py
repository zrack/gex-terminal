"""Live gamma-regime classification from computed GEX snapshots."""

from statistics import median
from typing import Any, Dict


def build_regime_map(data: Dict[str, Any], spot: float) -> Dict[str, Any]:
    """Summarize the current gamma regime and nearby structural triggers."""
    total_net = float(data["total_net_gex"])
    zero = float(data["zero_gamma_strike"])
    wall = float(data["gamma_wall_strike"])
    call_wall = float(data.get("call_wall_strike", wall))
    put_wall = float(data.get("put_wall_strike", wall))
    strikes = sorted(float(strike) for strike in data.get("strikes", []))
    proximity = _proximity_threshold(strikes, float(spot))

    near_zero = abs(float(spot) - zero) <= proximity
    near_wall = abs(float(spot) - wall) <= proximity
    primary = "positive_gamma" if total_net >= 0 else "negative_gamma"

    if near_zero:
        state = "transition"
        label = "TRANSITION"
        color = "#38bdf8"
        description = "Spot is near the zero-gamma boundary."
    elif near_wall:
        state = "pinned"
        label = "PINNED"
        color = "#f59e0b"
        description = "Spot is near the dominant gamma wall."
    elif primary == "positive_gamma":
        state = "positive_gamma"
        label = "POSITIVE GAMMA"
        color = "#22c55e"
        description = "Net gamma is positive; modeled hedging pressure may dampen movement."
    else:
        state = "negative_gamma"
        label = "NEGATIVE GAMMA"
        color = "#ef4444"
        description = "Net gamma is negative; modeled hedging pressure may amplify movement."

    return {
        "primary_regime": primary,
        "state": state,
        "label": label,
        "color": color,
        "description": description,
        "spot": float(spot),
        "zero_gamma": zero,
        "gamma_wall": wall,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "proximity_threshold": proximity,
        "distance_to_zero": zero - float(spot),
        "distance_to_wall": wall - float(spot),
        "next_trigger": _next_trigger(
            spot=float(spot),
            levels={
                "zero_gamma": zero,
                "gamma_wall": wall,
                "call_wall": call_wall,
                "put_wall": put_wall,
            },
        ),
        "zones": _zones(strikes=strikes, zero=zero, wall=wall, proximity=proximity),
    }


def _proximity_threshold(strikes: list[float], spot: float) -> float:
    if len(strikes) >= 2:
        gaps = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
        if gaps:
            return max(1.0, median(gaps) * 0.4)
    return max(1.0, abs(spot) * 0.0015)


def _next_trigger(*, spot: float, levels: Dict[str, float]) -> Dict[str, Any]:
    labels = {
        "zero_gamma": "Zero Gamma",
        "gamma_wall": "Gamma Wall",
        "call_wall": "Call Wall",
        "put_wall": "Put Wall",
    }
    name, price = min(levels.items(), key=lambda item: abs(float(item[1]) - spot))
    distance = float(price) - spot
    return {
        "name": name,
        "label": labels[name],
        "price": float(price),
        "distance": distance,
        "side": "above" if distance >= 0 else "below",
    }


def _zones(*, strikes: list[float], zero: float, wall: float, proximity: float) -> list[Dict[str, Any]]:
    low = min(strikes) if strikes else zero - proximity
    high = max(strikes) if strikes else zero + proximity
    return [
        {
            "name": "negative_gamma_zone",
            "label": "-GEX Expansion Zone",
            "low": float(low),
            "high": float(zero),
        },
        {
            "name": "transition_zone",
            "label": "Zero-Gamma Transition",
            "low": float(zero - proximity),
            "high": float(zero + proximity),
        },
        {
            "name": "positive_gamma_zone",
            "label": "+GEX Pinning Zone",
            "low": float(zero),
            "high": float(high),
        },
        {
            "name": "wall_pin_zone",
            "label": "Wall Pin Zone",
            "low": float(wall - proximity),
            "high": float(wall + proximity),
        },
    ]

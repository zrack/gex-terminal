"""GEX-proxy classification from computed snapshots."""

from statistics import median
from typing import Any, Dict


def build_regime_map(data: Dict[str, Any], spot: float) -> Dict[str, Any]:
    """Summarize the selected GEX proxy and nearby structural levels."""
    total_net = float(data["total_net_gex"])
    zero = float(data["zero_gamma_strike"])
    wall = float(data["gamma_wall_strike"])
    call_wall = float(data.get("call_wall_strike", wall))
    put_wall = float(data.get("put_wall_strike", wall))
    strikes = sorted(float(strike) for strike in data.get("strikes", []))
    proximity = _proximity_threshold(strikes, float(spot))

    near_zero = abs(float(spot) - zero) <= proximity
    near_wall = abs(float(spot) - wall) <= proximity
    primary = "positive_gex_proxy" if total_net >= 0 else "negative_gex_proxy"

    if near_zero:
        state = "transition"
        label = "COMPATIBILITY PROXIMITY"
        color = "#38bdf8"
        description = "Spot is near the historical strike-profile compatibility level."
    elif near_wall:
        state = "wall_proximity"
        label = "WALL PROXIMITY"
        color = "#f59e0b"
        description = "Spot is near the dominant gamma wall."
    elif primary == "positive_gex_proxy":
        state = "positive_gex_proxy"
        label = "POSITIVE GEX PROXY"
        color = "#22c55e"
        description = "The selected position quantities produce positive modeled net GEX."
    else:
        state = "negative_gex_proxy"
        label = "NEGATIVE GEX PROXY"
        color = "#ef4444"
        description = "The selected position quantities produce negative modeled net GEX."

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
        "zero_gamma": "Compatibility Level",
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
            "name": "negative_gex_proxy_zone",
            "label": "Negative GEX Proxy",
            "low": float(low),
            "high": float(zero),
        },
        {
            "name": "compatibility_transition",
            "label": "Compatibility Proximity",
            "low": float(zero - proximity),
            "high": float(zero + proximity),
        },
        {
            "name": "positive_gex_proxy_zone",
            "label": "Positive GEX Proxy",
            "low": float(zero),
            "high": float(high),
        },
        {
            "name": "wall_proximity_zone",
            "label": "Gamma-Wall Proximity",
            "low": float(wall - proximity),
            "high": float(wall + proximity),
        },
    ]

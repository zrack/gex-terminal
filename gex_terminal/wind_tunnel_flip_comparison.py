"""Compare two independently reconstructed saved-session net-GEX flips."""

import hashlib
from importlib.resources import files
from typing import Any, Mapping

from . import wind_tunnel as wind
from . import wind_tunnel_saved_investigation as saved


OPERATION = "compare-saved-flips"
MARKETS = ("ES", "NQ")


class FlipComparisonError(ValueError):
    """A path-free input error for the local comparison interface."""


def calculation_identity() -> dict:
    identity = saved.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_flip_comparison.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def normalize_request(request: Mapping[str, Any]) -> dict:
    if (not isinstance(request, Mapping) or set(request) - {"schema", "operation", "es", "nq"}
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise FlipComparisonError("Choose one saved ES flip and one saved NQ flip.")

    result = {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION}
    for symbol in MARKETS:
        selection = request.get(symbol.lower())
        fields = {"capture_sha256", "sequence"}
        if not isinstance(selection, Mapping) or set(selection) != fields:
            raise FlipComparisonError(f"Choose an exact flip from the saved {symbol} capture.")
        try:
            saved._request(selection, symbol)
        except ValueError as exc:
            raise FlipComparisonError(f"Invalid saved {symbol} capture identity or event sequence.") from exc
        result[symbol.lower()] = dict(selection)

    if result["es"]["capture_sha256"] == result["nq"]["capture_sha256"]:
        raise FlipComparisonError("ES and NQ must have distinct saved capture identities.")
    return result


async def compare_saved_flips(request: Mapping[str, Any], replays=None) -> dict:
    normalized = normalize_request(request)
    replays = replays or {}
    for symbol in MARKETS:
        replay = replays.get(symbol)
        checksum = normalized[symbol.lower()]["capture_sha256"]
        if (replay is None or replay.symbol != symbol
                or (replay.capture_sha256 is not None and replay.capture_sha256 != checksum)):
            raise FlipComparisonError(f"Open the original saved {symbol} capture to compare these flips.")

    for symbol in MARKETS:
        try:
            await replays[symbol].verify_capture(normalized[symbol.lower()]["capture_sha256"])
        except (ValueError, OSError) as exc:
            raise FlipComparisonError(f"The saved {symbol} capture could not be verified for this comparison.") from exc

    sides = {}
    for symbol in MARKETS:
        key = symbol.lower()
        try:
            sides[key] = await saved.investigate_saved({**normalized[key], "remove_update": True}, replays[symbol])
        except (ValueError, OSError) as exc:
            raise FlipComparisonError(f"The selected {symbol} update could not reproduce a saved flip.") from exc

    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{OPERATION}.v1", "version": wind.VERSION,
        "request": normalized, "request_sha256": wind._sha(normalized),
        "calculation": identity, "calculation_fingerprint": wind._sha(identity), **sides,
        "limitations": {
            "predictive_validity": "unmeasured", "future_events_used": False,
            "interpretation": "Each side shows its own priced exposure and same-cutoff removal result.",
            "reproduction": "Requires both original captures and a compatible calculation build.",
        },
    }
    result["result_sha256"] = wind._sha(result)
    return result

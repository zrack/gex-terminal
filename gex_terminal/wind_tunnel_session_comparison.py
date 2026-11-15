"""Compare two exact flips from distinct saved capture identities."""

import hashlib
from importlib.resources import files
from typing import Any, Mapping

from . import wind_tunnel as wind
from . import wind_tunnel_saved_investigation as saved
from .wind_tunnel_flip_comparison import FlipComparisonError


OPERATION = "compare-saved-sessions"
SIDES = {"left": "Session A", "right": "Session B"}


def calculation_identity() -> dict:
    identity = saved.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_session_comparison.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def normalize_request(request: Mapping[str, Any]) -> dict:
    if (not isinstance(request, Mapping) or set(request) - {"schema", "operation", *SIDES}
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise FlipComparisonError("Choose two flips from different saved sessions.")

    normalized = {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION}
    for side, label in SIDES.items():
        selection = request.get(side)
        if not isinstance(selection, Mapping) or set(selection) != {"symbol", "capture_sha256", "sequence"}:
            raise FlipComparisonError(f"Choose an exact saved flip for {label}.")
        symbol = selection["symbol"]
        if symbol not in ("ES", "NQ"):
            raise FlipComparisonError(f"Choose an ES or NQ capture for {label}.")
        try:
            saved._request({key: selection[key] for key in ("capture_sha256", "sequence")}, symbol)
        except ValueError as exc:
            raise FlipComparisonError(f"Invalid capture identity or event sequence for {label}.") from exc
        normalized[side] = dict(selection)

    if normalized["left"]["capture_sha256"] == normalized["right"]["capture_sha256"]:
        raise FlipComparisonError("Choose two different saved captures.")
    return normalized


async def compare_saved_sessions(request: Mapping[str, Any], replays=None) -> dict:
    normalized = normalize_request(request)
    replays = replays or {}
    for side, label in SIDES.items():
        replay = replays.get(side)
        selection = normalized[side]
        if (replay is None or replay.symbol != selection["symbol"]
                or replay.capture_sha256 not in (None, selection["capture_sha256"])):
            raise FlipComparisonError(f"Open the original saved capture for {label}.")

    for side, label in SIDES.items():
        try:
            await replays[side].verify_capture(normalized[side]["capture_sha256"])
        except (ValueError, OSError) as exc:
            raise FlipComparisonError(f"The saved capture for {label} could not be verified.") from exc

    sides = {}
    for side, label in SIDES.items():
        selection = normalized[side]
        replay_request = {"capture_sha256": selection["capture_sha256"], "sequence": selection["sequence"],
                          "remove_update": True}
        try:
            sides[side] = await saved.investigate_saved(replay_request, replays[side])
        except (ValueError, OSError) as exc:
            raise FlipComparisonError(f"The selected update for {label} could not reproduce a saved flip.") from exc

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

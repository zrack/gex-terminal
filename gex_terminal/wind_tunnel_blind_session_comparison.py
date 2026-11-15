"""Reproduce two committed reviews from different captures of the same market."""

import hashlib
from importlib.resources import files
from typing import Any, Mapping

from . import wind_tunnel as wind
from . import wind_tunnel_blind_review as blind
from .wind_tunnel_saved_receipt_compat import matches_es_only_build, with_recorded_identity


OPERATION = "blind-session-comparison"
SIDES = ("left", "right")


def calculation_identity() -> dict:
    identity = blind.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_blind_session_comparison.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def normalize_request(request: Mapping[str, Any]) -> dict:
    if (not isinstance(request, Mapping) or set(request) - {"schema", "operation", *SIDES}
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise blind.BlindReviewError("Choose two independently committed reviews from saved sessions.")
    normalized = {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION}
    for side in SIDES:
        entry = request.get(side)
        if (not isinstance(entry, Mapping) or set(entry) != {"symbol", "review"}
                or entry["symbol"] not in ("ES", "NQ")):
            raise blind.BlindReviewError("Each review requires a saved ES or NQ capture.")
        symbol = entry["symbol"]
        normalized[side] = {"symbol": symbol, "review": blind.normalize_request(entry["review"], symbol)}
    left, right = (normalized[side] for side in SIDES)
    if left["symbol"] != right["symbol"] or left["review"]["capture_sha256"] == right["review"]["capture_sha256"]:
        raise blind.BlindReviewError("Choose two distinct saved sessions of the same market.")
    return normalized


def capture_slots(request: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    selection = normalize_request(request)
    return {(selection[side]["symbol"], selection[side]["review"]["capture_sha256"]): side for side in SIDES}


def assemble_result(left: dict, right: dict) -> dict:
    sides = {"left": left, "right": right}
    selection = {side: {"symbol": result["flip"]["source"]["symbol"], "review": result["request"]}
                 for side, result in sides.items()}
    request = normalize_request(selection)
    child_identity = blind.calculation_identity()
    for side, result in sides.items():
        if result["calculation"] == child_identity:
            continue
        if (selection[side]["symbol"] != "ES"
                or not matches_es_only_build(blind.OPERATION, result["calculation"], child_identity)):
            raise blind.BlindReviewError("A review uses an incompatible calculation build.")
        sides[side] = with_recorded_identity(result, child_identity)
    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{OPERATION}.v1", "version": wind.VERSION,
        "request": request, "request_sha256": wind._sha(request),
        "calculation": identity, "calculation_fingerprint": wind._sha(identity), **sides,
        "limitations": {
            "predictive_validity": "unmeasured", "horizon_minutes": 30,
            "reproduction": "Requires both original captures and a compatible calculation build.",
        },
    }
    result["result_sha256"] = wind._sha(result)
    return result


async def blind_session_comparison(request: Mapping[str, Any], replays=None) -> dict:
    selection = normalize_request(request)
    replays = replays or {}
    for side in SIDES:
        replay = replays.get(side)
        label = "Session A" if side == "left" else "Session B"
        if replay is None or replay.symbol != selection[side]["symbol"]:
            raise blind.BlindReviewError(f"Open the original saved capture for {label}.")
        try:
            await replay.verify_capture(selection[side]["review"]["capture_sha256"])
        except (ValueError, OSError) as exc:
            raise blind.BlindReviewError(f"The original saved capture for {label} could not be verified.") from exc
    left = await blind.blind_review(selection["left"]["review"], replays["left"])
    right = await blind.blind_review(selection["right"]["review"], replays["right"])
    return assemble_result(left, right)

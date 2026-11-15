"""Reproduce two independently committed saved reviews as one comparison."""

import hashlib
from importlib.resources import files
from typing import Any, Mapping

from . import wind_tunnel as wind
from . import wind_tunnel_blind_review as blind
from .wind_tunnel_saved_receipt_compat import matches_es_only_build, with_recorded_identity


OPERATION = "blind-comparison"
MARKETS = ("ES", "NQ")


def calculation_identity() -> dict:
    identity = blind.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_blind_comparison.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def normalize_request(request: Mapping[str, Any]) -> dict:
    if (not isinstance(request, Mapping) or set(request) - {"schema", "operation", "es", "nq"}
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise blind.BlindReviewError("Choose independently committed ES and NQ reviews.")
    es = blind.normalize_request(request.get("es"), "ES")
    nq = blind.normalize_request(request.get("nq"), "NQ")
    if es["capture_sha256"] == nq["capture_sha256"]:
        raise blind.BlindReviewError("The comparison requires distinct ES and NQ captures.")
    return {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION, "es": es, "nq": nq}


def assemble_result(es: dict, nq: dict) -> dict:
    """Combine two authoritative, already revealed individual results."""
    request = normalize_request({"es": es["request"], "nq": nq["request"]})
    child_identity = blind.calculation_identity()
    if es["calculation"] != child_identity:
        # A standalone ES receipt can already have verified byte for byte with
        # the original ES-only proof. The pair uses the current proof for both.
        if not matches_es_only_build(blind.OPERATION, es["calculation"], child_identity):
            raise blind.BlindReviewError("The ES review uses an incompatible calculation build.")
        es = with_recorded_identity(es, child_identity)
    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{OPERATION}.v1", "version": wind.VERSION,
        "request": request, "request_sha256": wind._sha(request),
        "calculation": identity, "calculation_fingerprint": wind._sha(identity),
        "es": es, "nq": nq,
        "limitations": {
            "predictive_validity": "unmeasured", "horizon_minutes": 30,
            "reproduction": "Requires both original captures and a compatible calculation build.",
        },
    }
    result["result_sha256"] = wind._sha(result)
    return result


async def blind_comparison(request: Mapping[str, Any], replays=None) -> dict:
    normalized = normalize_request(request)
    replays = replays or {}
    for symbol in MARKETS:
        replay = replays.get(symbol)
        if replay is None or replay.symbol != symbol:
            raise blind.BlindReviewError(f"Open the original saved {symbol} capture to reproduce this comparison.")
        try:
            await replay.verify_capture(normalized[symbol.lower()]["capture_sha256"])
        except (ValueError, OSError) as exc:
            raise blind.BlindReviewError(f"The original saved {symbol} capture could not be verified for this comparison.") from exc
    es = await blind.blind_review(normalized["es"], replays["ES"])
    nq = await blind.blind_review(normalized["nq"], replays["NQ"])
    return assemble_result(es, nq)

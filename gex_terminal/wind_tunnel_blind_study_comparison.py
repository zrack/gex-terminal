"""Combine completed ES and NQ blind studies in one reproducible receipt."""

from collections.abc import Mapping
import hashlib
from importlib.resources import files
from pathlib import Path

from . import wind_tunnel as wind
from . import wind_tunnel_blind_saved_study as saved
from .wind_tunnel_blind_replay import HORIZON_MINUTES
from .wind_tunnel_blind_study import BlindStudyError
from .wind_tunnel_saved_receipt_compat import matches_es_only_build, with_recorded_identity


OPERATION = "blind-study-comparison"
MARKETS = ("ES", "NQ")
_CHILD_SCHEMA = f"gex-terminal.wind-tunnel.{saved.OPERATION}.v1"


def calculation_identity() -> dict:
    identity = saved.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_blind_study_comparison.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def _normalize(request: Mapping) -> tuple[dict, dict[str, list[str]]]:
    if (not isinstance(request, Mapping) or set(request) - {"schema", "operation", "es", "nq"}
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise BlindStudyError("Choose completed saved ES and NQ studies.")
    normalized = {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION}
    captures = {}
    for symbol in MARKETS:
        side = symbol.lower()
        child = request.get(side)
        if saved.capture_market(child) != symbol:
            raise BlindStudyError(f"The comparison requires the saved {symbol} study in its own slot.")
        captures[symbol] = saved.capture_ids(child)
        normalized[side] = dict(child)
    if set(captures["ES"]).intersection(captures["NQ"]):
        raise BlindStudyError("The comparison requires distinct saved ES and NQ captures.")
    return normalized, captures


def normalize_request(request: Mapping) -> dict:
    """Check the two protocols and their ordered capture bindings."""
    return _normalize(request)[0]


def assemble_result(es: dict, nq: dict) -> dict:
    """Combine two authoritative results that have already been revealed."""
    sides = {"es": es, "nq": nq}
    if any(not isinstance(child, dict) or child.get("schema") != _CHILD_SCHEMA for child in sides.values()):
        raise BlindStudyError("Complete both saved studies before comparing them.")
    request = normalize_request({side: child.get("request") for side, child in sides.items()})
    child_identity = saved.calculation_identity()
    for side, child in sides.items():
        recorded = child.get("calculation")
        if recorded == child_identity:
            continue
        # A legacy ES result can already have reproduced in its original
        # format. Use the current proof so the pair reproduces from its request.
        if side != "es" or not matches_es_only_build(saved.OPERATION, recorded, child_identity):
            raise BlindStudyError(f"The {side.upper()} study uses an incompatible calculation build.")
        sides[side] = with_recorded_identity(child, child_identity)
    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{OPERATION}.v1", "version": wind.VERSION,
        "request": request, "request_sha256": wind._sha(request),
        "calculation": identity, "calculation_fingerprint": wind._sha(identity), **sides,
        "limitations": {
            "predictive_validity": "unmeasured", "horizon_minutes": HORIZON_MINUTES,
            "reproduction": "Requires every original ES and NQ study capture and a compatible calculation build.",
        },
    }
    result["result_sha256"] = wind._sha(result)
    return result


async def blind_study_comparison(request: Mapping, captures: Mapping[str, Mapping[str, Path]]) -> dict:
    """Reproduce both saved studies with their original market and case order."""
    normalized, expected = _normalize(request)
    if not isinstance(captures, Mapping) or set(captures) != set(MARKETS):
        raise BlindStudyError("Supply the original saved ES and NQ study captures.")
    for symbol in MARKETS:
        sources = captures[symbol]
        if not isinstance(sources, Mapping) or set(sources) != set(expected[symbol]):
            raise BlindStudyError(f"Supply the exact saved {symbol} capture set from the comparison receipt.")
    es = await saved.blind_saved_study(normalized["es"], captures["ES"])
    nq = await saved.blind_saved_study(normalized["nq"], captures["NQ"])
    return assemble_result(es, nq)

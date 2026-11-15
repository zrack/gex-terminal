"""Reproduce two independently submitted studies from their saved captures."""

from collections.abc import Mapping
import hashlib
from importlib.resources import files
from pathlib import Path

from . import wind_tunnel as wind
from . import wind_tunnel_blind_saved_study as saved
from .wind_tunnel_blind_replay import HORIZON_MINUTES
from .wind_tunnel_blind_study import BlindStudyError
from .wind_tunnel_saved_receipt_compat import matches_es_only_build, with_recorded_identity


OPERATION = "blind-saved-study-comparison"
SIDES = ("a", "b")
_CHILD_SCHEMA = f"gex-terminal.wind-tunnel.{saved.OPERATION}.v1"


def calculation_identity() -> dict:
    identity = saved.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_blind_saved_study_comparison.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def _normalize(request: Mapping) -> tuple[dict, dict[str, list[str]]]:
    if (not isinstance(request, Mapping) or set(request) - {"schema", "operation", *SIDES}
            or request.get("schema", wind.REQUEST_SCHEMA) != wind.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION):
        raise BlindStudyError("Choose two saved studies for the comparison.")
    normalized = {"schema": wind.REQUEST_SCHEMA, "operation": OPERATION}
    captures = {}
    for side in SIDES:
        child = request.get(side)
        captures[side] = saved.capture_ids(child)
        normalized[side] = dict(child)
    if not set(captures["a"]).isdisjoint(captures["b"]):
        raise BlindStudyError("Choose separate captures for Study A and Study B so each stays blind.")
    return normalized, captures


def normalize_request(request: Mapping) -> dict:
    """Check both protocols and their ordered capture bindings."""
    return _normalize(request)[0]


def assemble_result(a: dict, b: dict) -> dict:
    """Combine two authoritative results after both studies reveal."""
    sides = {"a": a, "b": b}
    if any(not isinstance(child, dict) or child.get("schema") != _CHILD_SCHEMA for child in sides.values()):
        raise BlindStudyError("Complete both saved studies before comparing them.")
    request = normalize_request({side: child.get("request") for side, child in sides.items()})
    child_identity = saved.calculation_identity()
    for side, child in sides.items():
        recorded = child.get("calculation")
        if recorded == child_identity:
            continue
        if (saved.capture_market(request[side]) != "ES"
                or not matches_es_only_build(saved.OPERATION, recorded, child_identity)):
            raise BlindStudyError(f"Study {side.upper()} uses an incompatible calculation build.")
        # A verified legacy ES result uses the current proof in a new receipt.
        sides[side] = with_recorded_identity(child, child_identity)
    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{OPERATION}.v1", "version": wind.VERSION,
        "request": request, "request_sha256": wind._sha(request),
        "calculation": identity, "calculation_fingerprint": wind._sha(identity), **sides,
        "limitations": {
            "predictive_validity": "unmeasured", "horizon_minutes": HORIZON_MINUTES,
            "reproduction": "Requires the original captures for each study and a compatible calculation build.",
        },
    }
    result["result_sha256"] = wind._sha(result)
    return result


async def blind_saved_study_comparison(request: Mapping, captures: Mapping[str, Mapping[str, Path]]) -> dict:
    """Reproduce both saved studies with their original sides and case orders."""
    normalized, expected = _normalize(request)
    if not isinstance(captures, Mapping) or set(captures) != set(SIDES):
        raise BlindStudyError("Supply the original captures for both Study A and Study B.")
    for side in SIDES:
        sources = captures[side]
        if not isinstance(sources, Mapping) or set(sources) != set(expected[side]):
            raise BlindStudyError(f"Supply the exact capture set for Study {side.upper()} from the comparison receipt.")
    a = await saved.blind_saved_study(normalized["a"], captures["a"])
    b = await saved.blind_saved_study(normalized["b"], captures["b"])
    return assemble_result(a, b)

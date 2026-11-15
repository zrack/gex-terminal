"""Reproduce and attribute a net-GEX sign change in a local saved capture."""

import hashlib
from importlib.resources import files
import math
import re
from typing import Any, Mapping

from . import wind_tunnel
from .pricing_assumptions import is_priced_contract
from .session_capture import LOCAL_CAPTURE_MAX_EVENTS


SAVED_INVESTIGATION_OPERATIONS = {"ES": "investigate-saved", "NQ": "investigate-saved-nq"}


def calculation_identity() -> dict:
    identity = wind_tunnel.calculation_identity()
    for name in ("wind_tunnel_saved_investigation.py", "wind_tunnel_saved_replay.py",
                 "saved_workspace.py", "session_capture.py"):
        module = files("gex_terminal").joinpath(name)
        identity["implementation"][name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def _request(request: Mapping[str, Any], symbol: str) -> dict:
    operation = SAVED_INVESTIGATION_OPERATIONS[symbol]
    if not isinstance(request, Mapping) or set(request) - {
        "schema", "operation", "capture_sha256", "sequence", "remove_update",
    }:
        raise ValueError(f"Expected a bounded saved {symbol} investigation request")
    capture = request.get("capture_sha256")
    sequence = request.get("sequence")
    remove = request.get("remove_update", False)
    if (request.get("schema", wind_tunnel.REQUEST_SCHEMA) != wind_tunnel.REQUEST_SCHEMA
            or request.get("operation", operation) != operation
            or not isinstance(capture, str) or not re.fullmatch(r"[0-9a-f]{64}", capture)
            or type(sequence) is not int or not 1 <= sequence < LOCAL_CAPTURE_MAX_EVENTS
            or type(remove) is not bool):
        raise ValueError(f"Choose an {symbol} capture and a valid flip sequence")
    return {"schema": wind_tunnel.REQUEST_SCHEMA, "operation": operation,
            "capture_sha256": capture, "sequence": sequence, "remove_update": remove}


def _point(state: dict, source: dict) -> dict:
    summary = state["summary"]
    return {"as_of": state["as_of"], "spot": state["spot"], "source": source,
            "summary": {field: summary[field] for field in ("total_net_gex", "net_sign", "gamma_wall", "units")},
            "pricing_coverage": state.get("pricing_coverage")}


def _priced_rows(checkpoint, state: dict) -> dict:
    priced = {(row["provider"], row["contract_id"]): row for row in state["contracts"]}
    unpriced = {(row["contract_id"], row["position_source"]) for row in state["excluded_contracts"]
                if row["reason"] == "iv_unavailable"}
    selected = {}
    for raw in checkpoint.rows:
        if not raw.get("terminal_selected"):
            continue
        key = (raw["provider"], raw["contract_id"])
        included = priced.get(key)
        # An unpriced contract has a known selected quantity. Its GEX is
        # unavailable, while its contribution to the priced total is absent.
        if included is not None:
            selected[key] = {**included, "status": "included"}
        elif not is_priced_contract(raw) and (raw["contract_id"], raw["position_source"]) in unpriced:
            selected[key] = {**raw, "quantity": float(raw["accumulated_volume"]),
                             "net_gex": None, "status": "unpriced"}
    return selected


def _contributions(before: dict, after: dict, alternative: dict | None) -> list[dict]:
    missing = {"quantity": 0.0, "net_gex": 0.0, "status": "not_selected", "position_source": None}
    changed = []
    for key in before.keys() | after.keys():
        left, right = before.get(key, missing), after.get(key, missing)
        if all(left[field] == right[field] for field in missing):
            continue
        row = after.get(key) or before[key]
        branch = alternative.get(key, missing) if alternative is not None else {}
        changed.append({
            "provider": key[0], "contract_id": key[1], "strike": row["strike"],
            "option_type": row["option_type"], "expiry": row.get("expiry"),
            "expiry_timestamp": row.get("expiry_timestamp"), "position_source": row.get("position_source"),
            "before_position_source": left["position_source"], "after_position_source": right["position_source"],
            "before_status": left["status"], "after_status": right["status"],
            "before_quantity": left["quantity"], "after_quantity": right["quantity"],
            "before_gex": left["net_gex"], "after_gex": right["net_gex"],
            "delta_gex": (right["net_gex"] or 0.0) - (left["net_gex"] or 0.0),
            "counterfactual_quantity": branch.get("quantity"), "counterfactual_gex": branch.get("net_gex"),
            "counterfactual_status": branch.get("status"),
        })
    return sorted(changed, key=lambda row: (-abs(row["delta_gex"]), row["provider"], row["contract_id"]))


async def investigate_saved(request: Mapping[str, Any], replay) -> dict:
    normalized = _request(request, replay.symbol)
    if replay.capture_sha256 is not None and normalized["capture_sha256"] != replay.capture_sha256:
        raise ValueError(f"Open the original saved {replay.symbol} capture to reproduce this investigation")
    inputs = await replay.investigation(normalized["sequence"], normalized["remove_update"])
    if normalized["capture_sha256"] != replay.capture_sha256:
        raise ValueError(f"Open the original saved {replay.symbol} capture to reproduce this investigation")

    settings = inputs["model_request"]
    before_checkpoint, after_checkpoint = inputs["before"], inputs["after"]
    cache = wind_tunnel._GammaCache()
    before_state = wind_tunnel._state(before_checkpoint, settings, gamma_cache=cache)
    after_state = wind_tunnel._state(after_checkpoint, settings, gamma_cache=cache)
    if any(state["status"] != "available" for state in (before_state, after_state)):
        raise ValueError("Both sides of a net-GEX sign flip require priced exposure")
    before = _point(before_state, before_checkpoint.source)
    after = _point(after_state, after_checkpoint.source)
    if before["summary"]["net_sign"] * after["summary"]["net_sign"] != -1:
        raise ValueError("The selected replay update does not mark a net-GEX sign flip")

    alternative = counterfactual = reason = None
    status = "not_requested"
    if normalized["remove_update"]:
        checkpoint = inputs["counterfactual"]
        alternative_state = wind_tunnel._state(checkpoint, settings, gamma_cache=cache)
        if alternative_state["status"] == "available":
            counterfactual = _point(alternative_state, checkpoint.source)
            alternative = _priced_rows(checkpoint, alternative_state)
            status = "available"
        else:
            status, reason = "unavailable", alternative_state["reason"]

    contributions = _contributions(_priced_rows(before_checkpoint, before_state),
                                   _priced_rows(after_checkpoint, after_state), alternative)
    net_delta = after["summary"]["total_net_gex"] - before["summary"]["total_net_gex"]
    attributed = math.fsum(row["delta_gex"] for row in contributions)
    if not math.isclose(net_delta, attributed, rel_tol=1e-10, abs_tol=1e-6):
        raise ValueError("Contract contributions did not reconcile to the priced net-GEX change")

    identity = calculation_identity()
    result = {
        "schema": f"gex-terminal.wind-tunnel.{normalized['operation']}.v1", "version": wind_tunnel.VERSION,
        "request": normalized, "request_sha256": wind_tunnel._sha(normalized),
        "calculation": identity, "calculation_fingerprint": wind_tunnel._sha(identity),
        "source": after_checkpoint.source, "before": before, "after": after, "event": inputs["event"],
        "counterfactual": counterfactual, "counterfactual_status": status, "counterfactual_reason": reason,
        "removal_requested": normalized["remove_update"],
        "contributions": contributions, "net_gex_delta": net_delta, "attributed_gex_delta": attributed,
        "model": {"model": settings["model"], "label": wind_tunnel.CHECKPOINT_MODEL_LABEL,
                  "fallback_dte": settings["fallback_dte"], "risk_free_rate": settings["risk_free_rate"]},
        "limitations": {
            "source_kind": after_checkpoint.source["source_kind"], "predictive_validity": "unmeasured", "future_events_used": False,
            "interpretation": "Changes reconcile the priced model output. Removing the update changes only this replay calculation.",
            "reproduction": "Requires the original local capture, matching its SHA-256, and the recorded calculation build.",
        },
    }
    result["result_sha256"] = wind_tunnel._sha(result)
    return result

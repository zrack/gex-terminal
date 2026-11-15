"""Explain one known transition in the bundled synthetic ES replay."""

from dataclasses import replace
import hashlib
from importlib.resources import files
import math
from typing import Any, Mapping

from . import wind_tunnel


SESSION = "zero-gamma-flip"
EVENT_INDEX = 6
EVENT_TIME = "2026-07-16T16:00:04Z"
OPERATION = "investigate"


def calculation_identity() -> dict:
    # Extend the identity for this receipt kind without changing the identity
    # used by existing Wind Tunnel receipts.
    identity = wind_tunnel.calculation_identity()
    module = files("gex_terminal").joinpath("wind_tunnel_investigation.py")
    identity["implementation"][module.name] = hashlib.sha256(module.read_bytes()).hexdigest()
    return identity


def _request(request: Mapping[str, Any]) -> dict:
    if not isinstance(request, Mapping) or set(request) - {
        "schema", "operation", "session", "remove_call_update",
    }:
        raise ValueError("Expected a bounded Wind Tunnel investigation request")
    if (request.get("schema", wind_tunnel.REQUEST_SCHEMA) != wind_tunnel.REQUEST_SCHEMA
            or request.get("operation", OPERATION) != OPERATION
            or request.get("session") != SESSION):
        raise ValueError("This investigation requires the bundled Zero-Gamma Flip replay")
    remove = request.get("remove_call_update", False)
    if type(remove) is not bool:
        raise ValueError("remove_call_update must be boolean")
    return {"schema": wind_tunnel.REQUEST_SCHEMA, "operation": OPERATION,
            "session": SESSION, "remove_call_update": remove}


def _point(state: dict) -> dict:
    if state["status"] != "available":
        raise ValueError("The bundled investigation checkpoint could not be evaluated")
    summary = state["summary"]
    return {"as_of": state["as_of"], "spot": state["spot"], "summary": {
        field: summary[field] for field in ("total_net_gex", "net_sign", "gamma_wall", "units")
    }}


def _contributions(before: dict, after: dict, counterfactual: dict | None) -> list[dict]:
    earlier = {row["contract_id"]: row for row in before["contracts"]}
    later = {row["contract_id"]: row for row in after["contracts"]}
    branch = {row["contract_id"]: row for row in counterfactual["contracts"]} if counterfactual is not None else {}
    changed = []
    # This fully priced synthetic fixture aggregates quantities by strike and
    # side. A row absent from a prefix had no quantity in that prefix.
    for contract_id in earlier.keys() | later.keys():
        left, right = earlier.get(contract_id, {}), later.get(contract_id, {})
        strike_side = right or left
        before_qty, after_qty = left.get("quantity", 0.0), right.get("quantity", 0.0)
        before_gex, after_gex = left.get("net_gex", 0.0), right.get("net_gex", 0.0)
        if before_qty == after_qty and before_gex == after_gex:
            continue
        alternative = branch.get(contract_id, {})
        changed.append({
            "contract_id": contract_id, "strike": strike_side["strike"],
            "option_type": strike_side["option_type"],
            "before_quantity": before_qty, "after_quantity": after_qty,
            "before_gex": before_gex, "after_gex": after_gex,
            "delta_gex": after_gex - before_gex,
            "counterfactual_quantity": alternative.get("quantity", 0.0) if counterfactual is not None else None,
            "counterfactual_gex": alternative.get("net_gex", 0.0) if counterfactual is not None else None,
        })
    return sorted(changed, key=lambda row: (-abs(row["delta_gex"]), row["contract_id"]))


async def investigate(request: Mapping[str, Any]) -> dict:
    """Reconstruct the two adjacent prefixes and optionally omit the final update."""
    normalized = _request(request)
    records, raw = wind_tunnel._messages(wind_tunnel._session(SESSION))
    if len(records) <= EVENT_INDEX:
        raise ValueError("The bundled replay does not contain the investigation event")
    event = records[EVENT_INDEX]
    if (event.get("timestamp") != EVENT_TIME or event.get("type") != "options_volume_tick"
            or event.get("option_type") != "C" or event.get("schema_version", 1) != 1):
        raise ValueError("The bundled replay does not contain the expected call-volume update")

    settings = wind_tunnel.normalize_request({"session": SESSION, "fallback_dte": 0.01})
    earlier = await wind_tunnel._checkpoint({**settings, "checkpoint": EVENT_INDEX - 1})
    later = await wind_tunnel._checkpoint({**settings, "checkpoint": EVENT_INDEX})
    source_sha256 = hashlib.sha256(raw).hexdigest()
    if any(checkpoint.source["source_sha256"] != source_sha256 or checkpoint.mode != "legacy_v1"
           for checkpoint in (earlier, later)):
        raise ValueError("The bundled investigation inputs changed or are unsupported")

    cache = wind_tunnel._GammaCache()
    before_state = wind_tunnel._state(earlier, settings, gamma_cache=cache)
    after_state = wind_tunnel._state(later, settings, gamma_cache=cache)
    before = {**_point(before_state), "source": earlier.source}
    after = {**_point(after_state), "source": later.source}
    if before["summary"]["net_sign"] != -1 or after["summary"]["net_sign"] != 1:
        raise ValueError("The bundled event no longer produces the expected net-GEX sign flip")

    counterfactual_state = None
    counterfactual = None
    if normalized["remove_call_update"]:
        # The prefixes differ by just this option update. With it omitted the
        # earlier option and underlying state survives to the later cutoff.
        omitted = replace(earlier, as_of=later.as_of)
        counterfactual_state = wind_tunnel._state(omitted, settings, gamma_cache=cache)
        counterfactual = {**_point(counterfactual_state),
                          "input_checkpoint_sha256": earlier.source["checkpoint_sha256"]}

    contributions = _contributions(before_state, after_state, counterfactual_state)
    net_delta = after["summary"]["total_net_gex"] - before["summary"]["total_net_gex"]
    attributed = math.fsum(row["delta_gex"] for row in contributions)
    if not math.isclose(net_delta, attributed, rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError("The strike/side contributions did not reconcile to the net-GEX change")

    identity = calculation_identity()
    result = {
        "schema": "gex-terminal.wind-tunnel.investigate.v1", "version": wind_tunnel.VERSION,
        "request": normalized, "request_sha256": wind_tunnel._sha(normalized),
        "calculation": identity, "calculation_fingerprint": wind_tunnel._sha(identity),
        "source": later.source, "before": before, "after": after, "counterfactual": counterfactual,
        "event": {"index": EVENT_INDEX, "as_of": EVENT_TIME, "strike": event["strike"],
                  "option_type": event["option_type"], "volume": event["volume"],
                  "expiry": event["expiry"], "event_sha256": wind_tunnel._sha(event)},
        "contributions": contributions, "net_gex_delta": net_delta, "attributed_gex_delta": attributed,
        "model": {"model": settings["model"], "label": wind_tunnel.MODEL_LABELS[settings["model"]],
                  "fallback_dte": settings["fallback_dte"], "risk_free_rate": settings["risk_free_rate"]},
        "limitations": {"source_kind": "synthetic_fixture", "predictive_validity": "unmeasured",
                        "future_events_used": False,
                        "interpretation": "Attribution explains the change in the volume proxy for this synthetic fixture.",
                        "contract_scope": "Legacy rows are strike/side aggregates with configured expiry time."},
    }
    result["result_sha256"] = wind_tunnel._sha(result)
    return result

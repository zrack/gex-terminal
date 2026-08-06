"""Serialize a computed GEX snapshot to a portable JSON summary.

Kept free of any UI dependency so snapshots can be produced from the CLI, a
keybinding in the terminal, or a future scheduled job.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping

from gex_terminal.model_evidence import (
    DAY_COUNT_CONVENTION,
    GEX_UNITS,
    MODEL_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
)


def build_snapshot(
    *,
    symbol: str,
    spot: float,
    session_open: float,
    days_to_expiry: float,
    contract_multiplier: int,
    risk_free_rate: float,
    data: Dict[str, Any],
    chain_state: Mapping[float, Mapping[str, Any]],
    expiry_breakdown: Dict[str, float] | None = None,
    timestamp: str | None = None,
) -> Dict[str, Any]:
    """Assemble a JSON-serializable snapshot from a computed engine `data` dict."""
    strikes = []
    call_volumes = data.get("call_volume", ())
    put_volumes = data.get("put_volume", ())
    for index, (strike, gamma, call_gex, put_gex, net_gex) in enumerate(zip(
        data["strikes"], data["gammas"], data["call_gex"], data["put_gex"], data["net_gex"]
    )):
        state = chain_state.get(float(strike), {"C": 0, "P": 0})
        call_volume = (
            int(call_volumes[index])
            if index < len(call_volumes)
            else int(state.get("C", 0))
        )
        put_volume = (
            int(put_volumes[index])
            if index < len(put_volumes)
            else int(state.get("P", 0))
        )
        strikes.append({
            "strike": float(strike),
            "call_volume": call_volume,
            "put_volume": put_volume,
            "gamma": float(gamma),
            "call_gex": float(call_gex),
            "put_gex": float(put_gex),
            "net_gex": float(net_gex),
        })

    call_total = sum(float(value) for value in data["call_gex"])
    put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
    imbalance = call_total / put_total_abs if put_total_abs else 0.0

    directionalized = data.get("directionalized")
    return {
        "schema": "gex-terminal.snapshot.v2",
        "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "spot": float(spot),
        "session_open": float(session_open),
        "session_change": float(spot - session_open) if session_open else 0.0,
        "days_to_expiry": float(days_to_expiry),
        "contract_multiplier": int(contract_multiplier),
        "risk_free_rate": float(risk_free_rate),
        "metrics": {
            "total_net_gex": float(data["total_net_gex"]),
            "gamma_wall": float(data["gamma_wall_strike"]),
            "call_wall": float(data.get("call_wall_strike", data["gamma_wall_strike"])),
            "put_wall": float(data.get("put_wall_strike", data["gamma_wall_strike"])),
            "zero_gamma": float(data["zero_gamma_strike"]),
            "strike_profile_flip": (
                float(data["strike_profile_flip"])
                if data.get("strike_profile_flip") is not None
                else None
            ),
            "nearest_neutral_strike": float(
                data.get(
                    "nearest_neutral_strike",
                    data.get("nearest_zero_strike", data["zero_gamma_strike"]),
                )
            ),
            "imbalance": float(imbalance),
            "concentration_ratio": float(data.get("concentration_ratio", 0.0)),
            "concentration_band": [
                float(data.get("concentration_band_low", 0.0)),
                float(data.get("concentration_band_high", 0.0)),
            ],
        },
        "model": {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "normalized_schema_versions": list(
                data.get("normalized_schema_versions", (1,))
            ),
            "units": data.get("units", GEX_UNITS),
            "day_count_convention": data.get(
                "day_count_convention", DAY_COUNT_CONVENTION
            ),
            "calculation_mode": data.get("calculation_mode", "legacy_v1"),
            "pricing_models": list(data.get("pricing_models", ("black_scholes",))),
            "gamma_aggregation": data.get("gamma_aggregation", "quantity_weighted_mean"),
            "zero_gamma_method": data.get("zero_gamma_method", "legacy_strike_profile"),
            "zero_gamma_semantics": data.get("zero_gamma_semantics", "legacy_strike_profile"),
            "contract_count": int(data.get("contract_count", len(strikes))),
            "selected_contract_count": int(
                data.get("selected_contract_count", data.get("contract_count", len(strikes)))
            ),
            "expired_contract_count": int(data.get("expired_contract_count", 0)),
            "legacy_contract_fallback_count": int(
                data.get("legacy_contract_fallback_count", 0)
            ),
            "position_sources": list(
                data.get("position_sources", ("legacy_volume_proxy",))
            ),
            "position_source_conflict_count": int(
                data.get("position_source_conflict_count", 0)
            ),
            "iv_sources": list(data.get("iv_sources", ())),
            "iv_source_counts": dict(data.get("iv_source_counts", {})),
            "iv_inversion_methods": list(data.get("iv_inversion_methods", ())),
            "expiry_filter": data.get("expiry_filter", "all"),
            "as_of": data.get("as_of"),
            "parallel_models": (
                ["aggressor_directionalized_volume"]
                if isinstance(directionalized, dict)
                else []
            ),
            "direction_sources": list(
                directionalized.get("direction_sources", ())
                if isinstance(directionalized, dict)
                else ()
            ),
        },
        "directionalized": directionalized,
        "expiry_breakdown": expiry_breakdown or {},
        "strikes": strikes,
    }


def write_snapshot(snapshot: Dict[str, Any], output_path: str) -> Path:
    """Write a snapshot dict to `output_path` as pretty JSON and return the path."""
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return target

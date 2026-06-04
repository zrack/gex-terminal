"""Serialize a computed GEX snapshot to a portable JSON summary.

Kept free of any UI dependency so snapshots can be produced from the CLI, a
keybinding in the terminal, or a future scheduled job.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping


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
    for strike, gamma, call_gex, put_gex, net_gex in zip(
        data["strikes"], data["gammas"], data["call_gex"], data["put_gex"], data["net_gex"]
    ):
        state = chain_state.get(float(strike), {"C": 0, "P": 0})
        strikes.append({
            "strike": float(strike),
            "call_volume": int(state.get("C", 0)),
            "put_volume": int(state.get("P", 0)),
            "gamma": float(gamma),
            "call_gex": float(call_gex),
            "put_gex": float(put_gex),
            "net_gex": float(net_gex),
        })

    call_total = sum(float(value) for value in data["call_gex"])
    put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
    imbalance = call_total / put_total_abs if put_total_abs else 0.0

    return {
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
            "imbalance": float(imbalance),
            "concentration_ratio": float(data.get("concentration_ratio", 0.0)),
            "concentration_band": [
                float(data.get("concentration_band_low", 0.0)),
                float(data.get("concentration_band_high", 0.0)),
            ],
        },
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

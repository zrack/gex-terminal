"""Portable export formats for chart overlays and external tools."""

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, Iterable


OVERLAY_SCHEMA = "gex-terminal.tradingview-overlay.v1"


def build_tradingview_overlay(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a GEX snapshot into portable chart-overlay levels."""
    metrics = snapshot["metrics"]
    return {
        "schema": OVERLAY_SCHEMA,
        "generated_at": snapshot["timestamp"],
        "symbol": snapshot["symbol"],
        "spot": float(snapshot["spot"]),
        "source": {
            "days_to_expiry": float(snapshot["days_to_expiry"]),
            "contract_multiplier": int(snapshot["contract_multiplier"]),
            "risk_free_rate": float(snapshot["risk_free_rate"]),
        },
        "levels": [
            _level(
                name="gamma_wall",
                label="Gamma Wall",
                price=metrics["gamma_wall"],
                color="#f59e0b",
                line_style="solid",
                notes="largest absolute strike-level net gamma exposure",
            ),
            _level(
                name="zero_gamma",
                label="Zero Gamma",
                price=metrics["zero_gamma"],
                color="#38bdf8",
                line_style="dashed",
                notes="estimated volatility-regime transition level",
            ),
            _level(
                name="call_wall",
                label="Call Wall",
                price=metrics["call_wall"],
                color="#22c55e",
                line_style="solid",
                notes="largest call-side gamma exposure",
            ),
            _level(
                name="put_wall",
                label="Put Wall",
                price=metrics["put_wall"],
                color="#ef4444",
                line_style="solid",
                notes="largest put-side gamma exposure",
            ),
            *_major_exposure_levels(snapshot),
        ],
        "bands": [
            {
                "name": "major_exposure_band",
                "label": "70% Net Gamma Band",
                "low": float(metrics["concentration_band"][0]),
                "high": float(metrics["concentration_band"][1]),
                "color": "#8b5cf6",
                "notes": "smallest strike range covering roughly 70% of absolute net gamma",
            }
        ],
        "manual_annotation": [
            "Add each level as a horizontal ray or price line on the chart.",
            "Use the band low/high as a shaded box or two boundary lines.",
            "A Pine Script or broker integration would be needed for automatic chart drawing.",
        ],
    }


def tradingview_overlay_csv(snapshot: Dict[str, Any]) -> str:
    """Render overlay levels and bands as portable CSV."""
    rows = list(_csv_rows(build_tradingview_overlay(snapshot)))
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "record_type",
            "name",
            "label",
            "price",
            "low",
            "high",
            "color",
            "line_style",
            "notes",
        ),
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def write_tradingview_overlay(snapshot: Dict[str, Any], output_path: str) -> Path:
    """Write a TradingView-style overlay export as JSON or CSV."""
    target = Path(output_path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)

    suffix = target.suffix.lower()
    if suffix == ".csv":
        target.write_text(tradingview_overlay_csv(snapshot), encoding="utf-8")
    elif suffix in {"", ".json"}:
        target.write_text(
            json.dumps(build_tradingview_overlay(snapshot), indent=2),
            encoding="utf-8",
        )
    else:
        raise ValueError("TradingView overlay export path must end in .json or .csv")
    return target


def _level(
    *,
    name: str,
    label: str,
    price: float,
    color: str,
    line_style: str,
    notes: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "price": float(price),
        "color": color,
        "line_style": line_style,
        "notes": notes,
    }


def _major_exposure_levels(snapshot: Dict[str, Any], limit: int = 3) -> list[Dict[str, Any]]:
    rows = sorted(
        snapshot["strikes"],
        key=lambda row: abs(float(row["net_gex"])),
        reverse=True,
    )
    levels = []
    for index, row in enumerate(rows[:limit], start=1):
        net_gex = float(row["net_gex"])
        levels.append(
            _level(
                name=f"major_exposure_{index}",
                label=f"Major Exposure {index}",
                price=float(row["strike"]),
                color="#22c55e" if net_gex >= 0 else "#ef4444",
                line_style="dotted",
                notes=f"net_gex={net_gex:.2f}",
            )
        )
    return levels


def _csv_rows(overlay: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for level in overlay["levels"]:
        yield {
            "record_type": "level",
            "name": level["name"],
            "label": level["label"],
            "price": level["price"],
            "low": "",
            "high": "",
            "color": level["color"],
            "line_style": level["line_style"],
            "notes": level["notes"],
        }
    for band in overlay["bands"]:
        yield {
            "record_type": "band",
            "name": band["name"],
            "label": band["label"],
            "price": "",
            "low": band["low"],
            "high": band["high"],
            "color": band["color"],
            "line_style": "",
            "notes": band["notes"],
        }

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.snapshot_formats import (
    snapshot_to_csv,
    snapshot_to_markdown,
    write_snapshot_export,
)


def _snapshot():
    return {
        "timestamp": "2026-07-16T12:00:00",
        "symbol": "ES",
        "spot": 5943.25,
        "session_open": 5904.50,
        "session_change": 38.75,
        "days_to_expiry": 0.25,
        "contract_multiplier": 50,
        "risk_free_rate": 0.045,
        "metrics": {
            "total_net_gex": 2_850_000_000.0,
            "gamma_wall": 5950.0,
            "call_wall": 5950.0,
            "put_wall": 5900.0,
            "zero_gamma": 5914.0,
            "imbalance": 2.94,
            "concentration_ratio": 0.65,
            "concentration_band": [5950.0, 6000.0],
        },
        "model": {
            "schema_version": 2,
            "model_version": "gex-terminal.gex-model.v2",
            "normalized_schema_versions": [2],
            "calculation_mode": "contract_v2",
            "pricing_models": ["black_76"],
            "position_sources": ["open_interest"],
            "contract_count": 1,
            "selected_contract_count": 1,
            "expired_contract_count": 0,
            "legacy_contract_fallback_count": 0,
            "position_source_conflict_count": 0,
            "expiry_filter": "0dte",
            "units": "USD gamma exposure per 1% underlying move",
            "day_count_convention": "ACT/365",
            "gamma_aggregation": "quantity_weighted_mean",
            "zero_gamma_method": "strike_profile_linear_interpolation",
            "zero_gamma_semantics": "strike_profile_exposure_crossing",
            "as_of": "2026-07-16T12:00:00Z",
        },
        "expiry_breakdown": {"0DTE": 2_850_000_000.0},
        "feed_quality": {
            "health": "simulated",
            "status": "REPLAY",
            "message_count": 42,
            "dropped_count": 1,
            "malformed_count": 0,
            "notes": ["Replay fixture"],
        },
        "alerts": [
            {
                "type": "gamma_wall_shift",
                "severity": "medium",
                "spot": 5943.25,
                "message": "Gamma wall shifted 5900.0 -> 5950.0.",
            }
        ],
        "strikes": [
            {
                "strike": 5950.0,
                "call_volume": 13480,
                "put_volume": 3044,
                "gamma": 0.018,
                "call_gex": 4_000_000_000.0,
                "put_gex": -1_000_000_000.0,
                "net_gex": 3_000_000_000.0,
            }
        ],
    }


class SnapshotFormatsTests(unittest.TestCase):
    def test_snapshot_csv_contains_metric_and_strike_rows(self):
        rows = list(csv.DictReader(io.StringIO(snapshot_to_csv(_snapshot()))))

        self.assertIn("metric", {row["record_type"] for row in rows})
        self.assertIn("strike", {row["record_type"] for row in rows})
        self.assertIn("alert", {row["record_type"] for row in rows})
        self.assertIn("feed_quality", {row["record_type"] for row in rows})
        self.assertIn("model", {row["record_type"] for row in rows})
        model_names = {
            row["name"] for row in rows if row["record_type"] == "model"
        }
        self.assertIn("model_version", model_names)
        self.assertIn("units", model_names)

    def test_snapshot_markdown_contains_core_levels(self):
        markdown = snapshot_to_markdown(_snapshot())

        self.assertIn("# ES GEX Snapshot", markdown)
        self.assertIn("Gamma wall", markdown)
        self.assertIn("Zero gamma", markdown)
        self.assertIn("Replay Alerts", markdown)
        self.assertIn("Feed Quality", markdown)
        self.assertIn("Model Provenance", markdown)
        self.assertIn("black_76", markdown)
        self.assertIn("ACT/365", markdown)

    def test_write_snapshot_export_by_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            json_path = write_snapshot_export(_snapshot(), str(base / "snapshot.json"))
            csv_path = write_snapshot_export(_snapshot(), str(base / "snapshot.csv"))
            md_path = write_snapshot_export(_snapshot(), str(base / "snapshot.md"))

            self.assertEqual(json.loads(json_path.read_text())["symbol"], "ES")
            self.assertIn("record_type", csv_path.read_text())
            self.assertIn("# ES GEX Snapshot", md_path.read_text())


if __name__ == "__main__":
    unittest.main()

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.overlays import (
    OVERLAY_SCHEMA,
    build_tradingview_overlay,
    tradingview_overlay_csv,
    write_tradingview_overlay,
)


def _snapshot():
    return {
        "timestamp": "2026-07-16T12:00:00",
        "symbol": "ES",
        "spot": 5943.25,
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
        "strikes": [
            {"strike": 5900.0, "net_gex": -250_000_000.0},
            {"strike": 5950.0, "net_gex": 3_000_000_000.0},
            {"strike": 6000.0, "net_gex": 100_000_000.0},
            {"strike": 6025.0, "net_gex": 50_000_000.0},
        ],
    }


class TradingViewOverlayTests(unittest.TestCase):
    def test_overlay_contains_core_levels_and_band(self):
        overlay = build_tradingview_overlay(_snapshot())

        self.assertEqual(overlay["schema"], OVERLAY_SCHEMA)
        level_names = {level["name"] for level in overlay["levels"]}
        self.assertIn("gamma_wall", level_names)
        self.assertIn("zero_gamma", level_names)
        self.assertIn("call_wall", level_names)
        self.assertIn("put_wall", level_names)
        self.assertIn("major_exposure_1", level_names)
        self.assertEqual(overlay["bands"][0]["low"], 5950.0)
        self.assertEqual(overlay["bands"][0]["high"], 6000.0)

    def test_csv_contains_level_and_band_rows(self):
        rows = list(csv.DictReader(io.StringIO(tradingview_overlay_csv(_snapshot()))))

        self.assertEqual(rows[0]["record_type"], "level")
        self.assertEqual(rows[0]["name"], "gamma_wall")
        self.assertEqual(rows[-1]["record_type"], "band")
        self.assertEqual(rows[-1]["name"], "major_exposure_band")

    def test_write_json_and_csv_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = write_tradingview_overlay(_snapshot(), str(Path(tmp) / "levels.json"))
            csv_path = write_tradingview_overlay(_snapshot(), str(Path(tmp) / "levels.csv"))

            self.assertEqual(json.loads(json_path.read_text())["schema"], OVERLAY_SCHEMA)
            self.assertIn("major_exposure_band", csv_path.read_text())

    def test_rejects_unknown_export_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_tradingview_overlay(_snapshot(), str(Path(tmp) / "levels.txt"))


if __name__ == "__main__":
    unittest.main()

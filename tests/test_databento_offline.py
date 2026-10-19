import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.databento_offline import (
    build_offline_databento_certification,
    load_databento_records,
    replay_databento_records,
)


def _config():
    return GexConfig(
        symbol="ES", symbols=("ES",), data_mode="replay", data_provider="databento",
        contract_multiplier=50, risk_free_rate=0.045, days_to_expiry=14,
        refresh_interval_seconds=1, stale_after_seconds=10, replay_path="",
        replay_delay_seconds=0, tradovate_environment="demo",
    )


class DatabentoOfflineTests(unittest.IsolatedAsyncioTestCase):
    def test_loads_mixed_jsonl_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_text('# comment\n{"record_type":"definition"}\n', encoding="utf-8")
            self.assertEqual(load_databento_records(path), [{"record_type": "definition"}])

    async def test_stale_underlying_uses_labeled_fallback(self):
        records = [
            {"record_type":"definition", "instrument_id":101, "raw_symbol":"ESQ6 C6000",
             "asset":"ES", "underlying_id":202, "strike_price":6000,
             "instrument_class":"C", "expiration":"2026-08-20T20:00:00Z"},
            {"record_type":"mbp-1", "instrument_id":202, "bid_px_00":5999.75,
             "ask_px_00":6000.25, "ts_event":"2026-08-06T16:00:00Z"},
            {"record_type":"trades", "instrument_id":101, "price":105, "size":2,
             "side":"B", "ts_event":"2026-08-06T16:00:05Z"},
        ]
        report = await replay_databento_records(records, config=_config())
        self.assertEqual(report["temporal_integrity"]["stale_underlying_prices"], 1)
        self.assertEqual(report["coverage"]["fallback_iv_ticks"], 1)
        self.assertFalse(report["result"]["software_path_certified"])
        self.assertFalse(report["result"]["live_transport_certified"])

    async def test_adversarial_matrix_passes_without_live_claim(self):
        report = await build_offline_databento_certification(_config())
        self.assertTrue(report["result"]["passed"])
        self.assertFalse(report["result"]["live_transport_certified"])
        self.assertEqual(len(report["cases"]), 12)


if __name__ == "__main__":
    unittest.main()

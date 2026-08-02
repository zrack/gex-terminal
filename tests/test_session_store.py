import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.cli import compute_snapshot
from gex_terminal.config import GexConfig
from gex_terminal.replay_catalog import replay_session_for_name
from gex_terminal.session_store import (
    SESSION_RECORD_SCHEMA,
    SESSION_STORE_REPORT_SCHEMA,
    build_session_store_report,
    format_session_record_list,
    format_session_save_summary,
    load_session_records,
    save_session_snapshot,
    session_store_report_to_csv,
    session_store_report_to_markdown,
    write_session_store_report,
)


def _config(session_name="zero-gamma-flip"):
    session = replay_session_for_name(session_name)
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ", "SPX", "QQQ"),
        data_mode="replay",
        data_provider="replay",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path=session.path,
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


class SessionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_loads_lists_and_reports_session_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_snapshot, _, _ = await compute_snapshot(_config("trend-day"))
            second_snapshot, _, _ = await compute_snapshot(_config("zero-gamma-flip"))

            first = save_session_snapshot(
                first_snapshot,
                tmp,
                source_name="trend-day",
                label="trend baseline",
                generated_at="2026-08-02T12:00:00.000001",
            )
            second = save_session_snapshot(
                second_snapshot,
                tmp,
                source_name="zero-gamma-flip",
                label="zero flip",
                generated_at="2026-08-02T12:00:01.000001",
            )

            records = load_session_records(tmp)
            report = build_session_store_report(records)
            markdown = session_store_report_to_markdown(report)
            rows = list(csv.DictReader(io.StringIO(session_store_report_to_csv(report))))

            self.assertEqual(first["schema"], SESSION_RECORD_SCHEMA)
            self.assertEqual(second["label"], "zero flip")
            self.assertEqual(len(records), 2)
            self.assertEqual(report["schema"], SESSION_STORE_REPORT_SCHEMA)
            self.assertIn("Historical Session Records", format_session_record_list(records))
            self.assertIn("Saved session record", format_session_save_summary(first))
            self.assertIn("# Historical Session Store", markdown)
            self.assertIn("comparison", {row["record_type"] for row in rows})

            md_path = write_session_store_report(report, Path(tmp) / "session_store.md")
            csv_path = write_session_store_report(report, Path(tmp) / "session_store.csv")
            json_path = write_session_store_report(report, Path(tmp) / "session_store.json")

            self.assertIn("Historical Session Store", md_path.read_text())
            self.assertIn("record_type", csv_path.read_text())
            self.assertEqual(json.loads(json_path.read_text())["schema"], SESSION_STORE_REPORT_SCHEMA)


if __name__ == "__main__":
    unittest.main()

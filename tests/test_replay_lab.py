import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.replay_lab import (
    build_replay_lab_report,
    replay_lab_to_csv,
    replay_lab_to_markdown,
    write_replay_lab_report,
)


def _config():
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ", "SPX", "QQQ"),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="sample_data/demo_replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


class ReplayLabTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_replay_lab_report_with_alerts_and_comparisons(self):
        report = await build_replay_lab_report(
            _config(),
            session_names=("trend-day", "zero-gamma-flip"),
        )

        self.assertEqual(report["schema"], "gex-terminal.replay-lab.v1")
        self.assertEqual(len(report["sessions"]), 2)
        self.assertEqual(len(report["comparisons"]), 1)
        self.assertGreater(report["sessions"][0]["summary"]["snapshot_count"], 0)
        self.assertGreater(report["sessions"][1]["summary"]["alert_count"], 0)
        self.assertIn("snapshot", report["sessions"][0])

    async def test_formats_replay_lab_markdown_csv_and_json(self):
        report = await build_replay_lab_report(_config(), session_names=("trend-day",))

        markdown = replay_lab_to_markdown(report)
        csv_rows = list(csv.DictReader(io.StringIO(replay_lab_to_csv(report))))

        self.assertIn("# Replay Research Lab", markdown)
        self.assertIn("Trend Day", markdown)
        self.assertIn("session", {row["record_type"] for row in csv_rows})

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            md_path = write_replay_lab_report(report, str(base / "lab.md"))
            csv_path = write_replay_lab_report(report, str(base / "lab.csv"))
            json_path = write_replay_lab_report(report, str(base / "lab.json"))

            self.assertIn("Replay Research Lab", md_path.read_text())
            self.assertIn("record_type", csv_path.read_text())
            self.assertEqual(json.loads(json_path.read_text())["schema"], report["schema"])


if __name__ == "__main__":
    unittest.main()

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.provider_fixture_lab import (
    build_provider_fixture_lab_report,
    bundled_provider_fixture_cases,
    provider_fixture_case_command,
    provider_fixture_case_for_name,
    provider_fixture_lab_to_csv,
    provider_fixture_lab_to_markdown,
    write_provider_fixture_lab_report,
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


class ProviderFixtureLabTests(unittest.IsolatedAsyncioTestCase):
    def test_bundled_case_commands_use_installed_package_selector(self):
        for case in bundled_provider_fixture_cases():
            self.assertEqual(
                provider_fixture_case_command(case),
                f"gex-terminal inject-provider bundled:{case.name}",
            )
            self.assertEqual(provider_fixture_case_for_name(case.name), case)

    async def test_builds_provider_fixture_lab_report_across_bundled_cases(self):
        report = await build_provider_fixture_lab_report(_config())

        self.assertEqual(report["schema"], "gex-terminal.provider-fixture-lab.v1")
        self.assertEqual(report["scorecard"]["total"], len(bundled_provider_fixture_cases()))
        self.assertEqual(report["scorecard"]["passed"], len(bundled_provider_fixture_cases()))
        self.assertEqual(report["scorecard"]["failed"], 0)
        self.assertEqual(report["scorecard"]["healthy"], 0)
        self.assertEqual(report["scorecard"]["simulated"], 3)
        self.assertEqual(report["scorecard"]["degraded"], 2)

        summaries = {
            result["name"]: result["summary"]
            for result in report["cases"]
        }
        self.assertEqual(summaries["tradovate-live-sample"]["health"], "degraded")
        self.assertEqual(summaries["databento-glbx"]["symbol"], "ES")
        self.assertEqual(summaries["yfinance-etf-options"]["symbol"], "SPY")
        for summary in summaries.values():
            self.assertEqual(summary["source_kind"], "offline_provider_fixture")
            self.assertFalse(summary["network_used"])
            self.assertEqual(summary["mapping_status"], "computed")
            self.assertEqual(summary["status"], "REPLAY")
            self.assertEqual(summary["data_mode"], "REPLAY")
            self.assertEqual(summary["connection_state"], "DISCONNECTED")
            self.assertNotEqual(summary["health"], "healthy")
        self.assertIn("snapshot", report["cases"][0])

    async def test_formats_provider_fixture_lab_markdown_csv_and_json(self):
        report = await build_provider_fixture_lab_report(_config())

        markdown = provider_fixture_lab_to_markdown(report)
        csv_rows = list(csv.DictReader(io.StringIO(provider_fixture_lab_to_csv(report))))

        self.assertIn("# Offline Provider Fixture Workbench", markdown)
        self.assertIn("Tradovate Live Frames", markdown)
        self.assertIn("- Healthy live: `0`", markdown)
        self.assertIn("- Simulated: `3`", markdown)
        self.assertIn("| Mode | Network | Health |", markdown)
        self.assertIn("network used `no`; runtime `REPLAY` / `DISCONNECTED`", markdown)
        self.assertIn("historical compatibility field", markdown)
        self.assertIn("not a portfolio root", markdown)
        self.assertIn("databento-glbx", {row["case"] for row in csv_rows})
        self.assertEqual({row["network_used"] for row in csv_rows}, {"False"})
        self.assertEqual({row["data_mode"] for row in csv_rows}, {"REPLAY"})

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            md_path = write_provider_fixture_lab_report(report, str(base / "lab.md"))
            csv_path = write_provider_fixture_lab_report(report, str(base / "lab.csv"))
            json_path = write_provider_fixture_lab_report(report, str(base / "lab.json"))

            self.assertIn("Offline Provider Fixture Workbench", md_path.read_text())
            self.assertIn("fixture_format", csv_path.read_text())
            self.assertEqual(json.loads(json_path.read_text())["schema"], report["schema"])


if __name__ == "__main__":
    unittest.main()

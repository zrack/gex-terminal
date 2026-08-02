import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.research_journal import (
    ENTRY_SCHEMA,
    REPORT_SCHEMA,
    add_journal_entry,
    build_journal_report,
    compare_journal_entries,
    format_journal_list,
    journal_report_to_csv,
    journal_report_to_markdown,
    load_journal_entries,
    resolve_journal_entry,
    write_journal_report,
)


def _config(symbol="ES", multiplier=50):
    symbols = tuple(dict.fromkeys((symbol, "ES", "NQ", "SPX", "QQQ")))[:4]
    return GexConfig(
        symbol=symbol,
        symbols=symbols,
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=multiplier,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="sample_data/demo_replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


class ResearchJournalTests(unittest.IsolatedAsyncioTestCase):
    async def test_adds_loads_lists_and_compares_journal_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp) / "research_journal"
            first = await add_journal_entry(
                _config(),
                journal_dir,
                replay_session_name="trend-day",
            )
            second = await add_journal_entry(
                _config(),
                journal_dir,
                replay_session_name="zero-gamma-flip",
            )

            entries = load_journal_entries(journal_dir)
            comparison = compare_journal_entries(entries)

            self.assertEqual(first["schema"], ENTRY_SCHEMA)
            self.assertEqual(first["inputs"]["symbol"], "ES")
            self.assertEqual(first["inputs"]["contract_multiplier"], 50)
            self.assertEqual(second["source"]["name"], "zero-gamma-flip")
            self.assertEqual(len(entries), 2)
            self.assertEqual(resolve_journal_entry(entries, "latest")["id"], second["id"])
            self.assertEqual(comparison["from"]["id"], first["id"])
            self.assertEqual(comparison["to"]["id"], second["id"])
            self.assertNotIn("by -", " ".join(comparison["notes"]))
            self.assertIn("Journal Entries", format_journal_list(entries))
            self.assertIn("zero_gamma", entries[-1]["snapshot"]["metrics"])

    async def test_writes_markdown_csv_and_json_journal_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp) / "research_journal"
            normalized_entry = await add_journal_entry(
                _config(symbol="NQ", multiplier=20),
                journal_dir,
                replay_session_name="trend-day",
            )
            await add_journal_entry(_config(), journal_dir, replay_session_name="gap-fade")

            report = build_journal_report(load_journal_entries(journal_dir))
            markdown = journal_report_to_markdown(report)
            rows = list(csv.DictReader(io.StringIO(journal_report_to_csv(report))))

            self.assertEqual(report["schema"], REPORT_SCHEMA)
            self.assertEqual(normalized_entry["inputs"]["symbol"], "ES")
            self.assertEqual(normalized_entry["inputs"]["contract_multiplier"], 50)
            self.assertIn("# Historical Research Journal", markdown)
            self.assertIn("comparison", {row["record_type"] for row in rows})

            md_path = write_journal_report(report, Path(tmp) / "journal.md")
            csv_path = write_journal_report(report, Path(tmp) / "journal.csv")
            json_path = write_journal_report(report, Path(tmp) / "journal.json")

            self.assertIn("Historical Research Journal", md_path.read_text())
            self.assertIn("record_type", csv_path.read_text())
            self.assertEqual(json.loads(json_path.read_text())["schema"], REPORT_SCHEMA)


if __name__ == "__main__":
    unittest.main()

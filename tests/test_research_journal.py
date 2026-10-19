import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
from gex_terminal.session_capture import CapturedSessionWriter, load_captured_session


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
    async def test_adds_integrity_verified_capture_as_journal_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture_path = Path(tmp) / "capture.gex-session.jsonl"
            writer = CapturedSessionWriter(
                capture_path,
                source={"mode": "live", "provider": "test", "symbol": "ES"},
                model_inputs={
                    "days_to_expiry": 0.01,
                    "risk_free_rate": 0.045,
                    "contract_multiplier": 50,
                },
                label="captured baseline",
            )
            await writer.start()
            for message in (
                {"type": "underlying_tick", "symbol": "ES", "price": 5000,
                 "timestamp": "2026-08-04T16:00:00Z"},
                {"type": "options_volume_tick", "strike": 5000, "option_type": "C",
                 "volume": 100, "iv": 0.15, "timestamp": "2026-08-04T16:00:01Z"},
                {"type": "options_volume_tick", "strike": 5000, "option_type": "P",
                 "volume": 50, "iv": 0.15, "timestamp": "2026-08-04T16:00:02Z"},
            ):
                await writer.append(message)
            await writer.finalize()

            entry = await add_journal_entry(
                _config(),
                Path(tmp) / "journal",
                captured_session_path=capture_path,
            )

            self.assertEqual(entry["source"]["type"], "captured_session")
            self.assertEqual(entry["source"]["event_count"], 3)
            self.assertEqual(
                entry["source"]["path"],
                f"captured:{entry['source']['name']}",
            )
            self.assertEqual(entry["summary"]["path"], entry["source"]["path"])
            self.assertNotIn(tmp, json.dumps(entry))
            self.assertEqual(entry["snapshot"]["timestamp"], "2026-08-04T16:00:02Z")

    async def test_capture_journal_uses_messages_bound_to_verified_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture_path = Path(tmp) / "capture.gex-session.jsonl"
            replacement_path = Path(tmp) / "replacement.gex-session.jsonl"

            async def write_capture(path, spot):
                writer = CapturedSessionWriter(
                    path,
                    source={"mode": "live", "provider": "test", "symbol": "ES"},
                    model_inputs={"days_to_expiry": 0.01},
                )
                await writer.start()
                for message in (
                    {"type": "underlying_tick", "symbol": "ES", "price": spot},
                    {"type": "options_volume_tick", "strike": spot, "option_type": "C", "volume": 100, "iv": 0.15},
                    {"type": "options_volume_tick", "strike": spot, "option_type": "P", "volume": 50, "iv": 0.15},
                ):
                    await writer.append(message)
                await writer.finalize()

            await write_capture(capture_path, 5_000.0)
            await write_capture(replacement_path, 5_100.0)
            expected_capture, _ = load_captured_session(capture_path)
            real_load = load_captured_session

            def load_then_swap(path):
                verified = real_load(path)
                os.replace(replacement_path, capture_path)
                return verified

            with patch(
                "gex_terminal.research_journal.load_captured_session",
                load_then_swap,
            ):
                entry = await add_journal_entry(
                    _config(),
                    Path(tmp) / "journal",
                    captured_session_path=capture_path,
                )

            self.assertEqual(
                entry["source"]["content_sha256"],
                expected_capture["content_sha256"],
            )
            self.assertEqual(entry["summary"]["spot"], 5_000.0)

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

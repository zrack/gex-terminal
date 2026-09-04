import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.replay_catalog import ReplaySession
from gex_terminal.replay_lab import analyze_replay_session
from gex_terminal.research_journal import add_journal_entry, load_journal_entries
from gex_terminal.session_capture import CapturedSessionWriter
from tests.test_replay_lab import _config


def messages():
    option = {
        "schema_version": 2, "type": "options_volume_tick", "provider": "synthetic",
        "contract_id": "ES-C-5950", "symbol": "ES", "strike": 5950,
        "option_type": "C", "volume": 10, "iv": .2, "iv_source": "provider",
        "expiry": "2026-08-07", "expiry_timestamp": "2026-08-07T20:00:00Z",
        "contract_multiplier": 50, "instrument_class": "futures_option",
        "position_source": "trade_volume", "volume_semantics": "incremental",
        "event_time": "2026-08-01T14:00:02Z", "sequence": 1,
    }
    return [
        {"type": "underlying_tick", "symbol": "ES", "price": 5950,
         "timestamp": "2026-08-01T14:00:00Z"},
        option,
        {"type": "underlying_tick", "symbol": "NQ", "price": 20000,
         "timestamp": "2026-08-02T15:00:00Z", "session_phase": "rejected-late"},
        {**option, "event_time": "2026-08-03T15:00:00Z"},  # duplicate
        {**option, "sequence": 2, "contract_multiplier": 100,
         "event_time": "2026-08-04T15:00:00Z"},  # identity conflict
        {"type": "options_volume_tick", "timestamp": "2026-08-05T15:00:00Z"},
    ]


class ReplayChronologyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_records_remain_audit_only(self):
        session = ReplaySession("chronology", "unused", "Chronology", "Synthetic")
        report = await analyze_replay_session(session, _config(), messages=messages())
        snapshot = report["snapshot"]
        self.assertEqual(len(report["timeline"]), 1)
        self.assertEqual(report["timeline"][0]["message_index"], 2)
        self.assertEqual(report["timeline"][0]["input_event_time"], "2026-08-01T14:00:02Z")
        self.assertEqual(snapshot["timestamp"], snapshot["model"]["as_of"])
        self.assertEqual(snapshot["timestamp"], "2026-08-01T14:00:02Z")
        self.assertEqual(report["summary"]["last_timestamp"], snapshot["timestamp"])
        self.assertNotIn("rejected-late", report["summary"]["phases"])
        self.assertEqual(snapshot["raw_input_audit"]["last_timestamp"], "2026-08-05T15:00:00Z")
        self.assertEqual(snapshot["raw_input_audit"]["accepted_count"], 2)
        self.assertIn("rejected-late", snapshot["raw_input_audit"]["phases"])
        self.assertEqual(snapshot["feed_quality"]["dropped_count"], 1)
        self.assertEqual(snapshot["feed_quality"]["malformed_count"], 2)
        self.assertEqual(snapshot["feed_quality"]["duplicate_message_count"], 1)

    async def test_regressed_accepted_input_does_not_regress_model_time(self):
        rows = messages()[:2]
        rows.append({"type": "underlying_tick", "symbol": "ES", "price": 5951,
                     "timestamp": "2026-08-01T14:00:01Z"})
        report = await analyze_replay_session(
            ReplaySession("regression", "unused", "Regression", "Synthetic"),
            _config(), messages=rows,
        )
        self.assertEqual(report["timeline"][-1]["timestamp"], "2026-08-01T14:00:02Z")
        self.assertEqual(report["timeline"][-1]["input_event_time"], "2026-08-01T14:00:01Z")
        self.assertEqual(report["snapshot"]["spot"], 5951)

    async def test_untimed_legacy_input_is_labeled_processing_time(self):
        rows = [{key: value for key, value in row.items() if key not in {"timestamp", "event_time"}}
                for row in messages()[:2]]
        # Legacy inputs have no exact expiry to become expired at processing time.
        rows[1] = {"type": "options_volume_tick", "strike": 5950, "option_type": "C",
                   "volume": 10, "iv": .2}
        report = await analyze_replay_session(
            ReplaySession("untimed", "unused", "Untimed", "Synthetic"),
            _config(), messages=rows,
        )
        self.assertEqual(report["snapshot"]["replay_session"]["time_basis"], "processing_time")
        self.assertEqual(report["summary"]["last_timestamp"], "")
        self.assertEqual(report["snapshot"]["timestamp"], report["snapshot"]["model"]["as_of"])

    async def test_journal_retains_accepted_time_and_separate_raw_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "capture.jsonl"
            writer = CapturedSessionWriter(
                capture, source={"mode": "replay", "provider": "synthetic", "symbol": "ES"},
                model_inputs={"contract_multiplier": 50, "days_to_expiry": .01},
            )
            await writer.start()
            for row in messages()[:3]:
                await writer.append(row)
            await writer.finalize()
            await add_journal_entry(_config(), Path(directory) / "journal", captured_session_path=capture)
            entry = load_journal_entries(Path(directory) / "journal")[0]
            self.assertEqual(entry["snapshot"]["timestamp"], "2026-08-01T14:00:02Z")
            self.assertEqual(entry["snapshot"]["raw_input_audit"]["last_timestamp"], "2026-08-02T15:00:00Z")
            self.assertEqual(entry["summary"]["snapshot_count"], 1)

"""Full sessions preserve causal market state while native records live on disk."""
import copy
from enum import Enum
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from gex_terminal.cli import compute_snapshot
from gex_terminal.session_capture import load_captured_session
from scripts.databento_session_replay import build_index, convert_session, _json_safe, _json_value
from tests.test_databento_trial_replay import _records, _files as _raw_files, _config

START = "2026-08-05T22:00:00Z"
END = "2026-08-06T21:00:00Z"


def _files(root, records):
    adapted = []
    for record in records:
        if record.get("record_type") == "definition" and "ts_event" not in record:
            record = {**record, "ts_event": "2026-08-05T21:00:00Z"}
        if record.get("record_type") == "mbp-1":
            record = {**record, "record_type": "bbo-1s", "ts_recv": record["ts_event"]}
        adapted.append(record)
    return _raw_files(root, adapted)


class FullSessionConversionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gex causal session ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    async def convert(self, records, **kwargs):
        return await convert_session(files=_files(self.root, records), symbol="ES", output_dir=self.root / "output",
                                     start=START, end=END, **kwargs)

    async def test_single_state_crosses_midnight_and_matches_terminal_final_state(self):
        records = _records()
        quote = {**records[2], "ts_event": "2026-08-05T23:59:59Z"}
        trade = {**records[3], "ts_event": "2026-08-05T23:59:59.500000001Z", "size": 3}
        later_quote = {**quote, "ts_event": "2026-08-06T00:00:01Z"}
        later_trade = {**trade, "ts_event": "2026-08-06T00:00:01.500000001Z", "size": 7, "sequence": 2}
        result = await self.convert([*records[:2], later_trade, quote, later_quote, trade])
        metadata, messages = load_captured_session(result["capture"])
        self.assertTrue(metadata["integrity_verified"])
        self.assertEqual([m["volume"] for m in messages if m["type"] == "options_volume_tick"], [3, 7])
        report = json.loads(Path(result["report"]).read_text())
        self.assertEqual(report["raw_accounting"]["trades"]["selected_raw_quantity"], 10)
        self.assertEqual(report["final_selection"]["pricing_coverage"]["selected_quantity"], 10)
        snapshot, _, _ = await compute_snapshot(_config("ES", result["capture"]))
        self.assertAlmostEqual(snapshot["metrics"]["total_net_gex"], report["final_matrix"]["total_net_gex"])
        with sqlite3.connect(result["index"]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records WHERE selected=1").fetchone()[0], 6)

    async def test_future_metadata_is_not_preloaded_and_other_future_is_disclosed(self):
        records = _records()
        definition = {**records[0], "ts_event": "2026-08-06T16:00:02Z"}
        wrong = {**records[1], "instrument_id": 9999, "underlying_id": 9990}
        early_trade = {**records[3], "ts_event": "2026-08-06T16:00:01Z"}
        late_trade = {**early_trade, "sequence": 2, "ts_event": "2026-08-06T16:00:02.500000001Z"}
        quote = {**records[2], "ts_event": "2026-08-06T16:00:02Z"}
        wrong_trade = {**late_trade, "instrument_id": 9999, "sequence": 3}
        result = await self.convert([definition, wrong, records[2], quote, late_trade, early_trade, wrong_trade])
        _, messages = load_captured_session(result["capture"])
        self.assertEqual(sum(m["type"] == "options_volume_tick" for m in messages), 1)
        report = json.loads(Path(result["report"]).read_text())
        self.assertEqual(report["source"]["subset"]["excluded_option_events"], 1)
        self.assertEqual(report["raw_accounting"]["trades"]["records"], 3)
        self.assertEqual(report["raw_accounting"]["trades"]["selected_records"], 2)

    async def test_nanosecond_interval_quotes_and_native_duplicate_identity_survive_disk_merge(self):
        records = _records()
        quote = {**records[2], "record_type": "bbo-1s", "ts_event": "2026-08-06T15:59:00Z",
                 "ts_recv": "2026-08-06T16:00:01.000000001Z"}
        first = {**records[3], "ts_event": "2026-08-06T16:00:01.000000001Z", "_provider_trade_event_id": "1" * 64}
        second = {**first, "size": 2, "_provider_trade_event_id": "2" * 64}
        result = await self.convert([*records[:2], first, second, copy.deepcopy(first), quote])
        _, messages = load_captured_session(result["capture"])
        self.assertEqual(messages[0]["event_time"], quote["ts_recv"])
        trades = [m for m in messages if m["type"] == "options_volume_tick"]
        self.assertEqual([m["provider_trade_event_id"] for m in trades], ["1" * 64, "2" * 64, "1" * 64])
        report = json.loads(Path(result["report"]).read_text())
        self.assertEqual(report["final_selection"]["pricing_coverage"]["selected_quantity"], 9)

    async def test_all_expired_final_state_is_retained_without_refusing_session(self):
        records = _records()
        for definition in records[:2]:
            definition["expiration"] = "2026-08-06T16:01:00Z"
        final_quote = {**records[2], "ts_event": "2026-08-06T16:02:00Z"}
        result = await self.convert([*records, final_quote])
        metadata, messages = load_captured_session(result["capture"])
        self.assertTrue(metadata["completed"])
        self.assertEqual(sum(m.get("volume", 0) for m in messages), 12)
        report = json.loads(Path(result["report"]).read_text())
        self.assertEqual(report["final_selection"]["pricing_coverage"]["selected_contract_count"], 0)
        self.assertEqual(report["final_selection"]["expired_quantity"], 12)

    async def test_invalid_native_input_does_not_publish_complete_capture(self):
        records = _records()
        records[-1]["ts_event"] = END
        with self.assertRaisesRegex(ValueError, "outside"):
            await self.convert(records)
        self.assertFalse((self.root / "output/es.gex-session.jsonl").exists())

    async def test_outside_interval_end_quote_and_future_definition_fail_before_capture(self):
        for kind in ("quote_after", "quote_before", "future_definition"):
            with self.subTest(kind=kind):
                root = self.root / kind
                root.mkdir()
                records = _records()
                if kind == "future_definition":
                    records[0]["ts_event"] = END
                else:
                    records[2].update(record_type="bbo-1s", ts_recv=END if kind == "quote_after" else "2026-08-05T21:59:57Z")
                with self.assertRaisesRegex(ValueError, "outside"):
                    await convert_session(files=_files(root, records), symbol="ES", output_dir=root / "output", start=START, end=END)
                self.assertFalse((root / "output/es.gex-session.jsonl").exists())

    def test_native_enum_and_undefined_prices_are_serialized_without_fabrication(self):
        class NativeClass(Enum):
            FUTURE = "F"
        encoded = json.dumps(_json_safe({"instrument_class": NativeClass.FUTURE, "strike_price": float("nan"), "bid": float("inf")}), default=_json_value, allow_nan=False)
        self.assertEqual(json.loads(encoded), {"instrument_class": "F", "strike_price": None, "bid": None})

    def test_full_session_refuses_mbp_input_instead_of_claiming_bbo_provenance(self):
        output = self.root / "output"
        output.mkdir()
        records = _records()
        for record in records[:2]:
            record["ts_event"] = START
        with self.assertRaisesRegex(ValueError, "BBO-1s"):
            build_index(_raw_files(self.root, records), "ES", output)

    def test_untimed_definitions_cannot_seed_causal_session(self):
        output = self.root / "output"
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "including definitions"):
            build_index(_raw_files(self.root, _records()), "ES", output)

    def test_index_rejects_rolls_and_explicit_record_limit_without_materializing_list(self):
        for kind in ("roll", "limit"):
            with self.subTest(kind=kind):
                root = self.root / kind
                root.mkdir()
                records = _records()
                if kind == "roll":
                    records.append({**records[2], "instrument_id": 9990})
                output = root / "output"
                output.mkdir()
                with self.assertRaises(ValueError):
                    build_index(_files(root, records), "ES", output, max_records=4 if kind == "limit" else 100)


if __name__ == "__main__":
    unittest.main()

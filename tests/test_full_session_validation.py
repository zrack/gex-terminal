"""Independent raw/capture reconciliation across the historical session clock."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gex_terminal.session_capture import CapturedSessionWriter, load_captured_session
from scripts.databento_session_replay import convert_session
from scripts.validate_full_session import (RawTruth, black76, native_trade_fingerprint,
                                          ns, iso, validate_market, raw_records, model_years)
from tests.test_databento_trial_replay import _files, _records


START = "2026-08-05T22:00:00Z"
END = "2026-08-06T21:00:00Z"


def session_records():
    original = _records()
    call = {**original[0], "ts_event": "2026-08-05T21:59:58Z", "expiration": "2026-08-06T20:00:00Z", "cfi": "OCEFPS"}
    put = {**original[1], "ts_event": "2026-08-05T21:59:58Z", "expiration": "2026-08-06T20:00:00Z", "cfi": "OCEFPS", "strike_price": 6050.}
    later = {**call, "instrument_id": 9103, "raw_symbol": "ESQ6 P6000", "instrument_class": "P",
             "expiration": "2026-08-20T20:00:00Z", "cfi": "OPAFPS"}
    other = {**call, "instrument_id": 9999, "underlying_id": 9990}
    rows = [call, put, later, other]
    sequence = 0
    for stamp in ("2026-08-05T22:00:00Z", "2026-08-05T22:14:59Z", "2026-08-05T23:59:59Z",
                  "2026-08-06T00:00:01Z", "2026-08-06T13:39:59Z", "2026-08-06T19:59:58Z",
                  "2026-08-06T20:00:00Z", "2026-08-06T20:59:59Z"):
        rows.append({**original[2], "record_type": "bbo-1s", "ts_event": iso(ns(stamp) - 9_000_000_000), "ts_recv": stamp})
        if "20:00:00" in stamp or "20:59:59" in stamp:
            continue
        sequence += 1
        trade = {**original[3], "sequence": sequence, "ts_event": iso(ns(stamp) + 789_677_713), "size": 2, "price": 1.}
        rows.append(trade)
        if "23:59:59" in stamp:
            rows.append(copy.deepcopy(trade))
        sequence += 1
        rows.append({**trade, "instrument_id": 9102, "sequence": sequence, "size": 3, "price": .25, "side": "A"})
        sequence += 1
        rows.append({**trade, "instrument_id": 9103, "sequence": sequence, "size": 5, "price": 100., "side": "A"})
    rows.append({**original[3], "instrument_id": 9999, "sequence": 100, "ts_event": "2026-08-06T13:39:59.5Z", "size": 13})
    return rows


class FullSessionValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gex-independent-session-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    async def prepare(self, records=None):
        records = copy.deepcopy(session_records() if records is None else records)
        for row in records:
            if row.get("record_type") == "definition":
                row.setdefault("ts_event", "2026-08-05T21:59:58Z")
            if row.get("record_type") == "mbp-1":
                row.update(record_type="bbo-1s", ts_recv=row["ts_event"])
        files = _files(self.root, records)
        result = await convert_session(files=files, symbol="ES", output_dir=self.root / "replay", start=START, end=END)
        return files, result

    async def test_full_raw_reconciliation_midnight_expiry_styles_and_wind_receipts(self):
        files, replay = await self.prepare()
        with patch("scripts.validate_full_session.quantlib_reference", return_value=None):
            report = await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                           conversion_report=replay["report"], output=self.root / "validation")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["provider_requests"], 0)
        self.assertEqual(report["credits_used"], 0)
        raw = report["raw_accounting"]
        self.assertEqual(raw["selected_raw_quantity_including_duplicates"], 62)
        self.assertEqual(raw["selected_unique_quantity"], 60)
        self.assertEqual(raw["duplicate_trade_occurrences"], 1)
        self.assertEqual(raw["excluded_option_events"], 1)
        self.assertEqual(raw["excluded_option_quantity"], 13)
        self.assertEqual(len(report["checkpoints"]), 5)
        first, sample, before, after, final = report["checkpoints"]
        self.assertEqual(first["coverage"]["selected_quantity"], 20)
        self.assertEqual(sample["coverage"]["selected_quantity"], 50)
        self.assertEqual(before["coverage"]["selected_quantity"], 60)
        self.assertEqual(after["coverage"]["selected_quantity"], 30)
        self.assertEqual(final["expired_quantity_retained_in_session_ledger"], 30)
        self.assertEqual(final["coverage"]["selected_quantity"], 30)
        self.assertEqual(first["coverage"]["unpriced_quantity"], 6)
        self.assertTrue(all(row["receipt_reproduction"] == "verified" for row in report["checkpoints"]))
        self.assertTrue(any(check["status"] == "independent_reference_unavailable"
                            for row in report["checkpoints"] for check in row["numeric_checks"]))
        self.assertTrue((self.root / "validation/final-snapshot.json").exists())

    @unittest.skipUnless(importlib.util.find_spec("databento"), "optional native DBN SDK not installed")
    async def test_native_dbn_fields_match_captured_fingerprint_and_causal_bbo(self):
        import databento_dbn as dbn
        from scripts.verify_databento_functional import write_dbn
        records = _records()
        files = {}
        for row in records[:2]:
            row.update(underlying="ES", ts_event="2026-08-06T15:59:59Z")
        for role, kind in (("definitions", "definition"), ("trades", "trades")):
            files[role] = self.root / (role + ".dbn")
            write_dbn([row for row in records if row["record_type"] == kind], files[role])
        available = ns("2026-08-06T16:00:00.000000001Z")
        metadata = dbn.Metadata(dataset="GLBX.MDP3", start=available - 1_000_000_000,
                                stype_in=dbn.SType.RAW_SYMBOL, stype_out=dbn.SType.INSTRUMENT_ID,
                                schema=dbn.Schema.BBO_1S, symbols=[])
        quote = dbn.BBOMsg(rtype=dbn.RType.BBO_1S, publisher_id=1, instrument_id=9200,
                           ts_event=dbn.UNDEF_TIMESTAMP, ts_recv=available,
                           price=dbn.UNDEF_PRICE, size=0, side=dbn.Side.NONE,
                           levels=dbn.BidAskPair(bid_px=5999_750_000_000, ask_px=6000_250_000_000, bid_sz=1, ask_sz=1))
        files["underlying"] = self.root / "underlying.dbn"
        files["underlying"].write_bytes(metadata.encode() + bytes(quote))
        replay = await convert_session(files=files, symbol="ES", output_dir=self.root / "replay", start=START, end=END)
        report = await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                       conversion_report=replay["report"], output=self.root / "validation")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["raw_accounting"]["selected_unique_quantity"], 12)
        self.assertEqual(report["iv_sources"], {"black_76_inverted": 2})

    async def test_all_expired_final_state_remains_explicitly_unavailable(self):
        records = session_records()
        for record in records:
            if record.get("record_type") == "definition":
                record["expiration"] = "2026-08-06T20:00:00Z"
                record["cfi"] = "OCEFPS"
        files, replay = await self.prepare(records)
        report = await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                       conversion_report=replay["report"], output=self.root / "validation")
        final = report["checkpoints"][-1]
        self.assertEqual(final["coverage"]["selected_quantity"], 0)
        self.assertEqual(final["expired_quantity_retained_in_session_ledger"], 60)
        self.assertNotEqual(final["wind_status"], "available")
        self.assertTrue(final["snapshot_status"].startswith("unavailable:"))
        self.assertFalse((self.root / "validation/final-snapshot.json").exists())
        self.assertIn("prior nonempty", final["checkpoint_status"])
        self.assertEqual(final["receipt_reproduction"], "verified")

    async def test_missing_early_state_and_future_definitions_are_disclosed(self):
        records = _records()
        records[0]["ts_event"] = "2026-08-06T16:00:02Z"
        records.append({**records[2], "ts_event": "2026-08-06T16:00:02Z"})
        records.append({**records[3], "ts_event": "2026-08-06T16:00:02.500000001Z", "sequence": 3})
        files, replay = await self.prepare(records)
        report = await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                       conversion_report=replay["report"], output=self.root / "validation")
        self.assertEqual(report["raw_accounting"]["causally_unavailable_definition_events"], 1)
        self.assertEqual(report["raw_accounting"]["causally_unavailable_definition_quantity"], 7)
        self.assertEqual(report["raw_accounting"]["selected_unique_quantity"], 12)
        self.assertEqual(len(report["checkpoints"]), 5)
        self.assertEqual(report["checkpoints"][0]["wind_status"], "not_evaluable")
        self.assertIsNone(report["checkpoints"][0]["actual_as_of"])
        self.assertEqual(report["checkpoints"][-1]["receipt_reproduction"], "verified")

    def test_bounded_raw_json_lines_and_independent_session_window(self):
        huge = self.root / "huge.jsonl"
        huge.write_bytes(b" " * (1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            list(raw_records(huge))
        records = session_records()
        next(row for row in records if row.get("record_type") == "trades")["ts_event"] = END
        files = _files(self.root, records)
        with self.assertRaisesRegex(ValueError, "outside requested session"):
            RawTruth(self.root / "outside.sqlite", files, "ES", session={"start": START, "end": END})
        records = session_records()
        del records[0]["ts_event"]
        files = _files(self.root, records)
        with self.assertRaisesRegex(ValueError, "authoritative event time"):
            RawTruth(self.root / "untimed.sqlite", files, "ES", session={"start": START, "end": END})

    async def test_captured_native_style_premium_and_causal_quote_tampering_rejected(self):
        files, replay = await self.prepare()
        _, messages = load_captured_session(replay["capture"])
        trade = next(row for row in messages if row["type"] == "options_volume_tick")
        for name, mutate, expected in (
            ("style", lambda row: row.update(exercise_style="american"), "exercise_style"),
            ("premium", lambda row: row["iv_provenance"].update(option_price=999), "premium"),
            ("quote", lambda row: row["iv_provenance"].update(underlying_event_time="2026-08-06T20:59:59Z"), "causally"),
            ("fraction", lambda row: row.update(event_time=iso(ns(row["event_time"]) + 1)), "time/quantity"),
        ):
            with self.subTest(name=name):
                truth = RawTruth(self.root / f"{name}.sqlite", files, "ES")
                self.addCleanup(truth.close)
                value = copy.deepcopy(trade)
                mutate(value)
                with self.assertRaisesRegex(ValueError, expected):
                    truth.trade(value)

    async def test_native_freshness_edge_is_not_silently_relaxed_by_model_clock(self):
        records = session_records()
        first_call = next(row for row in records if row.get("record_type") == "trades" and row["instrument_id"] == 9101)
        first_call["ts_event"] = "2026-08-05T22:00:02.000000713Z"
        files, replay = await self.prepare(records)
        _, messages = load_captured_session(replay["capture"])
        edge = next(row for row in messages if row.get("contract_id") == "9101")
        self.assertEqual(edge["iv_source"], "black_76_inverted")
        self.assertEqual(edge["iv_provenance"]["underlying_price_age_ms"], 2000.)
        truth = RawTruth(self.root / "edge.sqlite", files, "ES")
        self.addCleanup(truth.close)
        with self.assertRaisesRegex(ValueError, "explicit precision-edge review"):
            truth.trade(edge)

    async def test_native_hash_drift_and_converter_accounting_drift_rejected(self):
        files, replay = await self.prepare()
        report_path = Path(replay["report"])
        report = json.loads(report_path.read_text())
        report["raw_accounting"]["trades"]["raw_quantity"] += 1
        report_path.write_text(json.dumps(report))
        with patch("scripts.validate_full_session.quantlib_reference", return_value=None):
            with self.assertRaisesRegex(ValueError, "quantity accounting"):
                await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                      conversion_report=report_path, output=self.root / "bad-accounting")
        with files["trades"].open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "provenance"):
            await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                  conversion_report=report_path, output=self.root / "bad-hash")

    async def test_retained_iv_must_link_to_an_actual_successful_contract_observation(self):
        records = session_records()
        next(row for row in records if row.get("instrument_id") == 9101
             and row.get("record_type") == "trades" and row["ts_event"].startswith("2026-08-06T00:00:01"))["price"] = 0.
        files, replay = await self.prepare(records)
        metadata, messages = load_captured_session(replay["capture"])
        retained = next(row for row in messages if row.get("iv_source") == "prior_valid")
        self.assertEqual(retained["iv_provenance"]["prior_iv_age_ms"], 2000.)
        with patch("scripts.validate_full_session.quantlib_reference", return_value=None):
            valid = await validate_market(files=files, symbol="ES", capture=replay["capture"],
                                          conversion_report=replay["report"], output=self.root / "valid-retained")
        self.assertEqual(valid["iv_sources"]["prior_valid"], 1)
        for kind in ("time", "rate", "source"):
            with self.subTest(kind=kind):
                changed = copy.deepcopy(messages)
                provenance = next(row for row in changed if row.get("iv_source") == "prior_valid")["iv_provenance"]
                if kind == "time":
                    provenance["prior_iv_event_time"] = iso(ns(provenance["prior_iv_event_time"]) - 1)
                    provenance["prior_iv_age_ms"] += .000001
                elif kind == "rate":
                    provenance["prior_iv_risk_free_rate"] = .09
                else:
                    provenance["prior_iv_source"] = "provider"
                capture = self.root / ("fabricated-" + kind + ".gex-session.jsonl")
                writer = CapturedSessionWriter(capture, source=metadata["source"], model_inputs=metadata["model_inputs"])
                await writer.start()
                for message in changed:
                    await writer.append(message)
                await writer.finalize()
                with patch("scripts.validate_full_session.quantlib_reference", return_value=None):
                    with self.assertRaisesRegex(ValueError, "actual prior successful"):
                        await validate_market(files=files, symbol="ES", capture=capture,
                                              conversion_report=replay["report"], output=self.root / ("bad-prior-" + kind))

    def test_independent_scalar_and_nanosecond_fill_identity(self):
        price, gamma = black76(100, 100, 1, 0, .2, "C")
        self.assertAlmostEqual(price, 7.965567455405804, places=12)
        self.assertAlmostEqual(gamma, .01984762737385059, places=14)
        _, put_gamma = black76(100, 100, 1, 0, .2, "P")
        self.assertEqual(gamma, put_gamma)
        first = {"instrument_id": 42, "ts_event": "2026-08-06T00:00:00.000000001Z", "price": 12.5, "size": 1, "sequence": 8}
        second = {**first, "ts_event": "2026-08-06T00:00:00.000000002Z"}
        self.assertNotEqual(native_trade_fingerprint(first), native_trade_fingerprint(second))
        self.assertNotEqual(native_trade_fingerprint(first), native_trade_fingerprint({**first, "size": 2}))
        native = {**first, "ts_event": ns(first["ts_event"]), "price": 12_500_000_000}
        self.assertEqual(native_trade_fingerprint(first), native_trade_fingerprint(native, native=True))
        self.assertEqual(iso(ns(first["ts_event"])), first["ts_event"])
        expiry = ns("2026-08-06T01:00:00Z")
        precise = ns("2026-08-06T00:00:00.789677713Z")
        self.assertEqual(model_years(expiry, precise), model_years(expiry, precise - 713))
        self.assertNotEqual(model_years(expiry, precise), (expiry - precise) / (365 * 86400 * 1e9))


if __name__ == "__main__":
    unittest.main()

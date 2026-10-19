import copy
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.cli import compute_snapshot
from gex_terminal.config import GexConfig
from gex_terminal.session_capture import load_captured_session
from gex_terminal.session_intake import SessionIntake
from gex_terminal.wind_tunnel_checkpoint import validate_checkpoint
from scripts.databento_trial_replay import (
    _event_ns, _historical_underlying_record, convert_sample, prepare_records,
)


FIXTURE = Path(__file__).resolve().parents[1] / "gex_terminal/data/provider_fixtures/databento_mixed_offline_records.jsonl"


def _records(symbol="ES"):
    records = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
    if symbol == "NQ":
        for row in records:
            if row["record_type"] == "definition":
                row["raw_symbol"] = row["raw_symbol"].replace("ES", "NQ")
                row["asset"] = "NQ"
                row["unit_of_measure_qty"] = 20
    return records


def _files(base, records):
    roles = {"definitions": {"definition"}, "underlying": {"mbp-1", "bbo-1s"}, "trades": {"trades"}}
    result = {}
    for role, kind in roles.items():
        path = base / f"{role}.jsonl"
        rows = [row for row in records if row["record_type"] in kind]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        result[role] = path
    return result


def _config(symbol, capture):
    return GexConfig(
        symbol=symbol, symbols=(symbol,), data_mode="replay", data_provider="replay",
        contract_multiplier=50 if symbol == "ES" else 20, risk_free_rate=0.045,
        days_to_expiry=0.25, refresh_interval_seconds=1, stale_after_seconds=10,
        replay_path=str(capture), replay_delay_seconds=0, tradovate_environment="demo",
    )


class DatabentoTrialReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_bbo_interval_end_prevents_future_book_and_uses_midpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            records = _records()
            # Last sale predates the interval, but the book is only available
            # at 16:00:01. The option trade inside that interval uses the prior
            # book; the later trade uses its new midpoint rather than last sale.
            interval_quote = {
                **records[2], "record_type": "bbo-1s", "price": 9000.0,
                "bid_px_00": 6009.75, "ask_px_00": 6010.25,
                "ts_event": "2026-08-06T15:59:50Z", "ts_recv": "2026-08-06T16:00:01Z",
            }
            records[3]["ts_event"] = "2026-08-06T16:00:00.500000001Z"
            result = await convert_sample(
                files=_files(base, [*records, interval_quote]), symbol="ES", output_dir=base / "out",
            )
            _, messages = load_captured_session(result["capture"])
            trades = [message for message in messages if message["type"] == "options_volume_tick"]
            before, after = [message["iv_provenance"] for message in trades]
            self.assertEqual(before["underlying_price"], 6000.0)
            self.assertEqual(before["underlying_price_source"], "databento_mbp1_midpoint")
            self.assertEqual(after["underlying_price"], 6010.0)
            self.assertEqual(after["underlying_price_source"], "databento_bbo_1s_midpoint")
            self.assertEqual(after["underlying_event_time"], "2026-08-06T16:00:01Z")
            self.assertEqual(after["underlying_price_age_ms"], 500.0)
            bbo_tick = [message for message in messages if message.get("price_source") == "databento_bbo_1s_midpoint"][0]
            self.assertEqual(bbo_tick["price"], 6010.0)
            self.assertEqual(bbo_tick["quote_time_basis"], "interval_end")
            self.assertEqual(bbo_tick["provider_last_trade_ts_event"], "2026-08-06T15:59:50Z")

    def test_bbo_requires_valid_interval_end_but_last_trade_may_be_undefined(self):
        record = {
            "record_type": "bbo-1s", "instrument_id": 9200,
            "ts_event": (1 << 64) - 1, "ts_recv": "2026-08-06T16:00:01.000000001Z",
            "bid_px_00": 5999.75, "ask_px_00": 6000.25, "price": 7000,
        }
        converted = _historical_underlying_record(record)
        self.assertEqual(converted["provider_last_trade_ts_event"], (1 << 64) - 1)
        self.assertEqual(_event_ns(converted), _event_ns({"ts_event": record["ts_recv"]}))
        self.assertNotIn("price", converted)
        for value in (None, "2026-08-06T16:00:01", (1 << 64) - 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _historical_underlying_record({**record, "ts_recv": value})

    @unittest.skipUnless(importlib.util.find_spec("databento"), "optional Databento SDK not installed")
    async def test_real_sdk_bbo_dbn_uses_interval_time_and_records_sampling(self):
        import databento_dbn as dbn
        from scripts.verify_databento_functional import write_dbn
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            records = _records()
            for record in records[:2]:
                record["underlying"] = "ES"
                record["ts_event"] = "2026-08-06T15:59:59Z"
            files = _files(base, records)
            for role, kind in (("definitions", "definition"), ("trades", "trades")):
                path = base / f"{role}.dbn"
                write_dbn([row for row in records if row["record_type"] == kind], path)
                files[role] = path
            end_ns = _event_ns({"ts_event": "2026-08-06T16:00:01Z"})
            metadata = dbn.Metadata(
                dataset="GLBX.MDP3", start=end_ns - 1_000_000_000,
                stype_in=dbn.SType.RAW_SYMBOL, stype_out=dbn.SType.INSTRUMENT_ID,
                schema=dbn.Schema.BBO_1S, symbols=[],
            )
            quote = dbn.BBOMsg(
                rtype=dbn.RType.BBO_1S, publisher_id=1, instrument_id=9200,
                ts_event=dbn.UNDEF_TIMESTAMP, ts_recv=end_ns,
                price=7000_000_000_000, size=1, side=dbn.Side.BID,
                levels=dbn.BidAskPair(
                    bid_px=5999_750_000_000, ask_px=6000_250_000_000, bid_sz=1, ask_sz=1,
                ),
            )
            files["underlying"] = base / "underlying-bbo-1s.dbn"
            files["underlying"].write_bytes(metadata.encode() + bytes(quote))
            result = await convert_sample(files=files, symbol="ES", output_dir=base / "out")
            report = json.loads(result["report"].read_text())
            self.assertTrue(report["result"]["software_path_certified"])
            self.assertEqual(report["historical_provenance"]["underlying_schema"], "bbo-1s")
            self.assertIn("interval-end", report["historical_provenance"]["underlying_sampling"])
            metadata, messages = load_captured_session(result["capture"])
            self.assertEqual(metadata["event_count"], 3)
            self.assertEqual(messages[0]["price"], 6000.0)
            self.assertEqual(messages[0]["event_time"], "2026-08-06T16:00:01.000000000Z")
            self.assertTrue(all(
                message["iv_provenance"]["underlying_price_source"] == "databento_bbo_1s_midpoint"
                for message in messages[1:]
            ))

    async def test_es_and_nq_capture_round_trip_uses_production_app(self):
        for symbol in ("ES", "NQ"):
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                files = _files(base, list(reversed(_records(symbol))))
                with patch("gex_terminal.adapters.databento._load_databento_sdk", side_effect=AssertionError("no network client")):
                    result = await convert_sample(files=files, symbol=symbol, output_dir=base / "out")
                report = json.loads(result["report"].read_text())
                metadata, messages = load_captured_session(result["capture"])
                self.assertTrue(metadata["completed"])
                self.assertTrue(metadata["integrity_verified"])
                self.assertEqual(metadata["event_count"], 3)
                self.assertFalse(metadata["source"]["network_used"])
                self.assertEqual(metadata["source"]["source_kind"], "historical_databento")
                self.assertTrue(report["result"]["software_path_certified"])
                self.assertFalse(report["result"]["live_transport_certified"])
                self.assertEqual(report["coverage"]["inverted_iv_ticks"], 2)
                self.assertTrue(all(message["iv_source"] == "black_76_inverted" for message in messages[1:]))
                snapshot, _, _ = await compute_snapshot(_config(symbol, result["capture"]))
                self.assertEqual(snapshot["symbol"], symbol)
                self.assertAlmostEqual(snapshot["metrics"]["total_net_gex"], report["snapshot"]["metrics"]["total_net_gex"])
                self.assertEqual(snapshot["contract_multiplier"], 50 if symbol == "ES" else 20)
                self.assertEqual(stat.S_IMODE(result["capture"].stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(result["report"].stat().st_mode), 0o600)
                intake = SessionIntake()
                inspected = intake.inspect(result["capture"].read_bytes())
                checkpoint = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], inspected["default_sequence"]))
                self.assertEqual(inspected["symbol"], symbol)
                self.assertEqual(checkpoint["source"]["data_mode"], "REPLAY")

    async def test_other_future_is_explicitly_excluded_not_used_as_current_forward(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            records = _records()
            other = copy.deepcopy(records[0])
            other["instrument_id"], other["underlying_id"] = 999, 888
            trade = copy.deepcopy(records[-1])
            trade["instrument_id"] = 999
            files = _files(base, [*records, other, trade])
            result = await convert_sample(files=files, symbol="ES", output_dir=base / "out")
            report = json.loads(result["report"].read_text())
            subset = report["historical_provenance"]["subset"]
            self.assertEqual(subset["excluded_other_future_definitions"], 1)
            self.assertEqual(subset["excluded_option_events"], 1)
            self.assertEqual(report["coverage"]["option_trades"], 2)

    async def test_future_definition_is_not_applied_to_an_earlier_trade(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            records = _records()
            for row in records[:2]:
                row["ts_event"] = "2026-08-06T16:00:02Z"
            with self.assertRaisesRegex(ValueError, "usable snapshot"):
                await convert_sample(files=_files(base, records), symbol="ES", output_dir=base / "out")
            report = json.loads((base / "out/es-replay-report.json").read_text())
            self.assertEqual(report["coverage"]["option_trades"], 0)
            self.assertFalse((base / "out/es.gex-session.jsonl").exists())

    async def test_fail_closed_for_bad_schema_identity_timestamp_and_record_bounds(self):
        mutations = []
        mixed_future = _records()
        mixed_future.append({**mixed_future[2], "instrument_id": 123})
        mutations.append((mixed_future, {}, "exactly one"))
        wrong_root = _records()
        wrong_root[0]["asset"] = "NQ"
        mutations.append((wrong_root, {}, "another underlying"))
        missing_time = _records()
        del missing_time[-1]["ts_event"]
        mutations.append((missing_time, {}, "require provider event"))
        mutations.append((_records(), {"max_records": 4}, "max-records"))
        for records, kwargs, error in mutations:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                files = _files(base, records)
                with self.assertRaisesRegex(ValueError, error):
                    await convert_sample(files=files, symbol="ES", output_dir=base / "out", **kwargs)
                self.assertFalse((base / "out").exists())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            files = _files(base, _records())
            files["trades"] = files["underlying"]
            with self.assertRaisesRegex(ValueError, "another schema"):
                prepare_records(files, symbol="ES")

    async def test_optional_policy_is_validated_before_output_and_outputs_never_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            files = _files(base, _records())
            policy = base / "invalid-policy.json"
            policy.write_text("{}")
            with self.assertRaises(ValueError):
                await convert_sample(files=files, symbol="ES", output_dir=base / "out", capture_policy=policy)
            self.assertFalse((base / "out").exists())
            result = await convert_sample(files=files, symbol="ES", output_dir=base / "out")
            original = result["capture"].read_bytes()
            with self.assertRaises(FileExistsError):
                await convert_sample(files=files, symbol="ES", output_dir=base / "out")
            self.assertEqual(result["capture"].read_bytes(), original)

    def test_nanosecond_order_is_not_rounded_or_assumed_utc(self):
        earlier = {"ts_event": "2026-08-06T16:00:00.000000001Z"}
        later = {"ts_event": "2026-08-06T16:00:00.000000002Z"}
        self.assertEqual(_event_ns(later) - _event_ns(earlier), 1)
        self.assertEqual(_event_ns(earlier), _event_ns({"ts_event": "2026-08-06T12:00:00.000000001-04:00"}))
        with self.assertRaisesRegex(ValueError, "timezone"):
            _event_ns({"ts_event": "2026-08-06T16:00:00"})
        with self.assertRaises(ValueError):
            _event_ns({"ts_event": (1 << 64) - 1})

    @unittest.skipUnless(importlib.util.find_spec("databento"), "optional Databento SDK not installed")
    async def test_real_sdk_dbn_records_convert_without_an_api_key(self):
        from scripts.verify_databento_functional import write_dbn
        import zstandard
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            records = _records()
            for record in records[:2]:
                record["underlying"] = "ES"
                record["ts_event"] = "2026-08-06T15:59:59Z"
            files = {}
            for role, kind in (("definitions", "definition"), ("underlying", "mbp-1"), ("trades", "trades")):
                path = base / f"{role}.dbn"
                write_dbn([row for row in records if row["record_type"] == kind], path)
                files[role] = path
            result = await convert_sample(files=files, symbol="ES", output_dir=base / "out")
            report = json.loads(result["report"].read_text())
            self.assertTrue(report["result"]["software_path_certified"])
            self.assertEqual(load_captured_session(result["capture"])[0]["event_count"], 3)
            compressed = {}
            for role, path in files.items():
                target = path.with_suffix(".dbn.zst")
                target.write_bytes(zstandard.ZstdCompressor().compress(path.read_bytes()))
                compressed[role] = target
            result = await convert_sample(files=compressed, symbol="ES", output_dir=base / "compressed")
            self.assertEqual(load_captured_session(result["capture"])[0]["event_count"], 3)
            files["trades"].write_bytes(files["trades"].read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "truncated"):
                await convert_sample(files=files, symbol="ES", output_dir=base / "truncated")
            self.assertFalse((base / "truncated").exists())


if __name__ == "__main__":
    unittest.main()

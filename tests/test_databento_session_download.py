"""Full-session quotes and credit-gated acquisitions use exact bounded requests."""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

from scripts import databento_session_download as session
from scripts.databento_trial_download import TrialRequestError, TrialSetupError


NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
DAY = "2026-10-16"
IDENTITIES = {symbol: {"instrument_id": number, "cached_sha256": "a" * 64,
                       "cached_schema": "bbo-1s", "cached_symbol": symbol + ".v.0"}
              for symbol, number in (("ES", 10252), ("NQ", 261401))}
FAKE_KEY = "db-" + "Z" * 29


class FakeStore:
    def __init__(self, count=2, *, warning=False):
        self.count, self.warning = count, warning
        self.reader = SimpleNamespace(close=Mock())

    def __iter__(self):
        for _ in range(self.count):
            yield object()
        if self.warning:
            warnings.warn("DBN file is truncated", UserWarning)


def client(*, costs=.1, count=10, size=1000, actual=2):
    stores = []
    def download(**kwargs):
        Path(kwargs["path"]).write_bytes(b"synthetic DBN")
        result = FakeStore(actual)
        stores.append(result)
        return result
    result = SimpleNamespace(
        metadata=SimpleNamespace(
            get_dataset_range=Mock(return_value={"start": "2010-01-01T00:00:00Z", "end": "2026-10-19T00:00:00Z"}),
            get_record_count=Mock(return_value=count), get_billable_size=Mock(return_value=size),
            get_cost=Mock(return_value=costs)),
        timeseries=SimpleNamespace(get_range=Mock(side_effect=download)), stores=stores)
    return result


class ProviderError(Exception):
    http_status = 422
    json_body = {"detail": {"case": "data_end_after_available_end", "message": FAKE_KEY}}

    def __str__(self):
        return "secret https://provider.invalid/?key=" + FAKE_KEY


class SessionDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gex-session-acquisition-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "acquisition"

    def plan(self, service=None):
        return session.quote_plan(service or client(), DAY, IDENTITIES, now=NOW)

    def download(self, service, plan=None, **options):
        return session.download_plan(service, plan or self.plan(), self.output,
                                     credits_remaining=options.pop("credits_remaining", 124.82),
                                     max_cost=options.pop("max_cost", 5),
                                     use_credits=options.pop("use_credits", True), now=NOW, **options)

    def test_exact_23_hour_window_all_parents_causal_definitions_and_fixed_futures(self):
        service = client()
        plan = self.plan(service)
        self.assertEqual(plan["window"], {"start": "2026-10-15T22:00:00Z", "end": "2026-10-16T21:00:00Z",
                                         "definition_start": "2026-10-14T00:00:00Z", "underlying_start": "2026-10-15T21:59:58Z"})
        for market in plan["markets"]:
            symbol = market["symbol"]
            self.assertEqual(len(market["option_parents"]), 26)
            definition, underlying, trades = [item["request"] for item in market["requests"]]
            self.assertEqual(definition["symbols"], list(session.databento_option_parent_symbols(symbol)) + [symbol + ".FUT"])
            self.assertEqual(definition["end"], plan["window"]["end"])
            self.assertEqual(trades["symbols"], market["option_parents"])
            self.assertEqual(underlying["stype_in"], "instrument_id")
            self.assertEqual(underlying["symbols"], [IDENTITIES[symbol]["instrument_id"]])
            self.assertTrue(all(item["request"]["limit"] == item["record_count"] + 1 for item in market["requests"]))
        service.timeseries.get_range.assert_not_called()
        self.assertEqual(service.metadata.get_cost.call_count, 6)
        self.assertIn("no_OI", plan["coverage"])

    def test_winter_timezone_and_nonhistorical_or_weekend_dates(self):
        window = session.session_window("2026-01-16", now=NOW)
        self.assertEqual(window["start"], "2026-01-15T23:00:00Z")
        self.assertEqual(window["end"], "2026-01-16T22:00:00Z")
        for value in ("2026-10-19", "2026-10-17", "2026-1-2", "nonsense"):
            with self.subTest(value=value), self.assertRaises(TrialSetupError):
                session.session_window(value, now=NOW)

    def test_metadata_bounds_counts_sizes_and_costs_fail_before_data(self):
        for field, values in (("get_record_count", [0, True, 1.0, 5_000_001]),
                              ("get_billable_size", [0, True, -1]),
                              ("get_cost", [float("nan"), float("inf"), -1, True])):
            for value in values:
                service = client()
                getattr(service.metadata, field).return_value = value
                with self.subTest(field=field, value=value), self.assertRaises(TrialSetupError):
                    self.plan(service)
                service.timeseries.get_range.assert_not_called()
        service = client(count=2_000_000)
        with self.assertRaisesRegex(TrialSetupError, "market bound"):
            self.plan(service)
        service = client()
        service.metadata.get_dataset_range.return_value["end"] = "2026-10-16T20:00:00Z"
        with self.assertRaisesRegex(TrialSetupError, "outside dataset"):
            self.plan(service)

    def test_over_budget_quote_is_retained_without_narrower_fallback_or_download(self):
        service = client(costs=1)
        plan = self.plan(service)
        self.assertEqual(plan["status"], "over_budget")
        path = self.root / "quote.json"
        session.private_json(path, plan)
        self.assertEqual(json.loads(path.read_text())["estimated_total_usd"], 6)
        with self.assertRaisesRegex(TrialSetupError, "narrower fallback"):
            self.download(service, plan)
        service.timeseries.get_range.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_hash_and_reconstructed_scope_reject_changed_requests_even_if_rehashed(self):
        original = self.plan()
        for mutate in (
                lambda p: p["markets"][0]["requests"][2]["request"].update(end="2026-10-16T21:01:00Z"),
                lambda p: p["markets"][1]["requests"][1]["request"].update(stype_in="continuous"),
                lambda p: p["markets"][0]["option_parents"].pop(),
                lambda p: p["dataset_availability"].update(end="2026-10-16T20:00:00Z"),
                lambda p: p.update(calendar="arbitrary new scope"),
                lambda p: p.update(max_records_per_market=10_000_000)):
            for rehash in (False, True):
                plan = deepcopy(original)
                mutate(plan)
                if rehash:
                    plan["plan_sha256"] = session._digest(plan)
                with self.subTest(rehash=rehash), self.assertRaises(TrialSetupError):
                    session.validate_plan(plan, now=NOW)

    def test_all_fresh_quotes_precede_any_download_and_source_plan_is_unchanged(self):
        service = client()
        plan = self.plan()
        before = deepcopy(plan)
        original = service.timeseries.get_range.side_effect
        def guarded(**kwargs):
            self.assertEqual(service.metadata.get_cost.call_count, 6)
            self.assertEqual(service.metadata.get_record_count.call_count, 6)
            return original(**kwargs)
        service.timeseries.get_range.side_effect = guarded
        result = self.download(service, plan)
        self.assertEqual(plan, before)
        self.assertEqual(result["status"], "download_complete")
        self.assertEqual(len(result["files"]), 6)
        self.assertAlmostEqual(result["attempted_quote_usd"], .6)
        self.assertIsNone(result["billing_actual_usd"])
        for item, call in zip(result["files"], service.timeseries.get_range.call_args_list):
            request = dict(call.kwargs)
            path = request.pop("path")
            self.assertEqual(request, item["request"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for path in self.output.glob("*.json"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertTrue(all(store.reader.close.called for store in service.stores))
        calls = service.metadata.get_cost.call_count
        with self.assertRaisesRegex(TrialSetupError, "already exists"):
            self.download(service, plan)
        self.assertEqual(service.metadata.get_cost.call_count, calls)

    def test_ack_budget_balance_and_metadata_drift_block_all_downloads(self):
        for options in ({"use_credits": False}, {"max_cost": 6}, {"max_cost": .2},
                        {"credits_remaining": .2}, {"credits_remaining": float("nan")}):
            service = client()
            with self.subTest(options=options), self.assertRaises(TrialSetupError):
                self.download(service, **options)
            service.timeseries.get_range.assert_not_called()
            self.assertFalse(self.output.exists())
        service = client(count=11)
        with self.assertRaisesRegex(TrialSetupError, "metadata changed"):
            self.download(service, self.plan())
        service.timeseries.get_range.assert_not_called()
        service = client(costs=1)
        with self.assertRaisesRegex(TrialSetupError, "Fresh total"):
            self.download(service, self.plan())
        service.timeseries.get_range.assert_not_called()

    def test_failed_download_keeps_safe_attempt_ledger_without_retry(self):
        service = client()
        def fail(**kwargs):
            Path(kwargs["path"]).write_bytes(b"retained partial bytes")
            raise ProviderError()
        service.timeseries.get_range.side_effect = fail
        with self.assertRaises(TrialRequestError) as caught:
            self.download(service)
        self.assertNotIn(FAKE_KEY, str(caught.exception))
        self.assertIn("HTTP 422", str(caught.exception))
        self.assertEqual(service.timeseries.get_range.call_count, 1)
        stopped = json.loads((self.output / "download-stopped.json").read_text())
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(stopped["attempted_quote_usd"], .1)
        self.assertTrue((self.output / "progress-00-before.json").exists())
        self.assertFalse((self.output / "progress-00-complete.json").exists())
        self.assertTrue((self.output / "es" / "definitions.dbn").exists())
        self.assertNotIn(FAKE_KEY, (self.output / "download-stopped.json").read_text())

    def test_empty_limit_reaching_and_truncated_files_stop_and_close_reader(self):
        for count, truncated in ((0, False), (11, False), (2, True)):
            service = client()
            stores = []
            def download(**kwargs):
                Path(kwargs["path"]).write_bytes(b"synthetic")
                store = FakeStore(count, warning=truncated)
                stores.append(store)
                return store
            service.timeseries.get_range.side_effect = download
            self.output = self.root / f"stop-{count}-{truncated}"
            with self.subTest(count=count, truncated=truncated), self.assertRaises(TrialRequestError):
                self.download(service)
            self.assertEqual(service.timeseries.get_range.call_count, 1)
            self.assertTrue(stores[0].reader.close.called)
            self.assertFalse((self.output / "download-complete.json").exists())

    def test_compressed_output_bound_stops_the_sdk_write_and_restores_process_limit(self):
        import resource
        previous = resource.getrlimit(resource.RLIMIT_FSIZE)
        service = client()
        def oversized(**kwargs):
            Path(kwargs["path"]).write_bytes(b"x" * 65)
            return FakeStore()
        service.timeseries.get_range.side_effect = oversized
        with patch.object(session, "MAX_COMPRESSED_BYTES", 64):
            plan = self.plan()
            with self.assertRaises(TrialRequestError):
                self.download(service, plan)
        self.assertLessEqual((self.output / "es" / "definitions.dbn").stat().st_size, 64)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_FSIZE), previous)
        self.assertEqual(service.timeseries.get_range.call_count, 1)

    def test_private_atomic_receipts_refuse_overwrite_symlinks_and_duplicate_json_fields(self):
        path = self.root / "quote.json"
        session.private_json(path, self.plan())
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            session.private_json(path, {"overwrite": True})
        self.assertEqual(path.read_bytes(), before)
        link = self.root / "link.json"
        link.symlink_to(path)
        with self.assertRaises(OSError):
            session.read_plan(link)
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(ValueError):
            session.read_plan(duplicate)

    def test_cached_id_requires_matching_symbol_single_identity_and_complete_decode(self):
        source = self.root / "underlying.dbn"
        source.write_bytes(b"synthetic cached BBO")
        store = SimpleNamespace(metadata=SimpleNamespace(schema="bbo-1s", symbols=["ES.v.0"]),
                                reader=SimpleNamespace(close=Mock()))
        class Cached:
            metadata, reader = store.metadata, store.reader
            def __iter__(self):
                return iter([SimpleNamespace(instrument_id=10252)] * 2)
        identity = session.cached_underlying_identity(source, "ES", store_factory=lambda _: Cached())
        self.assertEqual(identity["instrument_id"], 10252)
        self.assertTrue(store.reader.close.called)
        with self.assertRaisesRegex(TrialSetupError, "selected market"):
            session.cached_underlying_identity(source, "NQ", store_factory=lambda _: Cached())

    def test_cli_unauthorized_download_refuses_before_loading_key(self):
        with patch.object(session, "read_key") as key, patch("sys.stdout", io.StringIO()):
            status = session.main(["download", "--plan", "unused.json", "--output", str(self.output),
                                   "--credits-remaining", "124.82"])
        self.assertEqual(status, 2)
        key.assert_not_called()


if __name__ == "__main__":
    unittest.main()

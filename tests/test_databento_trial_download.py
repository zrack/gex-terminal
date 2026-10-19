"""Budget, exact-request, privacy and offline setup contracts for the trial."""

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import databento_trial_download as trial


START = "2026-10-16T13:35:00Z"
NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
FAKE_KEY = "db-" + "A" * 29


def fake_client(costs=(0.1, 0.2, 0.3)):
    def download(**kwargs):
        Path(kwargs["path"]).write_bytes(b"synthetic DBN placeholder")
        return [{"synthetic": True}]
    return SimpleNamespace(
        metadata=SimpleNamespace(get_cost=Mock(side_effect=costs)),
        timeseries=SimpleNamespace(get_range=Mock(side_effect=download)),
    )


class FakeProviderError(Exception):
    def __init__(self, case="data_end_after_available_end"):
        super().__init__(f"https://provider.invalid/?key={FAKE_KEY}")
        self.http_status = 422
        self.json_body = {"detail": {"case": case, "message": FAKE_KEY, "docs": FAKE_KEY}}
        self.headers = {"Authorization": FAKE_KEY}
        self.request_id = FAKE_KEY


class DatabentoTrialDownloadTests(unittest.TestCase):
    def setUp(self):
        self.requests = trial.build_requests("ES", START, now=NOW)

    def test_nq_scope_and_no_definition_lookahead(self):
        requests = trial.build_requests("NQ", START, now=NOW)
        self.assertEqual(requests[0]["symbols"], ["NQ.OPT", "NQ.FUT"])
        self.assertEqual(requests[0]["end"], START)
        self.assertEqual(requests[1]["symbols"], ["NQ.v.0"])
        self.assertEqual(requests[1]["schema"], "bbo-1s")
        self.assertEqual(requests[2]["end"], "2026-10-16T13:36:00Z")
        self.assertTrue(all(r["dataset"] == "GLBX.MDP3" for r in requests))
        self.assertTrue(all(r["limit"] == 60000 for r in requests))

    def test_mbp_1_remains_an_explicit_underlying_option(self):
        requests = trial.build_requests("NQ", START, underlying_schema="mbp-1", now=NOW)
        self.assertEqual(requests[1]["schema"], "mbp-1")
        self.assertEqual(requests[1]["start"], "2026-10-16T13:34:58Z")
        self.assertEqual(requests[1]["end"], "2026-10-16T13:36:00Z")
        with self.assertRaises(trial.TrialSetupError):
            trial.build_requests("NQ", START, underlying_schema="invalid", now=NOW)

    def test_timezone_equivalence_and_invalid_windows(self):
        self.assertEqual(self.requests, trial.build_requests("ES", "2026-10-16T06:35:00-07:00", now=NOW))
        for value in ("2026-10-16T13:35:00", "2026-10-19T00:00:00Z", "2026-10-17T13:35:00Z", "bad"):
            with self.subTest(value=value), self.assertRaises(trial.TrialSetupError):
                trial.build_requests("ES", value, now=NOW)

    def test_quote_never_downloads_and_preserves_parameters(self):
        client = fake_client()
        self.assertEqual(trial.quote_requests(client, self.requests), [0.1, 0.2, 0.3])
        self.assertEqual([c.kwargs for c in client.metadata.get_cost.call_args_list], self.requests)
        client.timeseries.get_range.assert_not_called()

    def test_invalid_quotes_never_download(self):
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(trial.TrialSetupError):
                trial.quote_requests(fake_client((value, 0, 0)), self.requests)

    def test_quote_failure_reports_schema_status_and_allowlisted_case_only(self):
        client = fake_client((0.1, FakeProviderError(), 0.3))
        with self.assertRaises(trial.TrialRequestError) as caught:
            trial.quote_requests(client, self.requests)
        message = str(caught.exception)
        self.assertIn("quote failed for bbo-1s", message)
        self.assertIn("HTTP 422", message)
        self.assertIn("case data_end_after_available_end", message)
        self.assertNotIn(FAKE_KEY, message)
        self.assertNotIn("provider.invalid", message)
        self.assertEqual(client.metadata.get_cost.call_count, 2)
        client.timeseries.get_range.assert_not_called()

    def test_unknown_provider_diagnostics_are_not_printed(self):
        for case in (FAKE_KEY, "account_jane", {"secret": FAKE_KEY}):
            error = trial.TrialRequestError("quote", "trades", FakeProviderError(case))
            self.assertIn("HTTP 422", str(error))
            self.assertIsNone(error.provider_case)
            self.assertNotIn(FAKE_KEY, str(error))
            self.assertNotIn("account_jane", str(error))
        error = trial.TrialRequestError("quote", "trades", RuntimeError(FAKE_KEY))
        self.assertIn("quote failed for trades", str(error))
        self.assertNotIn(FAKE_KEY, str(error))

    def test_budget_and_credits_stop_all_downloads(self):
        for ceiling, balance, ack in ((0.5, 125, True), (1, 0.2, True), (1, 125, False), (6, 125, True), (1, 0, True)):
            with tempfile.TemporaryDirectory() as tmp:
                client = fake_client()
                output = Path(tmp) / "trial"
                with self.subTest(ceiling=ceiling, balance=balance, ack=ack), self.assertRaises(trial.TrialSetupError):
                    trial.download_requests(client, self.requests, symbol="ES", max_cost=ceiling,
                                            credits_remaining=balance, acknowledge=ack, output_dir=output)
                client.timeseries.get_range.assert_not_called()
                self.assertFalse(output.exists())

    def test_download_matches_quote_private_manifest_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = fake_client()
            output = Path(tmp) / "trial"
            result = trial.download_requests(client, self.requests, symbol="ES", max_cost=1,
                                             credits_remaining=125, acknowledge=True, output_dir=output)
            self.assertEqual(result["status"], "download_complete")
            self.assertEqual(result["record_counts"], {"definition": 1, "bbo-1s": 1, "trades": 1})
            self.assertEqual(result["underlying_schema"], "bbo-1s")
            self.assertEqual(result["underlying_sampling"], "one-second BBO snapshots")
            self.assertFalse(result["live_certified"])
            self.assertIn("no OI", result["coverage"])
            for index, call in enumerate(client.timeseries.get_range.call_args_list):
                parameters = dict(call.kwargs)
                path = parameters.pop("path")
                self.assertEqual(parameters, self.requests[index])
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual(json.loads((output / "download-complete.json").read_text())["replay_start"], START)
            with self.assertRaises(trial.TrialSetupError):
                trial.download_requests(client, self.requests, symbol="ES", max_cost=1,
                                        credits_remaining=125, acknowledge=True, output_dir=output)
            self.assertEqual(client.timeseries.get_range.call_count, 3)

    def test_empty_or_truncated_stream_stops_without_completion(self):
        for count in (0, trial.RECORD_LIMIT):
            with tempfile.TemporaryDirectory() as tmp:
                client = fake_client()
                def download(**kwargs):
                    Path(kwargs["path"]).write_bytes(b"synthetic")
                    return iter(range(count))
                client.timeseries.get_range.side_effect = download
                output = Path(tmp) / "trial"
                with self.subTest(count=count), self.assertRaises(trial.TrialSetupError):
                    trial.download_requests(client, self.requests, symbol="ES", max_cost=1,
                                            credits_remaining=125, acknowledge=True, output_dir=output)
                self.assertFalse((output / "download-complete.json").exists())
                self.assertTrue((output / "download-stopped.json").exists())
                self.assertEqual(client.timeseries.get_range.call_count, 1)

    def test_download_failure_saves_private_safe_stop_and_explains_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nq-trial"
            client = fake_client()
            def fail_download(**kwargs):
                Path(kwargs["path"]).write_bytes(b"retained partial data")
                raise FakeProviderError()
            client.timeseries.get_range.side_effect = fail_download
            with self.assertRaisesRegex(trial.TrialRequestError, "download failed for definition.*HTTP 422"):
                trial.download_requests(client, self.requests, symbol="NQ", max_cost=1,
                                        credits_remaining=125, acknowledge=True, output_dir=output)
            stopped = output / "download-stopped.json"
            manifest = json.loads(stopped.read_text())
            self.assertEqual(manifest["status"], "stopped_request_error")
            self.assertEqual(manifest["stopped_stage"], "download")
            self.assertEqual(manifest["stopped_schema"], "definition")
            self.assertEqual(manifest["http_status"], 422)
            self.assertEqual(manifest["provider_case"], "data_end_after_available_end")
            self.assertEqual(stat.S_IMODE(stopped.stat().st_mode), 0o600)
            self.assertNotIn(FAKE_KEY, stopped.read_text())
            self.assertFalse((output / "download-complete.json").exists())
            self.assertEqual((output / "definitions.dbn").read_bytes(), b"retained partial data")
            before = stopped.read_bytes()
            with self.assertRaises(trial.TrialSetupError) as caught:
                trial.download_requests(client, self.requests, symbol="NQ", max_cost=1,
                                        credits_remaining=125, acknowledge=True, output_dir=output)
            message = str(caught.exception)
            self.assertIn("NQ trial directory already exists", message)
            self.assertIn(str(output), message)
            self.assertIn("Previous stop: download for definition", message)
            self.assertEqual(stopped.read_bytes(), before)
            self.assertEqual(client.metadata.get_cost.call_count, 3)
            self.assertEqual(client.timeseries.get_range.call_count, 1)

    def test_stream_validation_failure_records_stage_without_exception_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "trial"
            client = fake_client()
            def fail_validation(**kwargs):
                Path(kwargs["path"]).write_bytes(b"invalid stream")
                def records():
                    yield object()
                    raise RuntimeError(FAKE_KEY)
                return records()
            client.timeseries.get_range.side_effect = fail_validation
            with self.assertRaisesRegex(trial.TrialRequestError, "validation failed for definition") as caught:
                trial.download_requests(client, self.requests, symbol="ES", max_cost=1,
                                        credits_remaining=125, acknowledge=True, output_dir=output)
            self.assertNotIn(FAKE_KEY, str(caught.exception))
            manifest = json.loads((output / "download-stopped.json").read_text())
            self.assertEqual(manifest["stopped_stage"], "validation")
            self.assertEqual(manifest["stopped_schema"], "definition")
            self.assertNotIn(FAKE_KEY, json.dumps(manifest))
            self.assertFalse((output / "download-complete.json").exists())
            self.assertEqual(client.timeseries.get_range.call_count, 1)

    def test_existing_output_ignores_untrusted_or_linked_stop_information(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "trial"
            output.mkdir()
            stopped = output / "download-stopped.json"
            manifest = {"schema": trial.MANIFEST_SCHEMA, "status": "stopped_request_error",
                        "stopped_stage": FAKE_KEY, "stopped_schema": "definition"}
            stopped.write_text(json.dumps(manifest))
            message = trial.existing_output_message(output, "ES")
            self.assertNotIn(FAKE_KEY, message)
            self.assertNotIn("Previous stop", message)
            stopped.unlink()
            outside = Path(tmp) / "outside.json"
            manifest["stopped_stage"] = "download"
            outside.write_text(json.dumps(manifest))
            stopped.symlink_to(outside)
            self.assertNotIn("Previous stop", trial.existing_output_message(output, "ES"))

    def test_key_is_literal_and_requires_owner_only_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            trial.private_write(path, f"DATABENTO_API_KEY={FAKE_KEY}\n")
            self.assertEqual(trial.read_key(path), FAKE_KEY)
            os.chmod(path, 0o644)
            with self.assertRaises(trial.TrialSetupError):
                trial.read_key(path)
            os.chmod(path, 0o600)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(trial.TrialSetupError):
                trial.read_key(link)
            with self.assertRaises(FileExistsError):
                trial.private_write(path, "do not replace")
            self.assertEqual(trial.read_key(path), FAKE_KEY)

    def test_provider_exception_never_prints_secret(self):
        for error in (ValueError(FAKE_KEY), RuntimeError(FAKE_KEY)):
            buffer = io.StringIO()
            with patch.object(trial, "read_key", return_value=FAKE_KEY), patch.object(
                trial, "build_requests", side_effect=error
            ), contextlib.redirect_stdout(buffer):
                self.assertEqual(trial.main(["quote", "--start", START]), 2)
            self.assertNotIn(FAKE_KEY, buffer.getvalue())

    def test_check_makes_no_client_and_download_needs_ack(self):
        client = Mock()
        with patch.object(trial, "read_key", return_value=FAKE_KEY), patch.dict(
            "sys.modules", {"databento": SimpleNamespace(Historical=client)}
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(trial.main(["check"]), 0)
                self.assertEqual(trial.main(["download", "--start", START]), 2)
            client.assert_not_called()

    def test_cli_quote_and_download_match_sampling_and_preserve_legacy_output(self):
        original_build_requests = trial.build_requests
        def historical_requests(symbol, start, **kwargs):
            return original_build_requests(symbol, start, now=NOW, **kwargs)
        for schema in ("bbo-1s", "mbp-1"):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as tmp:
                client = fake_client((0.1, 0.2, 0.3) * 2)
                arguments = ["--symbol", "NQ", "--start", START]
                if schema == "mbp-1":
                    arguments += ["--underlying-schema", schema]
                with patch.object(trial, "read_key", return_value=FAKE_KEY), patch.object(
                    trial, "DATA_ROOT", Path(tmp)
                ), patch.object(trial, "build_requests", side_effect=historical_requests), patch.dict(
                    "sys.modules", {"databento": SimpleNamespace(Historical=Mock(return_value=client))}
                ), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(trial.main(["quote", *arguments]), 0)
                    self.assertEqual(trial.main([
                        "download", *arguments, "--use-credits", "--credits-remaining", "125"
                    ]), 0)
                suffix = "-bbo-1s" if schema == "bbo-1s" else ""
                output = Path(tmp) / f"nq-20261016T133500Z{suffix}"
                manifest = json.loads((output / "download-complete.json").read_text())
                self.assertEqual(manifest["underlying_schema"], schema)
                estimates = client.metadata.get_cost.call_args_list
                self.assertEqual(estimates[:3], estimates[3:])
                self.assertEqual(estimates[1].kwargs["schema"], schema)
                for quote, download in zip(estimates[:3], client.timeseries.get_range.call_args_list):
                    parameters = dict(download.kwargs)
                    parameters.pop("path")
                    self.assertEqual(quote.kwargs, parameters)

    def test_cli_reports_safe_quote_failure_without_secrets(self):
        client = fake_client((FakeProviderError(),))
        buffer = io.StringIO()
        with patch.object(trial, "read_key", return_value=FAKE_KEY), patch.object(
            trial, "build_requests", return_value=self.requests
        ), patch.dict(
            "sys.modules", {"databento": SimpleNamespace(Historical=Mock(return_value=client))}
        ), contextlib.redirect_stdout(buffer):
            self.assertEqual(trial.main(["quote", "--start", START]), 2)
        self.assertIn("Setup stopped: Historical quote failed for definition (HTTP 422", buffer.getvalue())
        self.assertNotIn(FAKE_KEY, buffer.getvalue())
        client.timeseries.get_range.assert_not_called()


if __name__ == "__main__":
    unittest.main()

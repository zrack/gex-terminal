import copy
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from gex_terminal.cli import main_sync
from gex_terminal.databento_certification_policy import (
    ES_PRELIVE_V1,
    certification_policy_identity,
)
from gex_terminal.live_population_contract import (
    LIVE_POPULATION_CANONICALIZATION,
    LIVE_POPULATION_EVIDENCE_CEILING,
    LIVE_POPULATION_PLAN_SCHEMA,
    LIVE_POPULATION_RESULT_SCHEMA,
    LivePopulationContractError,
    live_population_plan_identity,
    live_population_result_identity,
    load_live_population_plan,
    load_live_population_result_manifest,
    validate_live_population_plan,
    validate_live_population_result_manifest,
)
from gex_terminal.package_data import provider_fixture_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")


def _valid_plan() -> dict:
    windows = (
        "globex",
        "regular_open",
        "midday",
        "regular_close",
        "globex",
        "regular_open",
        "midday",
        "regular_close",
        "globex",
        "regular_open",
        "midday",
        "regular_close",
    )
    slots = []
    first = datetime(2026, 10, 5, 1, 0, tzinfo=timezone.utc)
    for index, window in enumerate(windows):
        day_index = index // 3
        intra_day_hours = (1, 10, 18)[index % 3]
        start = (first + timedelta(days=day_index)).replace(hour=intra_day_hours)
        slots.append(
            {
                "run_id": f"gex-live-002-es-p001-run-{index + 1:02d}",
                "window": window,
                "trading_date": (date(2026, 10, 5) + timedelta(days=day_index)).isoformat(),
                "start_utc": _utc(start),
                "end_utc": _utc(start + timedelta(minutes=20)),
                "calendar_context": (
                    "scheduled_event" if day_index == 2 else "ordinary"
                ),
                "restart_observation": index in {0, 3},
            }
        )
    return {
        "schema": LIVE_POPULATION_PLAN_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "population_id": "gex-live-002-es-p001",
        "target": {
            "provider": "databento",
            "dataset": "GLBX.MDP3",
            "symbol": "ES",
            "canonical_contract_multiplier": 50.0,
        },
        "certification_policy": certification_policy_identity(ES_PRELIVE_V1),
        "runtime": {
            "gex_terminal_version": "0.5.0",
            "python_version": "3.12.11",
            "provider_sdk_version": "0.83.0",
            "operating_system": "macOS 15.6.1",
            "architecture": "arm64",
        },
        "authority": {
            "operator_alias": "operator-001",
            "reviewer_alias": "reviewer-001",
            "approval_reference": "owner-approval-2026-10-01",
            "entitlement_scope": "GLBX.MDP3 read-only ES observation",
            "rights_reference": "rights-review-2026-10-01",
            "retention_reference": "retention-review-2026-10-01",
            "read_only_provider_access": True,
            "raw_capture": False,
        },
        "timing": {
            "timezone": "UTC",
            "clock_source": "system UTC synchronized before each attempt",
            "exchange_calendar_source": "CME calendar reviewed 2026-10-01",
            "stale_response": "stop, retain failure, and do not restart the counter",
        },
        "lineage": {
            "status": "first_population",
            "prior_population_id": None,
            "prior_result_manifest_sha256": None,
        },
        "coverage_limitations": [
            "Calendar labels are declarations and do not establish a market regime."
        ],
        "planned_slots": slots,
        "evidence_ceiling": LIVE_POPULATION_EVIDENCE_CEILING,
    }


def _valid_results(plan: dict) -> dict:
    identity = live_population_plan_identity(plan)
    observations = []
    for slot in plan["planned_slots"]:
        observations.append(
            {
                "run_id": slot["run_id"],
                "outcome": "passed",
                "actual_start_utc": slot["start_utc"],
                "actual_stop_utc": slot["end_utc"],
                "runtime": copy.deepcopy(plan["runtime"]),
                "certification_policy_sha256": plan["certification_policy"][
                    "sha256"
                ],
                "report": {
                    "status": "produced",
                    "sha256": hashlib.sha256(slot["run_id"].encode()).hexdigest(),
                },
                "redacted_notes": "",
            }
        )
    return {
        "schema": LIVE_POPULATION_RESULT_SCHEMA,
        "canonicalization": LIVE_POPULATION_CANONICALIZATION,
        "plan_identity": identity,
        "observations": observations,
        "evidence_ceiling": LIVE_POPULATION_EVIDENCE_CEILING,
    }


class LivePopulationPlanTests(unittest.TestCase):
    def test_valid_plan_has_stable_complete_identity(self):
        plan = _valid_plan()
        reordered = {key: plan[key] for key in reversed(tuple(plan))}

        normalized = validate_live_population_plan(plan)
        self.assertEqual(
            live_population_plan_identity(normalized),
            live_population_plan_identity(reordered),
        )
        changed = copy.deepcopy(plan)
        changed["coverage_limitations"].append(
            "Scheduled-event labels are not volatility measurements."
        )
        self.assertNotEqual(
            live_population_plan_identity(plan)["sha256"],
            live_population_plan_identity(changed)["sha256"],
        )

    def test_plan_requires_registered_es_policy_identity_and_target(self):
        for mutation in ("policy", "symbol", "multiplier"):
            with self.subTest(mutation=mutation):
                plan = _valid_plan()
                if mutation == "policy":
                    plan["certification_policy"]["sha256"] = "0" * 64
                elif mutation == "symbol":
                    plan["target"]["symbol"] = "NQ"
                else:
                    plan["target"]["canonical_contract_multiplier"] = 20.0
                with self.assertRaises(LivePopulationContractError):
                    validate_live_population_plan(plan)

    def test_plan_slots_fail_closed_on_population_shape_drift(self):
        mutations = {}

        missing = _valid_plan()
        missing["planned_slots"].pop()
        mutations["missing slot"] = missing

        duration = _valid_plan()
        start = datetime.strptime(
            duration["planned_slots"][0]["start_utc"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        duration["planned_slots"][0]["end_utc"] = _utc(
            start + timedelta(minutes=19)
        )
        mutations["wrong duration"] = duration

        windows = _valid_plan()
        windows["planned_slots"][0]["window"] = "midday"
        mutations["wrong window counts"] = windows

        overlap = _valid_plan()
        overlap["planned_slots"][1]["start_utc"] = overlap["planned_slots"][0][
            "start_utc"
        ]
        overlap["planned_slots"][1]["end_utc"] = overlap["planned_slots"][0][
            "end_utc"
        ]
        mutations["overlap"] = overlap

        dates = _valid_plan()
        for slot in dates["planned_slots"]:
            slot["trading_date"] = "2026-10-05"
        mutations["too few trading dates"] = dates

        restart = _valid_plan()
        restart["planned_slots"][3]["trading_date"] = restart["planned_slots"][0][
            "trading_date"
        ]
        mutations["restart same date"] = restart

        for label, plan in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(LivePopulationContractError):
                    validate_live_population_plan(plan)

    def test_runtime_and_owner_decisions_reject_placeholders(self):
        for path, value in (
            (("runtime", "python_version"), "3.12"),
            (("runtime", "provider_sdk_version"), ">=0.83.0"),
            (("runtime", "operating_system"), "REPLACE_WITH_OS"),
            (("authority", "approval_reference"), "unknown"),
            (("timing", "clock_source"), "TBD"),
        ):
            with self.subTest(path=path):
                plan = _valid_plan()
                plan[path[0]][path[1]] = value
                with self.assertRaises(LivePopulationContractError):
                    validate_live_population_plan(plan)

    def test_lineage_is_explicit_and_hash_bound(self):
        first = _valid_plan()
        self.assertEqual(
            validate_live_population_plan(first)["lineage"]["status"],
            "first_population",
        )

        successor = _valid_plan()
        successor["population_id"] = "gex-live-002-es-p002"
        successor["lineage"] = {
            "status": "successor_population",
            "prior_population_id": first["population_id"],
            "prior_result_manifest_sha256": "a" * 64,
        }
        self.assertEqual(
            validate_live_population_plan(successor)["lineage"][
                "prior_result_manifest_sha256"
            ],
            "a" * 64,
        )

        for mutation in ("missing hash", "self reference", "first with prior"):
            with self.subTest(mutation=mutation):
                invalid = copy.deepcopy(successor if mutation != "first with prior" else first)
                if mutation == "missing hash":
                    invalid["lineage"]["prior_result_manifest_sha256"] = None
                elif mutation == "self reference":
                    invalid["lineage"]["prior_population_id"] = invalid[
                        "population_id"
                    ]
                else:
                    invalid["lineage"]["prior_population_id"] = "earlier-population"
                with self.assertRaises(LivePopulationContractError):
                    validate_live_population_plan(invalid)

    def test_packaged_template_is_complete_in_shape_but_deliberately_unfrozen(self):
        path = provider_fixture_path(
            "databento_es_live_population_plan_template.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(path.is_absolute())
        self.assertEqual(len(payload["planned_slots"]), 12)
        self.assertEqual(
            payload["certification_policy"],
            certification_policy_identity(ES_PRELIVE_V1),
        )
        with self.assertRaisesRegex(
            LivePopulationContractError, "placeholder"
        ):
            validate_live_population_plan(payload)
        serialized = json.dumps(payload).casefold()
        for sensitive_name in (
            "api_key",
            "account_id",
            "authorization",
            "credential",
            "secret",
            "subscription_id",
        ):
            self.assertNotIn(sensitive_name, serialized)

    def test_file_loader_rejects_duplicate_keys_without_echoing_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            path.write_text(
                '{"schema":"must-not-echo","schema":"also-private"}',
                encoding="utf-8",
            )
            with self.assertRaises(LivePopulationContractError) as context:
                load_live_population_plan(path)
        self.assertNotIn("must-not-echo", str(context.exception))
        self.assertNotIn("also-private", str(context.exception))


class LivePopulationResultTests(unittest.TestCase):
    def test_actual_times_preserve_seconds_and_fractional_precision(self):
        plan = _valid_plan()
        results = _valid_results(plan)
        results["observations"][0][
            "actual_start_utc"
        ] = "2026-10-05T00:59:59.125Z"
        results["observations"][0][
            "actual_stop_utc"
        ] = "2026-10-05T01:20:00.750001Z"

        normalized = validate_live_population_result_manifest(plan, results)
        first = normalized["observations"][0]
        self.assertEqual(first["actual_start_utc"], "2026-10-05T00:59:59.125000Z")
        self.assertEqual(first["actual_stop_utc"], "2026-10-05T01:20:00.750001Z")

        equivalent = copy.deepcopy(results)
        equivalent["observations"][0][
            "actual_start_utc"
        ] = "2026-10-05T00:59:59.125000Z"
        self.assertEqual(
            live_population_result_identity(plan, results),
            live_population_result_identity(plan, equivalent),
        )

    def test_complete_results_accept_failures_and_missed_runs_without_replacement(self):
        plan = _valid_plan()
        results = _valid_results(plan)
        failed = results["observations"][1]
        failed["outcome"] = "policy_failure"
        failed["redacted_notes"] = "Quantitative policy gate failed."
        missed = results["observations"][2]
        missed.update(
            {
                "outcome": "missed",
                "actual_start_utc": None,
                "actual_stop_utc": None,
                "runtime": None,
                "certification_policy_sha256": None,
                "report": {"status": "not_produced", "sha256": None},
                "redacted_notes": "Planned window was not attempted.",
            }
        )

        normalized = validate_live_population_result_manifest(plan, results)
        self.assertEqual(len(normalized["observations"]), 12)
        self.assertEqual(normalized["observations"][1]["outcome"], "policy_failure")
        self.assertEqual(normalized["observations"][2]["outcome"], "missed")
        first_hash = live_population_result_identity(plan, results)["sha256"]
        results["observations"][1]["redacted_notes"] += " Retained for review."
        self.assertNotEqual(
            first_hash,
            live_population_result_identity(plan, results)["sha256"],
        )

    def test_results_require_exact_plan_run_population(self):
        plan = _valid_plan()
        mutations = {}

        missing = _valid_results(plan)
        missing["observations"].pop()
        mutations["missing"] = missing

        extra = _valid_results(plan)
        extra["observations"].append(copy.deepcopy(extra["observations"][-1]))
        mutations["extra"] = extra

        replacement = _valid_results(plan)
        replacement["observations"][1]["run_id"] = "replacement-run"
        mutations["replacement"] = replacement

        reordered = _valid_results(plan)
        reordered["observations"][0], reordered["observations"][1] = (
            reordered["observations"][1],
            reordered["observations"][0],
        )
        mutations["reordered"] = reordered

        for label, results in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(LivePopulationContractError):
                    validate_live_population_result_manifest(plan, results)

    def test_results_fail_closed_on_identity_runtime_policy_and_time_drift(self):
        plan = _valid_plan()
        mutations = {}

        identity = _valid_results(plan)
        identity["plan_identity"]["sha256"] = "0" * 64
        mutations["plan identity"] = identity

        runtime = _valid_results(plan)
        runtime["observations"][0]["runtime"]["python_version"] = "3.12.12"
        mutations["runtime"] = runtime

        policy = _valid_results(plan)
        policy["observations"][0]["certification_policy_sha256"] = "0" * 64
        mutations["policy"] = policy

        short_pass = _valid_results(plan)
        short_pass["observations"][0][
            "actual_start_utc"
        ] = "2026-10-05T01:00:00.000001Z"
        mutations["short pass"] = short_pass

        missed_claim = _valid_results(plan)
        missed_claim["observations"][0]["outcome"] = "missed"
        missed_claim["observations"][0]["redacted_notes"] = "Not attempted."
        mutations["missed with runtime"] = missed_claim

        for label, results in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(LivePopulationContractError):
                    validate_live_population_result_manifest(plan, results)

    def test_failed_runs_require_notes_and_policy_failures_require_report(self):
        plan = _valid_plan()
        no_notes = _valid_results(plan)
        no_notes["observations"][0]["outcome"] = "entitlement_failure"
        with self.assertRaisesRegex(LivePopulationContractError, "notes"):
            validate_live_population_result_manifest(plan, no_notes)

        no_report = _valid_results(plan)
        no_report["observations"][0].update(
            {
                "outcome": "policy_failure",
                "report": {"status": "not_produced", "sha256": None},
                "redacted_notes": "Policy evaluation failed.",
            }
        )
        with self.assertRaisesRegex(LivePopulationContractError, "report"):
            validate_live_population_result_manifest(plan, no_report)

    def test_result_file_loader_cross_checks_frozen_plan(self):
        plan = _valid_plan()
        results = _valid_results(plan)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "plan.json"
            result_path = root / "results.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result_path.write_text(json.dumps(results), encoding="utf-8")

            loaded = load_live_population_result_manifest(plan_path, result_path)
        self.assertEqual(loaded["plan_identity"], live_population_plan_identity(plan))


class LivePopulationCliTests(unittest.TestCase):
    def test_validation_commands_are_local_read_only_and_print_identities(self):
        plan = _valid_plan()
        results = _valid_results(plan)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "plan.json"
            result_path = root / "results.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result_path.write_text(json.dumps(results), encoding="utf-8")
            before = (plan_path.read_bytes(), result_path.read_bytes())

            with (
                patch.object(
                    socket.socket,
                    "connect",
                    side_effect=AssertionError("network access is forbidden"),
                ),
                patch(
                    "gex_terminal.cli.build_market_data_adapter",
                    side_effect=AssertionError("provider setup is forbidden"),
                ),
            ):
                output = StringIO()
                with patch.object(
                    sys,
                    "argv",
                    ["gex-terminal", "live-population-plan-validate", str(plan_path)],
                ), redirect_stdout(output):
                    main_sync()
                self.assertIn("Live population plan valid", output.getvalue())
                self.assertIn("sha256=", output.getvalue())

                output = StringIO()
                with patch.object(
                    sys,
                    "argv",
                    [
                        "gex-terminal",
                        "live-population-results-validate",
                        str(plan_path),
                        str(result_path),
                    ],
                ), redirect_stdout(output):
                    main_sync()
                self.assertIn("Live population results valid", output.getvalue())
                self.assertIn("sha256=", output.getvalue())

            self.assertEqual(before, (plan_path.read_bytes(), result_path.read_bytes()))

    def test_subprocess_cli_succeeds_and_rejection_does_not_echo_document_value(self):
        plan = _valid_plan()
        results = _valid_results(plan)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "plan.json"
            result_path = root / "results.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            result_path.write_text(json.dumps(results), encoding="utf-8")

            plan_completed = _run_cli(
                "live-population-plan-validate", str(plan_path)
            )
            result_completed = _run_cli(
                "live-population-results-validate",
                str(plan_path),
                str(result_path),
            )

            private_value = "must-not-echo-private-value"
            plan["target"]["symbol"] = private_value
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            rejected = _run_cli("live-population-plan-validate", str(plan_path))

        self.assertEqual(plan_completed.returncode, 0, plan_completed.stderr)
        self.assertEqual(result_completed.returncode, 0, result_completed.stderr)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn(private_value, rejected.stderr)


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("GEX_LOG_LEVEL", None)
    return subprocess.run(
        [sys.executable, "-m", "gex_terminal.cli", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()

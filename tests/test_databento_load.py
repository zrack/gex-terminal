import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.verify_databento_load import FAMILY_ROOTS, build_load_report, main


class DatabentoProviderLoadTests(unittest.TestCase):
    def _report(self, **kwargs):
        return asyncio.run(build_load_report(
            contracts_per_family=4, rounds=1, snapshot_every=1,
            minimum_ingest_records_per_second=0.001,
            maximum_snapshot_milliseconds=100000,
            maximum_peak_megabytes=100000, **kwargs,
        ))

    def test_raw_provider_load_covers_all_families_and_reconciles_state(self):
        report = self._report()
        self.assertTrue(report["result"]["passed"], report["gates"])
        self.assertEqual(report["workload"]["total_families"], 52)
        self.assertEqual(report["workload"]["unique_option_contracts"], 208)
        self.assertEqual(report["workload"]["raw_records"], 1460)
        self.assertEqual(report["workload"]["record_types"], {
            "definition": 208, "mbp-1": 4, "trades": 104, "statistics": 1144,
        })
        for symbol, families in FAMILY_ROOTS.items():
            self.assertEqual(len(families), 26)
            result = report["reconciliation"][symbol]
            self.assertTrue(all(result["checks"].values()), result)
            self.assertEqual(result["observed_state_count"], 156)
            self.assertEqual(result["observed_selected_count"], 78)
            self.assertEqual(result["deleted_oi_contracts"], 52)
            self.assertEqual(result["valid_zero_oi_contracts"], 26)
            self.assertEqual(result["observed_selected_quantity"], result["expected_selected_quantity"])
            self.assertEqual(result["observed_revisions_rejected"], 312)
        self.assertEqual(report["observed"]["peak_position_states"], 312)
        self.assertFalse(report["environment"]["tracemalloc_during_timing"])
        self.assertFalse(report["environment"]["asyncio_debug_during_measurement"])
        self.assertFalse(report["result"]["live_capacity_certified"])
        self.assertTrue(report["environment"]["source_sha256"])

    def test_budget_failures_fail_closed_without_wall_time_assertions(self):
        with patch("scripts.verify_databento_load._peak_rss_megabytes", return_value=512):
            report = asyncio.run(build_load_report(
                contracts_per_family=4, rounds=1,
                minimum_ingest_records_per_second=1e30,
                maximum_snapshot_milliseconds=1e-30,
                maximum_peak_megabytes=256,
            ))
        self.assertTrue(report["gates"]["correctness"])
        self.assertFalse(report["gates"]["ingest_rate"])
        self.assertFalse(report["gates"]["snapshot_latency"])
        self.assertFalse(report["gates"]["peak_memory"])
        self.assertFalse(report["result"]["passed"])

    def test_invalid_counts_and_budgets_rejected_before_provider_work(self):
        for kwargs in ({"contracts_per_family": 3}, {"rounds": 0},
                       {"rounds": 1.5},
                       {"snapshot_every": 0}, {"minimum_ingest_records_per_second": float("nan")},
                       {"maximum_peak_megabytes": 0}):
            with self.subTest(kwargs=kwargs), patch("scripts.verify_databento_load._exercise") as exercise:
                with self.assertRaises(ValueError):
                    asyncio.run(build_load_report(**kwargs))
                exercise.assert_not_called()

    def test_cli_writes_failing_budget_receipt_and_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "load.json"
            exit_code = main([
                "--output", str(path), "--contracts-per-family", "4", "--rounds", "1",
                "--minimum-ingest-records-per-second", "1e30",
                "--maximum-snapshot-milliseconds", "100000",
                "--maximum-peak-megabytes", "100000",
            ])
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 2)
        self.assertFalse(report["result"]["passed"])
        self.assertFalse(report["gates"]["ingest_rate"])
        self.assertTrue(report["gates"]["correctness"])

    def test_cli_invalid_nonfinite_budget_keeps_valid_failure_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            exit_code = main(["--output", str(path), "--maximum-peak-megabytes", "nan"])
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["error"]["type"], "ValueError")
        self.assertEqual(report["requested"]["maximum_peak_megabytes"], "nan")


if __name__ == "__main__":
    unittest.main()

"""Sparse option sides remain unavailable through downstream research tools."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from gex_terminal.config import GexConfig
from gex_terminal.demo_lab import build_demo_lab
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.overlays import build_tradingview_overlay, tradingview_overlay_csv
from gex_terminal.provider_fixture_lab import (
    ProviderFixtureCase,
    analyze_provider_fixture_case,
    summarize_provider_fixture_snapshot,
)
from gex_terminal.regime import build_regime_map
from gex_terminal.replay_catalog import ReplaySession
from gex_terminal.replay_lab import analyze_replay_session
from gex_terminal.research_journal import (
    build_journal_entry,
    build_journal_report,
    journal_report_to_csv,
    journal_report_to_markdown,
)
from gex_terminal.sensitivity import build_sensitivity_report, sensitivity_to_csv
from gex_terminal.session_store import (
    build_session_store_report,
    load_session_records,
    save_session_snapshot,
    session_store_report_to_csv,
    session_store_report_to_markdown,
)


def _config():
    return GexConfig(
        symbol="NQ", symbols=("NQ", "ES", "SPX", "QQQ"),
        data_mode="replay", data_provider="replay", contract_multiplier=20,
        risk_free_rate=0.045, days_to_expiry=63.0,
        refresh_interval_seconds=1.0, stale_after_seconds=10.0,
        replay_path="unused.jsonl", replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


def _session(path="unused.jsonl"):
    return ReplaySession(
        name="single-call-contract", path=str(path), label="Single Call Contract",
        description="Synthetic sparse NQ sample for absent-side regressions.",
        symbol="NQ", contract_multiplier=20,
    )


def _messages(side="C"):
    return [
        {"type": "underlying_tick", "symbol": "NQ", "price": 31025.0,
         "timestamp": "2026-10-16T13:35:00Z"},
        {"type": "options_volume_tick", "strike": 31000.0, "option_type": side,
         "volume": 1, "iv": 0.2, "timestamp": "2026-10-16T13:35:01Z"},
        {"type": "options_volume_tick", "strike": 31000.0, "option_type": side,
         "volume": 1, "iv": 0.2, "timestamp": "2026-10-16T13:35:02Z"},
    ]


async def _replay(side="C"):
    return await analyze_replay_session(_session(), _config(), messages=_messages(side))


class SparseReportWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_only_replay_preserves_unavailable_put_wall_and_ratio(self):
        report = await _replay()
        self.assertEqual(report["summary"]["call_wall"], 31000.0)
        self.assertIsNone(report["summary"]["put_wall"])
        self.assertIsNone(report["summary"]["imbalance"])
        self.assertEqual(report["summary"]["side_coverage"], "calls_only")
        for point in report["timeline"]:
            self.assertIsNone(point["put_wall"])
            self.assertIsNone(point["imbalance"])
            self.assertEqual(point["side_coverage"], "calls_only")
        self.assertNotIn("imbalance_threshold", {alert["type"] for alert in report["alerts"]})
        self.assertIsNone(json.loads(json.dumps(report))["summary"]["put_wall"])

    async def test_puts_only_replay_has_zero_ratio_and_no_call_wall(self):
        report = await _replay("P")
        self.assertIsNone(report["summary"]["call_wall"])
        self.assertEqual(report["summary"]["put_wall"], 31000.0)
        self.assertEqual(report["summary"]["imbalance"], 0.0)
        self.assertEqual(report["summary"]["side_coverage"], "puts_only")

    async def test_missing_ratio_does_not_fabricate_a_threshold_crossing(self):
        messages = _messages()
        messages.append({
            "type": "options_volume_tick", "strike": 31000.0, "option_type": "P",
            "volume": 1, "iv": 0.2, "timestamp": "2026-10-16T13:35:03Z",
        })
        report = await analyze_replay_session(_session(), _config(), messages=messages)
        self.assertEqual(report["summary"]["imbalance"], 2.0)
        self.assertNotIn("imbalance_threshold", {alert["type"] for alert in report["alerts"]})

    async def test_chart_overlays_omit_unobserved_side_lines(self):
        snapshot = (await _replay())["snapshot"]
        levels = build_tradingview_overlay(snapshot)["levels"]
        self.assertIn("call_wall", {level["name"] for level in levels})
        self.assertNotIn("put_wall", {level["name"] for level in levels})
        csv_rows = list(csv.DictReader(io.StringIO(tradingview_overlay_csv(snapshot))))
        self.assertNotIn("put_wall", {row["name"] for row in csv_rows})

    async def test_nq_call_only_overlay_qualifies_nearest_strike_compatibility_marker(self):
        snapshot = (await _replay())["snapshot"]
        overlay = build_tradingview_overlay(snapshot)
        level = next(level for level in overlay["levels"] if level["name"] == "zero_gamma")
        self.assertIsNone(snapshot["metrics"]["strike_profile_flip"])
        self.assertEqual(level["price"], 31000.0)
        self.assertEqual(level["label"], "Compatibility Level (Nearest Neutral Strike)")
        self.assertIn("no strike-profile crossing observed", level["notes"])
        self.assertIn("volatility behavior are unmeasured", level["notes"])
        self.assertEqual(overlay["source"]["zero_gamma_method"], "nearest_strike_bucket_fallback")
        rows = list(csv.DictReader(io.StringIO(tradingview_overlay_csv(snapshot))))
        csv_level = next(row for row in rows if row["name"] == "zero_gamma")
        self.assertEqual(csv_level["label"], level["label"])

    async def test_overlay_distinguishes_an_observed_strike_profile_crossing(self):
        messages = [*_messages(), {
            "type": "options_volume_tick", "strike": 30950.0, "option_type": "P",
            "volume": 1, "iv": 0.2, "timestamp": "2026-10-16T13:35:03Z",
        }]
        snapshot = (await analyze_replay_session(_session(), _config(), messages=messages))["snapshot"]
        overlay = build_tradingview_overlay(snapshot)
        level = next(level for level in overlay["levels"] if level["name"] == "zero_gamma")
        self.assertGreater(snapshot["metrics"]["strike_profile_flip"], 30950.0)
        self.assertLess(snapshot["metrics"]["strike_profile_flip"], 31000.0)
        self.assertEqual(level["label"], "Strike Profile Crossing")
        self.assertEqual(level["price"], snapshot["metrics"]["strike_profile_flip"])
        self.assertIn("adjacent strike-bucket net GEX changes sign", level["notes"])
        self.assertIn("portfolio gamma root and volatility behavior are unmeasured", level["notes"])
        self.assertEqual(overlay["source"]["zero_gamma_method"], "strike_profile_linear_interpolation")

    async def test_session_store_round_trip_and_comparison_keep_missing_values(self):
        snapshot = (await _replay())["snapshot"]
        with tempfile.TemporaryDirectory() as tmp:
            save_session_snapshot(snapshot, tmp, generated_at="2026-10-16T13:35:02")
            save_session_snapshot(snapshot, tmp, generated_at="2026-10-16T13:35:03")
            records = load_session_records(tmp)
            report = build_session_store_report(records)
        self.assertIsNone(records[0]["summary"]["put_wall"])
        self.assertIsNone(records[0]["summary"]["imbalance"])
        self.assertIsNone(report["latest_comparison"]["deltas"]["put_wall"])
        self.assertIsNone(report["latest_comparison"]["deltas"]["imbalance"])
        self.assertIn("Imbalance delta: `unavailable`", session_store_report_to_markdown(report))
        rows = list(csv.DictReader(io.StringIO(session_store_report_to_csv(report))))
        self.assertTrue(all(row["put_wall"] == "" for row in rows))
        self.assertTrue(all(row["imbalance"] == "" for row in rows))

    async def test_journal_comparison_keeps_newly_available_walls_unquantified(self):
        before = await _replay()
        messages = [*_messages(), {
            "type": "options_volume_tick", "strike": 30950.0, "option_type": "P",
            "volume": 1, "iv": 0.2, "timestamp": "2026-10-16T13:35:03Z",
        }]
        after = await analyze_replay_session(_session(), _config(), messages=messages)
        entries = [
            build_journal_entry(before, config=_config(), generated_at="2026-10-16T13:35:02"),
            build_journal_entry(after, config=_config(), generated_at="2026-10-16T13:35:03"),
        ]
        report = build_journal_report(entries)
        self.assertIsNone(report["latest_comparison"]["deltas"]["put_wall"])
        self.assertIsNone(report["latest_comparison"]["deltas"]["imbalance"])
        self.assertIn("Historical Research Journal", journal_report_to_markdown(report))
        rows = list(csv.DictReader(io.StringIO(journal_report_to_csv(report))))
        self.assertEqual(rows[0]["put_wall"], "")
        self.assertEqual(rows[-1]["put_wall"], "")

    async def test_provider_fixture_summary_preserves_absent_side_and_failed_cases(self):
        snapshot = (await _replay())["snapshot"]
        case = ProviderFixtureCase(
            name="calls-only", label="Calls Only", provider="databento", symbol="NQ",
            fixture_path=Path("does-not-exist.json"), description="Sparse fixture",
        )
        summary = summarize_provider_fixture_snapshot(case, snapshot)
        self.assertEqual(summary["call_wall"], 31000.0)
        self.assertIsNone(summary["put_wall"])
        failed = await analyze_provider_fixture_case(case, _config())
        self.assertFalse(failed["summary"]["ok"])
        self.assertIsNone(failed["summary"]["call_wall"])
        self.assertIsNone(failed["summary"]["put_wall"])

    async def test_calls_only_demo_pack_exports_and_receipt_handle_missing_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.jsonl"
            source.write_text("".join(json.dumps(row) + "\n" for row in _messages()))
            output = Path(tmp) / "demo"
            with patch("gex_terminal.demo_lab.replay_session_for_name", return_value=_session(source)):
                manifest = await build_demo_lab(
                    _config(), output, replay_session_name="single-call-contract",
                    screenshot_width=140, screenshot_height=42,
                )
            self.assertIsNone(manifest["summary"]["put_wall"])
            self.assertIsNone(manifest["summary"]["imbalance"])
            self.assertIn("Imbalance: unavailable", (output / "gex-terminal-color.svg").read_text())
            self.assertIsNone(json.loads((output / "snapshot.json").read_text())["metrics"]["put_wall"])
            self.assertTrue((output / "review-receipt.json").exists())


class SparseSensitivityTests(unittest.TestCase):
    def test_absent_sides_stay_null_through_scenarios_and_parity_checks(self):
        for side in ("C", "P"):
            with self.subTest(side=side):
                calls = np.array([2.0 if side == "C" else 0.0])
                puts = np.array([2.0 if side == "P" else 0.0])
                matrix = IntradayGexEngine(multiplier=20).compute_intraday_gex_matrix(
                    spot_price=31025.0, strikes=np.array([31000.0]),
                    days_to_expiry=63.0, risk_free_rate=0.045,
                    implied_vols=np.array([0.2]), accumulated_call_vol=calls,
                    accumulated_put_vol=puts,
                )
                inputs = dict(
                    spot=31025.0, chain_state={31000.0: {"C": calls[0], "P": puts[0], "iv": 0.2}},
                    days_to_expiry=63.0, risk_free_rate=0.045, contract_multiplier=20,
                )
                report = build_sensitivity_report(**inputs, base_matrix=matrix)
                absent = "put_wall" if side == "C" else "call_wall"
                self.assertTrue(all(row[absent] is None for row in report["scenarios"]))
                csv_rows = list(csv.DictReader(io.StringIO(sensitivity_to_csv(report))))
                self.assertTrue(all(row[absent] == "" for row in csv_rows))
                phantom = dict(matrix, **{f"{absent}_strike": 31000.0})
                with self.assertRaisesRegex(ValueError, f"{absent}_strike"):
                    build_sensitivity_report(**inputs, base_matrix=phantom)

    def test_regime_map_keeps_absent_walls_out_of_nearest_trigger(self):
        regime = build_regime_map({
            "total_net_gex": 100.0, "zero_gamma_strike": 30800.0,
            "gamma_wall_strike": 31000.0, "call_wall_strike": 31000.0,
            "put_wall_strike": None, "strikes": [31000.0],
        }, spot=31025.0)
        self.assertIsNone(regime["put_wall"])
        self.assertNotEqual(regime["next_trigger"]["name"], "put_wall")

    def test_regime_map_does_not_invent_missing_side_walls_from_net_wall(self):
        regime = build_regime_map({
            "total_net_gex": 100.0, "zero_gamma_strike": 30800.0,
            "gamma_wall_strike": 31000.0, "strikes": [31000.0],
        }, spot=31025.0)
        self.assertIsNone(regime["call_wall"])
        self.assertIsNone(regime["put_wall"])


if __name__ == "__main__":
    unittest.main()

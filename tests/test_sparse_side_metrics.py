"""Sparse observed sides must not manufacture walls or invert dominance."""

import csv
import io
import json
import unittest
from dataclasses import replace

import numpy as np
from rich.text import Text
from textual.widgets import Static

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine, side_exposure_balance
from gex_terminal.pricing_assumptions import build_pricing_assumptions
from gex_terminal.snapshot import build_snapshot
from gex_terminal.snapshot_formats import snapshot_to_csv, snapshot_to_markdown
from gex_terminal.tui import GexTerminalApp
from tests.test_databento_regressions import definition, quote, trade
from tests.test_tui_first_run import _config


def matrix(calls, puts):
    return IntradayGexEngine(20).compute_intraday_gex_matrix(
        spot_price=31000, strikes=np.array([30900, 31000, 31100]),
        days_to_expiry=63, risk_free_rate=.045,
        implied_vols=np.array([.2, .2, .2]),
        accumulated_call_vol=np.array(calls), accumulated_put_vol=np.array(puts),
        pricing_model="black_76",
    )


def snapshot(data):
    return build_snapshot(
        symbol="NQ", spot=31000, session_open=31000, days_to_expiry=63,
        contract_multiplier=20, risk_free_rate=.045, data=data, chain_state={},
    )


class SparseSideMetricsTests(unittest.TestCase):
    def test_absent_side_has_no_wall_in_matrix_or_json_snapshot(self):
        for calls, puts, expected_call, expected_put, status in (
            ([0, 2, 0], [0, 0, 0], 31000, None, "calls_only"),
            ([0, 0, 0], [0, 2, 0], None, 31000, "puts_only"),
            ([0, 0, 0], [0, 0, 0], None, None, "no_selected_quantities"),
            ([0, 2, 0], [0, 0, 1], 31000, 31100, "both_sides"),
        ):
            with self.subTest(status=status):
                data = matrix(calls, puts)
                self.assertEqual(data["call_wall_strike"], expected_call)
                self.assertEqual(data["put_wall_strike"], expected_put)
                metrics = json.loads(json.dumps(snapshot(data), allow_nan=False))["metrics"]
                self.assertEqual(metrics["call_wall"], expected_call)
                self.assertEqual(metrics["put_wall"], expected_put)
                self.assertEqual(metrics["side_coverage"], status)
                if status in {"calls_only", "no_selected_quantities"}:
                    self.assertIsNone(metrics["imbalance"])
                elif status == "puts_only":
                    self.assertEqual(metrics["imbalance"], 0)
                else:
                    self.assertAlmostEqual(
                        metrics["imbalance"], sum(data["call_gex"]) / abs(sum(data["put_gex"]))
                    )

    def test_export_preserves_unavailable_metrics_and_explains_side_coverage(self):
        for calls, puts, label, absent_wall in (
            ([0, 2, 0], [0, 0, 0], "Calls only", "put_wall"),
            ([0, 0, 0], [0, 2, 0], "Puts only", "call_wall"),
            ([0, 0, 0], [0, 0, 0], "No selected quantities", "put_wall"),
        ):
            with self.subTest(label=label):
                data = snapshot(matrix(calls, puts))
                markdown = snapshot_to_markdown(data)
                self.assertIn(f"Call/put balance: `{label}`", markdown)
                self.assertIn(f"{absent_wall.replace('_', ' ').capitalize()}: `unavailable`", markdown)
                rows = {row["name"]: row for row in csv.DictReader(io.StringIO(snapshot_to_csv(data)))
                        if row["record_type"] == "metric"}
                self.assertEqual(rows[absent_wall]["value"], "")
                self.assertEqual(rows["side_coverage"]["value"], data["metrics"]["side_coverage"])

    def test_missing_wall_fields_do_not_fall_back_to_unrelated_gamma_wall(self):
        data = matrix([0, 2, 0], [0, 0, 0])
        data.pop("put_wall_strike")
        self.assertIsNone(snapshot(data)["metrics"]["put_wall"])

    def test_exports_keep_exercise_qualification_and_configured_rate_visible(self):
        data = matrix([0, 2, 0], [0, 0, 0])
        # Legacy captures have no exercise evidence; a model name is not proof.
        self.assertEqual(snapshot(data)["model"]["pricing_assumptions"]["status"], "exercise_style_unknown")
        assumptions = build_pricing_assumptions(
            [{"pricing_model": "black_76", "exercise_style": "american"}], .045,
        )
        data["pricing_assumptions"] = assumptions
        exported = snapshot(data)
        self.assertEqual(exported["model"]["pricing_assumptions"], assumptions)
        markdown = snapshot_to_markdown(exported)
        for text in ("Black-76", "approximation error unmeasured", "early exercise is not modeled",
                     "configured, not observed market data", "ACT/365"):
            self.assertIn(text, markdown)
        rows = list(csv.DictReader(io.StringIO(snapshot_to_csv(exported))))
        model_row = next(row for row in rows if row["record_type"] == "model" and row["name"] == "pricing_assumptions")
        self.assertEqual(json.loads(model_row["value"]), assumptions)

    def test_zero_computed_exposure_has_no_wall_even_with_positive_input_quantity(self):
        data = IntradayGexEngine(20).compute_intraday_gex_matrix(
            spot_price=100, strikes=np.array([1e12]), days_to_expiry=.001,
            risk_free_rate=.045, implied_vols=np.array([.01]),
            accumulated_call_vol=np.array([2]), accumulated_put_vol=np.array([0]),
        )
        self.assertEqual(data["call_gex"], [0])
        self.assertIsNone(data["call_wall_strike"])
        self.assertIsNone(data["put_wall_strike"])

    def test_ratio_distinguishes_absent_denominator_from_valid_zero(self):
        self.assertEqual(side_exposure_balance(2, 0), (None, "calls_only"))
        self.assertEqual(side_exposure_balance(0, 2), (0, "puts_only"))
        self.assertEqual(side_exposure_balance(0, 0), (None, "no_selected_quantities"))
        self.assertEqual(side_exposure_balance(3, 2), (1.5, "both_sides"))


class SparseSideTerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_call_only_then_both_sides_and_put_only_render_honestly(self):
        for initial_side, initial_label, absent_side in (("C", "Calls only", "put"), ("P", "Puts only", "call")):
            with self.subTest(side=initial_side):
                config = replace(_config("replay"), symbol="NQ", contract_multiplier=20,
                                 days_to_expiry=63, refresh_interval_seconds=3600)
                consumer = StatefulGexConsumer(IntradayGexEngine(20), target_underlying="NQ", data_mode="replay")
                adapter = DatabentoAdapter(consumer, target_underlying="NQ")
                await adapter._handle_live_record(definition("NQ", instrument_class=initial_side,
                    raw_symbol=f"NQZ6 {initial_side}31000", strike_price=31000,
                    expiration="2026-12-18T14:30:00Z", cfi="OCAFPS" if initial_side == "C" else "OPAFPS"))
                await adapter._handle_live_record(quote(bid_px_00=30999.75, ask_px_00=31000.25,
                    ts_event="2026-10-16T13:35:00Z"))
                await adapter._handle_live_record(trade(size=2, ts_event="2026-10-16T13:35:00Z"))
                app = GexTerminalApp(consumer, config)

                def visible(selector):
                    content = app.query_one(selector, Static).content
                    return content.plain if isinstance(content, Text) else Text.from_markup(str(content)).plain

                async with app.run_test(size=(140, 42)) as pilot:
                    await pilot.pause()
                    self.assertEqual(visible("#stat-imbalance"), initial_label)
                    self.assertIn(initial_label, visible("#balance-pressure"))
                    self.assertNotIn("dominant", visible("#stat-imbalance-foot"))
                    self.assertIn(f"{absent_side} wall --", visible("#dealer-regime"))
                    self.assertNotIn("0.00x", visible("#balance-pressure"))
                    # Repeated unavailable ratios must neither crash nor create ratio alerts.
                    for _ in range(2):
                        await app.refresh_terminal_data()
                    self.assertFalse(any("imbalance threshold crossed" in event for event in app._events))
                    self.assertIn("American futures CRR", visible("#pricing-assumptions"))
                    self.assertIn("early exercise is modeled", visible("#pricing-assumptions"))
                    await pilot.press("v")
                    details = app.screen.query_one("#info-content", Static).content.plain
                    self.assertIn("numerical discretization remains", details)
                    self.assertIn("empirical pricing accuracy is unmeasured", details)
                    self.assertIn("configured, not observed market data", details)
                    await pilot.press("escape")

                    other_side = "P" if initial_side == "C" else "C"
                    await adapter._handle_live_record(definition("NQ", instrument_id=102,
                        instrument_class=other_side, raw_symbol=f"NQZ6 {other_side}31000", strike_price=31000,
                        expiration="2026-12-18T14:30:00Z", cfi="OPAFPS" if other_side == "P" else "OCAFPS"))
                    await adapter._handle_live_record(trade(instrument_id=102, size=1, ts_event="2026-10-16T13:35:01Z"))
                    await app.refresh_terminal_data()
                    self.assertIn("x", visible("#stat-imbalance"))
                    self.assertIn("dominant", visible("#stat-imbalance-foot"))
                    self.assertNotIn("wall --", visible("#dealer-regime"))


if __name__ == "__main__":
    unittest.main()

"""Exercise visible Terminal coverage and captured-observation details offline."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import unittest

from rich.text import Text
from textual.screen import Screen
from textual.widgets import DataTable, Static

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.replay_catalog import replay_session_for_name
from gex_terminal.tui import GexTerminalApp
from tests.test_tui_first_run import _config
from tests.test_wind_tunnel_checkpoint import AS_OF, emit, option
from tests.test_pricing_coverage import unavailable


def visible(root, selector):
    content = root.query_one(selector, Static).content
    return content.plain if isinstance(content, Text) else Text.from_markup(str(content)).plain


def unpriced(*, volume=1):
    return unavailable(
        "captured-put", volume=volume, strike=30430,
        iv_provenance={"method": "black_76_bisection", "status": "outside_no_arbitrage_bounds",
                       "option_price": 508, "lower_bound": 529.6077, "upper_bound": 30429,
                       "underlying_price": 29900.375, "underlying_price_age_ms": 493.863,
                       "underlying_event_time": AS_OF},
    )


class DelayedRowsConsumer(StatefulGexConsumer):
    def __init__(self):
        super().__init__(IntradayGexEngine(50), data_mode="replay")
        self.delay_rows = False
        self.rows_started = asyncio.Event()
        self.release_rows = asyncio.Event()

    async def selected_contract_rows(self, **kwargs):
        if self.delay_rows:
            self.delay_rows = False
            self.rows_started.set()
            await self.release_rows.wait()
        return await super().selected_contract_rows(**kwargs)


async def ready(*events, consumer=None):
    consumer = consumer or StatefulGexConsumer(IntradayGexEngine(50), data_mode="replay")
    await emit(consumer, {"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                          "symbol": "ES", "price": 6000, "event_time": AS_OF})
    for event in events:
        await emit(consumer, event)
    return GexTerminalApp(consumer, replace(_config("replay"), refresh_interval_seconds=3600,
                                           replay_path="local-test-capture.jsonl"))


class TerminalPricingCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_coverage_is_prominent_and_details_use_captured_inputs(self):
        app = await ready(option("priced", volume=1691), unpriced())
        before = deepcopy(await app.consumer.process_latest_snapshot(.01))
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            widget = app.query_one("#pricing-coverage", Static)
            self.assertTrue(widget.display)
            self.assertGreater(widget.region.height, 0)
            summary = visible(app, "#pricing-coverage")
            for phrase in ("Partial", "contracts 1/2 (50.00%)", "1,691/1,692 (99.94%)",
                           "captured premium", "Raw quantities are retained", "excluded from modeled GEX"):
                self.assertIn(phrase, summary)
            self.assertNotIn("100.00%", summary)
            await pilot.press("v")
            details = visible(app.screen, "#info-content")
            for phrase in ("captured-put", "put 30,430", "quantity 1", "508 points", "529.6077 points",
                           "21.6077 points", "underlying 29,900.375", "quote age 0.494 seconds"):
                self.assertIn(phrase, details)
            self.assertNotIn("bad provider", details.lower())
            self.assertNotIn("15%", details)
        # Presentation never attaches fallback coverage or changes math output.
        self.assertEqual(await app.consumer.process_latest_snapshot(.01), before)

    async def test_all_priced_v2_rows_show_complete_without_mutating_matrix_shape(self):
        app = await ready(option("priced", volume=10))
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            summary = visible(app, "#pricing-coverage")
            self.assertIn("Complete", summary)
            self.assertIn("contracts 1/1 (100.00%)", summary)
            self.assertIn("10/10 (100.00%)", summary)
            self.assertNotIn("pricing_coverage", app._last_data)
            await pilot.press("v")
            self.assertNotIn("Unpriced contracts · captured observations", visible(app.screen, "#info-content"))

    async def test_all_unpriced_error_keeps_coverage_and_diagnostics_without_zero_gex(self):
        app = await ready(unpriced(volume=7))
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            self.assertIsNone(app._last_data)
            self.assertEqual(visible(app, "#stat-netgex"), "--")
            self.assertEqual(app.query_one("#gex-table", DataTable).row_count, 0)
            summary = visible(app, "#pricing-coverage")
            self.assertIn("All unpriced", summary)
            self.assertIn("contracts 0/1 (0.00%)", summary)
            self.assertIn("0/7 (0.00%)", summary)
            self.assertIn("GEX UNAVAILABLE", visible(app, "#matrix-state"))
            self.assertIn("IV unavailable", visible(app, "#stat-netgex-foot"))
            self.assertIn("Raw quantity retained", visible(app, "#stat-imbalance-foot"))
            self.assertIn("retained · GEX unavailable", visible(app, "#feed-proxy"))
            self.assertIn("Raw quantities retained", visible(app, "#flow-message"))
            self.assertNotIn("Waiting for active contracts", visible(app, "#flow-message"))
            await pilot.press("v")
            details = visible(app.screen, "#info-content")
            self.assertIn("captured-put", details)
            self.assertIn("No valid IV fits those captured inputs", details)
            self.assertIn("Black-76", details)
            self.assertIn("508 points", details)

    async def test_new_expiry_selection_and_new_source_remove_old_unpriced_details(self):
        future = option("later-priced", volume=10, expiry="2026-09-05",
                        expiry_timestamp="2026-09-05T20:00:00Z")
        app = await ready(future, unpriced())
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            self.assertIn("Partial", visible(app, "#pricing-coverage"))
            for _ in range(len(app._expiry_filter_choices())):
                await app.action_cycle_expiry_filter()
                if app.config.expiry_filter == "2026-09-05":
                    break
            self.assertEqual(app.config.expiry_filter, "2026-09-05")
            self.assertIn("Complete", visible(app, "#pricing-coverage"))
            await pilot.press("v")
            self.assertNotIn("captured-put", visible(app.screen, "#info-content"))
            await pilot.press("escape")
            app.config = replace(app.config, expiry_filter="all")
            app.consumer.set_expiry_filter("all")
            await app.refresh_terminal_data()
            self.assertIn("Partial", visible(app, "#pricing-coverage"))
            await app._load_replay_session(replay_session_for_name("zero-gamma-flip"))
            self.assertNotIn("outside the model's valid pricing bounds", visible(app, "#pricing-coverage"))
            await pilot.press("v")
            self.assertNotIn("captured-put", visible(app.screen, "#info-content"))

    async def test_empty_reset_clears_stale_pricing_detail(self):
        app = await ready(option("priced"), unpriced())
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            await app.consumer.reset_state(data_mode="replay")
            await app.refresh_terminal_data()
            self.assertIn("Not reported", visible(app, "#pricing-coverage"))
            self.assertEqual(app._last_selected_contract_rows, [])
            await pilot.press("v")
            self.assertNotIn("captured-put", visible(app.screen, "#info-content"))
            self.assertNotIn("508 points", visible(app.screen, "#info-content"))

    async def test_empty_expiry_selection_reports_zero_denominators_for_v2_source(self):
        future = option("later-priced", volume=10, expiry="2026-09-05",
                        expiry_timestamp="2026-09-05T20:00:00Z")
        app = await ready(future)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            self.assertIn("Complete", visible(app, "#pricing-coverage"))
            await app.action_cycle_expiry_filter()
            self.assertEqual(app.config.expiry_filter, "0dte")
            coverage = visible(app, "#pricing-coverage")
            self.assertIn("No selected contracts", coverage)
            self.assertIn("contracts 0/0 (n/a)", coverage)
            self.assertIn("quantity 0/0 (n/a)", coverage)
            self.assertNotIn("Not reported", coverage)
            self.assertNotIn("100", coverage)
            self.assertIsNone(app._last_data)
            self.assertEqual(len(app.consumer.contract_state), 1)

    async def test_delayed_row_refresh_cannot_publish_after_source_reset(self):
        consumer = DelayedRowsConsumer()
        app = await ready(option("priced"), unpriced(), consumer=consumer)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            consumer.delay_rows = True
            refresh = asyncio.create_task(app.refresh_terminal_data())
            try:
                await asyncio.wait_for(consumer.rows_started.wait(), 2)
                app._reset_terminal_session_state()
                cleared = visible(app, "#pricing-coverage")
                consumer.release_rows.set()
                await asyncio.wait_for(refresh, 2)
                self.assertEqual(visible(app, "#pricing-coverage"), cleared)
                self.assertEqual(app._last_selected_contract_rows, [])
                self.assertIsNone(app._last_data)
                await pilot.press("v")
                self.assertNotIn("captured-put", visible(app.screen, "#info-content"))
            finally:
                consumer.release_rows.set()
                await refresh

    async def test_delayed_row_refresh_respects_dashboard_screen_ownership(self):
        consumer = DelayedRowsConsumer()
        app = await ready(option("priced"), unpriced(), consumer=consumer)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            baseline = deepcopy(app._last_pricing_display)
            consumer.delay_rows = True
            refresh = asyncio.create_task(app.refresh_terminal_data())
            try:
                await asyncio.wait_for(consumer.rows_started.wait(), 2)
                await app.push_screen(Screen())
                consumer.release_rows.set()
                await asyncio.wait_for(refresh, 2)
                self.assertEqual(app._last_pricing_display, baseline)
                self.assertIsNone(app._exception)
            finally:
                consumer.release_rows.set()
                await refresh


if __name__ == "__main__":
    unittest.main()

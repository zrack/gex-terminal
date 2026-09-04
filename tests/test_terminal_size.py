import unittest

from textual.widgets import DataTable, Static

from gex_terminal.cli import seed_demo_session
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.tui import GexTerminalApp
from tests.test_tui_first_run import _config


class TerminalSizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_supported_sizes_expose_table_quality_and_replay_controls(self):
        for size in ((140, 42), (160, 48), (180, 54)):
            with self.subTest(size=size):
                consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="demo")
                await seed_demo_session(consumer)
                app = GexTerminalApp(consumer, _config())
                async with app.run_test(size=size) as pilot:
                    await pilot.pause()
                    table = app.query_one("#gex-table", DataTable)
                    self.assertGreater(table.row_count, 0)
                    self.assertGreaterEqual(table.content_size.height, 3)
                    for selector in ("#gex-table", "#matrix-controls", "#quality-summary"):
                        widget = app.query_one(selector)
                        self.assertTrue(widget.visible)
                        self.assertGreater(widget.region.width, 0)
                        self.assertGreater(widget.region.height, 0)
                        self.assertGreaterEqual(widget.region.y, 0)
                        self.assertLessEqual(widget.region.bottom, size[1])
                    self.assertFalse(app.query_one("#minimum-size-message").display)
                    for selector in ("#stat-spot", "#stat-netgex", "#quality-summary"):
                        widget = app.query_one(selector)
                        self.assertLessEqual(widget.region.bottom, widget.parent.content_region.bottom)
                        self.assertGreaterEqual(widget.region.y, widget.parent.content_region.y)
                    await app.action_cycle_replay_session()
                    self.assertTrue(app._replay_browser_open)

    async def test_small_size_warns_and_recovers_on_resize_without_losing_state(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="demo")
        await seed_demo_session(consumer)
        app = GexTerminalApp(consumer, _config())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for width, height in ((80, 24), (120, 40)):
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                warning = app.query_one("#minimum-size-message", Static)
                self.assertTrue(warning.display)
                self.assertIn("140 × 42", str(warning.content))
                self.assertFalse(app.query_one("#dashboard").display)
            count = consumer.message_count
            await pilot.resize_terminal(140, 42)
            await pilot.pause()
            self.assertFalse(app.query_one("#minimum-size-message").display)
            self.assertTrue(app.query_one("#dashboard").display)
            self.assertEqual(consumer.message_count, count)
            self.assertGreater(app.query_one("#gex-table", DataTable).row_count, 0)

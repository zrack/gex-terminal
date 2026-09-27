import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from textual.widgets import DataTable, OptionList, Static

from gex_terminal.cli import seed_demo_session
from gex_terminal.tui_views import ReplayPicker, ResearchInfo
from gex_terminal.tui import GexTerminalApp
from gex_terminal.replay_catalog import replay_session_for_name
from tests.test_replay_keyboard import _app


class ResearchFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_health_summary_keeps_raw_connection_state_in_details(self):
        app = _app()
        await seed_demo_session(app.consumer)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            summary = app.query_one("#quality-summary", Static).content.plain
            self.assertTrue(summary.startswith("Offline · no network needed\n"))
            self.assertIn("Connection", summary)
            await pilot.press("v")
            details = app.screen.query_one("#info-content", Static).content.plain
            self.assertIn("Connection", details)
            self.assertIn(app.consumer.feed_quality_snapshot()["connection_state"], details)

    async def test_details_identify_provider_and_custom_replay_without_connecting(self):
        for mode, path, expected in (
            ("live", replay_session_for_name("demo").path, "Source      tradovate"),
            ("replay", "user-selected-replay.jsonl", "Source      Local replay"),
        ):
            with self.subTest(mode=mode):
                base = _app(data_mode=mode)
                app = GexTerminalApp(base.consumer, replace(base.config, replay_path=path))
                async with app.run_test(size=(100, 32)) as pilot:
                    await pilot.press("v")
                    content = str(app.screen.query_one("#info-content", Static).content)
                    self.assertIn(expected, content)
                    self.assertEqual(app.consumer.message_count, 0)

    async def test_selected_strike_survives_refresh_sort_and_responsive_columns(self):
        app = _app()
        await seed_demo_session(app.consumer)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            table = app.query_one("#gex-table", DataTable)
            await pilot.press("down", "down", "down")
            selected = app._selected_strike_key(table)
            self.assertNotEqual(table.cursor_row, 0)
            await app.refresh_terminal_data()
            self.assertEqual(app._selected_strike_key(table), selected)
            await pilot.press("s")
            self.assertEqual(app._selected_strike_key(table), selected)
            await pilot.resize_terminal(100, 32)
            await pilot.pause()
            self.assertEqual(app._selected_strike_key(table), selected)
            self.assertEqual(len(table.columns), 4)
            await pilot.press("c")
            self.assertEqual(len(table.columns), 7)
            self.assertEqual(app._selected_strike_key(table), selected)

    async def test_picker_tracks_visible_selection_and_restores_focus(self):
        app = _app()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("p")
            picker = app.screen
            self.assertIsInstance(picker, ReplayPicker)
            options = picker.query_one(OptionList)
            self.assertIs(app.focused, options)
            await pilot.press("down", "down", "down")
            await pilot.pause()
            self.assertEqual(options.highlighted, 10)
            rendered = "\n".join(options.render_line(row).text for row in range(options.size.height))
            self.assertIn("NQ Portable", rendered)
            self.assertIn("NQ", str(picker.query_one("#replay-description", Static).content))
            await pilot.press("escape")
            self.assertFalse(app._replay_browser_open)
            self.assertIs(app.focused, app.query_one("#gex-table", DataTable))

    async def test_help_and_details_are_reachable_without_mutating_research(self):
        app = _app()
        await seed_demo_session(app.consumer)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            config = app.config
            count = app.consumer.message_count
            for key, expected in (("question_mark", "Model assumptions"), ("v", "Feed diagnostics")):
                await pilot.press(key)
                self.assertIsInstance(app.screen, ResearchInfo)
                self.assertIn(expected, str(app.screen.query_one("#info-content", Static).content))
                await pilot.press("d", "m", "p")
                self.assertIs(app.config, config)
                self.assertEqual(app.consumer.message_count, count)
                await pilot.press("escape")
                self.assertIs(app.screen, app._refresh_screen_owner)

    async def test_unchanged_snapshots_show_message_instead_of_a_full_sparkline(self):
        app = _app()
        await seed_demo_session(app.consumer)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await app.refresh_terminal_data()
            self.assertFalse(app.query_one("#gex-flow").display)
            self.assertIn("No change", str(app.query_one("#flow-message", Static).content))
            await app.action_cycle_multiplier_assumption()
            self.assertTrue(app.query_one("#gex-flow").display)
            self.assertFalse(app.query_one("#flow-message").display)

    async def test_two_exports_are_distinct_and_details_retain_destination(self):
        app = _app()
        await seed_demo_session(app.consumer)
        with tempfile.TemporaryDirectory() as directory:
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.pause()
                from gex_terminal.snapshot import write_snapshot
                paths = []

                def save(snapshot, filename):
                    path = write_snapshot(snapshot, Path(directory) / filename)
                    paths.append(path)
                    return path

                with patch("gex_terminal.tui.write_snapshot", side_effect=save):
                    await pilot.press("e", "e")
                self.assertEqual(len(set(paths)), 2)
                self.assertTrue(all(path.is_file() for path in paths))
                self.assertEqual(app._last_export, paths[-1].resolve())
                await pilot.press("v")
                self.assertIn(str(paths[-1]), str(app.screen.query_one("#info-content", Static).content))


if __name__ == "__main__":
    unittest.main()

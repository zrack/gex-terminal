"""Exercise Textual key routing, not direct replay action calls."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from textual.screen import Screen
from textual.widgets import DataTable, Footer

from gex_terminal.cli import seed_demo_session
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.replay_catalog import replay_session_for_name
from gex_terminal.tui import GexTerminalApp
from tests.test_tui_first_run import _config


def _app(*, data_mode="demo", allow_replay_switching=True):
    config = replace(_config(data_mode), refresh_interval_seconds=3600)
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=config.contract_multiplier),
        target_underlying=config.symbol,
        risk_free_rate=config.risk_free_rate,
        data_mode=config.data_mode,
        stale_after_seconds=config.stale_after_seconds,
    )
    return GexTerminalApp(
        consumer, config, allow_replay_switching=allow_replay_switching,
    )


class KeyboardOverlay(Screen):
    BINDINGS = [("escape", "dismiss_overlay", "Close")]

    def __init__(self):
        super().__init__()
        self.selected_row = None

    def compose(self):
        yield DataTable(id="overlay-table")

    def on_mount(self):
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("Choice")
        table.add_rows([("First",), ("Second",), ("Third",)])
        table.focus()

    def on_data_table_row_selected(self, event):
        self.selected_row = event.cursor_row

    def action_dismiss_overlay(self):
        self.app.pop_screen()


class ReplayKeyboardTests(unittest.IsolatedAsyncioTestCase):
    def _footer_actions(self, app):
        return {key.action for key in app.query_one(Footer).query("FooterKey")}

    async def test_keyboard_browses_and_loads_es_then_nq_at_supported_sizes(self):
        for size in ((140, 42), (180, 54)):
            with self.subTest(size=size):
                app = _app()
                async with app.run_test(size=size) as pilot:
                    await pilot.pause()
                    table = app.query_one("#gex-table", DataTable)
                    self.assertIs(app.focused, table)
                    await pilot.press("p", "down")
                    self.assertTrue(app._replay_browser_open)
                    self.assertEqual(app._selected_replay_session().name, "expiration-compression")
                    await pilot.press("up", "enter")
                    self.assertFalse(app._replay_browser_open)
                    self.assertEqual(app._active_replay_session.name, "zero-gamma-flip")
                    self.assertEqual(app.config.data_mode, "replay")
                    self.assertEqual(app.consumer.target_underlying, "ES")
                    self.assertEqual(app.consumer.engine.multiplier, 50)
                    self.assertGreater(app.consumer.message_count, 0)
                    self.assertGreater(table.row_count, 0)

                    # Replace an already loaded replay through the same real keys.
                    await pilot.press("p")
                    target = replay_session_for_name("nq-research-loop")
                    steps = (app._session_index(target) - app._replay_browser_index) % len(app._replay_sessions)
                    await pilot.press(*(["down"] * steps), "enter")
                    self.assertFalse(app._replay_browser_open)
                    self.assertEqual(app._active_replay_session.name, target.name)
                    self.assertEqual(app.config.replay_path, target.path)
                    self.assertEqual(app.consumer.target_underlying, "NQ")
                    self.assertEqual(app.config.contract_multiplier, 20)
                    self.assertEqual(app.consumer.engine.multiplier, 20)
                    self.assertEqual(app.consumer.runtime_status, "REPLAY")
                    self.assertGreater(app.consumer.message_count, 0)
                    self.assertGreater(table.row_count, 0)
                    self.assertEqual(
                        {contract["symbol"] for contract in app.consumer.contract_state.values()},
                        {"NQ"},
                    )
                    self.assertEqual(app._last_data["multiplier_provenance"]["effective_multipliers"], [20.0])

    async def test_close_and_load_return_navigation_to_table(self):
        app = _app()
        await seed_demo_session(app.consumer)
        selected_rows = []

        def observe_selection(message):
            if isinstance(message, DataTable.RowSelected) and message.control.id == "gex-table":
                selected_rows.append(message.cursor_row)

        async with app.run_test(size=(140, 42), message_hook=observe_selection) as pilot:
            await pilot.pause()
            table = app.query_one("#gex-table", DataTable)
            original_config = app.config
            original_count = app.consumer.message_count
            await pilot.press("down")
            self.assertEqual(table.cursor_row, 1)
            await pilot.press("p", "down")
            await pilot.pause()
            self.assertIn("select_replay_session", self._footer_actions(app))
            self.assertIn("close_replay_browser", self._footer_actions(app))
            self.assertEqual(table.cursor_row, 1)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIn("select_replay_session", self._footer_actions(app))
            self.assertNotIn("close_replay_browser", self._footer_actions(app))
            self.assertFalse(app._replay_browser_open)
            self.assertIs(app.config, original_config)
            self.assertEqual(app.consumer.message_count, original_count)
            await pilot.press("up", "enter")
            self.assertEqual(table.cursor_row, 0)
            self.assertEqual(selected_rows[-1], 0)
            self.assertIs(app.config, original_config)
            await pilot.press("p", "down", "p")
            await pilot.pause()
            self.assertNotIn("select_replay_session", self._footer_actions(app))
            self.assertFalse(app._replay_browser_open)
            self.assertIs(app.config, original_config)
            await pilot.press("p", "enter")
            await pilot.pause()
            self.assertNotIn("select_replay_session", self._footer_actions(app))
            self.assertFalse(app._replay_browser_open)
            loaded_config = app.config
            loaded_count = app.consumer.message_count
            selected_rows.clear()
            await pilot.press("down", "enter")
            self.assertEqual(table.cursor_row, 1)
            self.assertEqual(selected_rows[-1], 1)
            self.assertIs(app.config, loaded_config)
            self.assertEqual(app.consumer.message_count, loaded_count)

    async def test_keyboard_selection_wraps_in_both_directions(self):
        app = _app()
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.press("p")
            await pilot.press(*(["up"] * (app._replay_browser_index + 1)))
            self.assertEqual(app._replay_browser_index, len(app._replay_sessions) - 1)
            await pilot.press("down")
            self.assertEqual(app._replay_browser_index, 0)
            await pilot.press("escape")
            self.assertEqual(app.consumer.message_count, 0)

    async def test_overlay_and_resize_do_not_steal_picker_or_table_keys(self):
        app = _app()
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.press("p", "down")
            selected = app._replay_browser_index
            overlay = KeyboardOverlay()
            await app.push_screen(overlay)
            await pilot.pause()
            await pilot.press("down", "enter")
            self.assertEqual(overlay.selected_row, 1)
            self.assertEqual(app._replay_browser_index, selected)
            self.assertTrue(app._replay_browser_open)
            self.assertEqual(app.consumer.message_count, 0)
            await pilot.press("p")
            self.assertTrue(app._replay_browser_open)
            self.assertEqual(app._replay_browser_index, selected)
            await pilot.resize_terminal(80, 24)
            await pilot.resize_terminal(180, 54)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(app.screen, app._refresh_screen_owner)
            self.assertTrue(app._replay_browser_open)
            self.assertEqual(app._replay_browser_index, selected)
            await pilot.press("up", "enter")
            self.assertEqual(app._active_replay_session.name, "zero-gamma-flip")
            self.assertFalse(app._replay_browser_open)

    async def test_keyboard_cannot_replace_live_or_captured_source(self):
        for mode, allowed in (("live", True), ("replay", False)):
            with self.subTest(mode=mode, allowed=allowed):
                app = _app(data_mode=mode, allow_replay_switching=allowed)
                original_config = app.config
                with patch.object(app, "_load_replay_messages") as load:
                    async with app.run_test(size=(140, 42)) as pilot:
                        await pilot.press("p", "down", "enter", "escape")
                        self.assertFalse(app._replay_browser_open)
                        self.assertIs(app.config, original_config)
                        self.assertEqual(app.consumer.message_count, 0)
                    load.assert_not_called()

    async def test_failed_keyboard_load_keeps_selection_and_can_retry(self):
        app = _app()
        await seed_demo_session(app.consumer)
        original_config = app.config
        original_count = app.consumer.message_count
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.press("p", "down")
            selected = app._replay_browser_index
            for error in (ValueError("invalid replay"), FileNotFoundError("missing replay")):
                with self.subTest(error=type(error).__name__):
                    with patch.object(app, "_load_replay_messages", side_effect=error):
                        await pilot.press("enter")
                    self.assertTrue(app._replay_browser_open)
                    self.assertEqual(app._replay_browser_index, selected)
                    self.assertIs(app.config, original_config)
                    self.assertEqual(app.consumer.message_count, original_count)
                    self.assertTrue(any("replay load failed" in event for event in app._events))
            await pilot.press("enter")
            self.assertFalse(app._replay_browser_open)
            self.assertEqual(app._active_replay_session.name, "expiration-compression")


if __name__ == "__main__":
    unittest.main()

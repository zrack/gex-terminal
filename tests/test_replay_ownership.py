import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal import cli
from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.replay_catalog import replay_session_for_name
from gex_terminal.tui import GexTerminalApp


class ReplayOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_settles_old_writer_before_interactive_replacement(self):
        for clock in ("fixed", "event"):
            with self.subTest(clock=clock), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "old.jsonl"
                messages = [
                    {"type": "underlying_tick", "symbol": "ES", "price": 5950,
                     "timestamp": "2026-08-01T14:00:00Z"},
                    {"type": "options_volume_tick", "strike": 5950, "option_type": "C",
                     "volume": 10, "iv": .2, "timestamp": "2026-08-01T14:00:01Z"},
                    {"type": "options_volume_tick", "strike": 9999, "option_type": "C",
                     "volume": 10, "iv": .2, "timestamp": "2026-08-01T14:00:02Z"},
                ]
                source.write_text("\n".join(json.dumps(message) for message in messages))
                old_writer_waiting = asyncio.Event()
                never_released = asyncio.Event()
                observed = {}

                def build_adapter(consumer, config):
                    async def controlled_sleep(delay):
                        if consumer.message_count == 2:
                            old_writer_waiting.set()
                            await never_released.wait()
                        await asyncio.sleep(0)
                    return ReplayAdapter(
                        consumer, config.replay_path, delay_seconds=.1,
                        replay_clock=clock, sleep=controlled_sleep,
                    )

                async def interactive_run(app):
                    async with app.run_test(size=(160, 48)):
                        await asyncio.wait_for(old_writer_waiting.wait(), 3)
                        previous_writer = app._source_task
                        self.assertIsNotNone(previous_writer)
                        self.assertFalse(previous_writer.done())
                        await app.action_cycle_replay_session()
                        app._replay_browser_index = app._session_index(
                            replay_session_for_name("zero-gamma-flip")
                        )
                        await app.action_select_replay_session()
                        self.assertTrue(previous_writer.cancelled())
                        self.assertIsNone(app._source_task)
                        self.assertNotIn(9999, app.consumer.chain_state)
                        count = app.consumer.message_count
                        never_released.set()
                        await asyncio.sleep(0)
                        self.assertEqual(app.consumer.message_count, count)
                        self.assertNotIn(9999, app.consumer.chain_state)
                        observed["session"] = app._active_replay_session.name

                environment = {key: value for key, value in os.environ.items()
                               if not key.startswith("GEX_")}
                with patch.dict(os.environ, environment, clear=True), patch.object(
                    sys, "argv", ["gex-terminal", "--replay", str(source), "--replay-clock", clock]
                ), patch.object(cli, "build_market_data_adapter", side_effect=build_adapter), patch.object(
                    GexTerminalApp, "run_async", interactive_run
                ):
                    await cli.main()
                self.assertEqual(observed["session"], "zero-gamma-flip")

    async def test_failed_source_blocks_reset_and_preserves_error(self):
        from tests.test_tui_first_run import _config
        from gex_terminal.consumer import StatefulGexConsumer
        from gex_terminal.engine import IntradayGexEngine

        async def broken_source():
            raise ValueError("source failed")

        writer = asyncio.create_task(broken_source())
        await asyncio.sleep(0)
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="replay")
        consumer.current_spot = 123
        app = GexTerminalApp(consumer, _config("replay"), source_task=writer)
        async with app.run_test(size=(160, 48)):
            await app._load_replay_session(replay_session_for_name("trend-day"))
        self.assertEqual(consumer.current_spot, 123)
        self.assertIs(app._source_task, writer)
        errors = await cli._shutdown_runtime_tasks(writer, None, None, consumer, run_failed=False)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)

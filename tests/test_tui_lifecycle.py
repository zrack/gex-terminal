import asyncio
import unittest

from textual.css.query import NoMatches
from textual.screen import Screen

from gex_terminal.cli import seed_demo_session
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.tui import GexTerminalApp


def _config(refresh_interval_seconds: float = 3600.0) -> GexConfig:
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ"),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=refresh_interval_seconds,
        stale_after_seconds=10.0,
        replay_path="sample_data/demo_replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


class ControlledRefreshConsumer(StatefulGexConsumer):
    def __init__(self) -> None:
        super().__init__(IntradayGexEngine(), data_mode="demo")
        self.initial_snapshot_complete = asyncio.Event()
        self.block_stage: str | None = None
        self.stage_started = asyncio.Event()
        self.release_stage = asyncio.Event()
        self.stage_cancelled = asyncio.Event()
        self.snapshot_call_count = 0

    def block_next(self, stage: str) -> None:
        if stage not in {"snapshot", "breakdown"}:
            raise ValueError(f"unsupported refresh stage: {stage}")
        self.block_stage = stage
        self.stage_started = asyncio.Event()
        self.release_stage = asyncio.Event()
        self.stage_cancelled = asyncio.Event()

    async def _block_if_selected(self, stage: str) -> None:
        if self.block_stage != stage:
            return
        self.block_stage = None
        self.stage_started.set()
        try:
            await self.release_stage.wait()
        except asyncio.CancelledError:
            self.stage_cancelled.set()
            raise

    async def process_latest_snapshot(self, *args, **kwargs):
        self.snapshot_call_count += 1
        await self._block_if_selected("snapshot")
        result = await super().process_latest_snapshot(*args, **kwargs)
        self.initial_snapshot_complete.set()
        return result

    async def process_expiry_breakdown(self, *args, **kwargs):
        await self._block_if_selected("breakdown")
        return await super().process_expiry_breakdown(*args, **kwargs)


class TuiRefreshLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def _ready_app(self, *, interval: float = 3600.0):
        consumer = ControlledRefreshConsumer()
        await seed_demo_session(consumer)
        app = GexTerminalApp(consumer, _config(interval))
        context = app.run_test(size=(160, 48))
        pilot = await context.__aenter__()
        await asyncio.wait_for(consumer.initial_snapshot_complete.wait(), 2)
        await pilot.pause()
        return consumer, app, context, pilot

    async def test_screen_owns_interval_and_cancels_inflight_refresh_before_detach(self):
        consumer, app, context, _pilot = await self._ready_app(interval=0.1)
        timer = app._refresh_timer
        self.assertIsNotNone(timer)
        self.assertIs(timer.target, app.screen)

        consumer.block_next("snapshot")
        await asyncio.wait_for(consumer.stage_started.wait(), 2)
        screen = app.screen

        await asyncio.wait_for(context.__aexit__(None, None, None), 2)

        self.assertTrue(consumer.stage_cancelled.is_set())
        self.assertFalse(app.is_running)
        self.assertFalse(screen.is_running)
        self.assertIsNone(timer._task)
        self.assertIsNone(app._exception)

    async def test_refresh_stays_bound_to_dashboard_across_screen_replacement(self):
        consumer, app, context, pilot = await self._ready_app()
        try:
            app._refresh_timer.pause()
            owner = app._refresh_screen_owner
            self.assertIs(owner, app.screen)
            baseline = (app._last_data, app._last_breakdown, tuple(app._gex_flow))

            consumer.block_next("snapshot")
            refresh = asyncio.create_task(app.refresh_terminal_data())
            await asyncio.wait_for(consumer.stage_started.wait(), 2)
            await app.push_screen(Screen())
            await pilot.pause()
            self.assertIsNot(app.screen, owner)

            consumer.release_stage.set()
            await asyncio.wait_for(refresh, 2)
            self.assertEqual(
                (app._last_data, app._last_breakdown, tuple(app._gex_flow)),
                baseline,
            )

            calls = consumer.snapshot_call_count
            await app.refresh_terminal_data()
            self.assertEqual(consumer.snapshot_call_count, calls)

            app.pop_screen()
            await pilot.pause()
            self.assertIs(app.screen, owner)
            await app.refresh_terminal_data()
            self.assertEqual(consumer.snapshot_call_count, calls + 1)
        finally:
            await context.__aexit__(None, None, None)

    async def test_resize_updates_dashboard_owner_behind_pushed_screen(self):
        _consumer, app, context, pilot = await self._ready_app()
        try:
            app._refresh_timer.pause()
            owner = app._refresh_screen_owner
            await app.push_screen(Screen())
            await pilot.pause()
            overlay = app.screen

            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            self.assertFalse(overlay.has_class("compact"))
            self.assertTrue(owner.query_one("#minimum-size-message").display)
            self.assertFalse(owner.query_one("#dashboard").display)

            app.pop_screen()
            await pilot.pause()
            self.assertIs(app.screen, owner)
            self.assertTrue(owner.query_one("#minimum-size-message").display)
            self.assertFalse(owner.query_one("#dashboard").display)

            await pilot.resize_terminal(160, 48)
            await pilot.pause()
            self.assertFalse(owner.query_one("#minimum-size-message").display)
            self.assertTrue(owner.query_one("#dashboard").display)
        finally:
            await context.__aexit__(None, None, None)

    async def test_quit_invalidates_inflight_refresh_before_publication(self):
        consumer, app, context, _pilot = await self._ready_app()
        try:
            app._refresh_timer.pause()
            baseline = (
                app._last_data,
                app._last_breakdown,
                app._last_refresh_at,
                tuple(app._gex_flow),
            )
            consumer.block_next("breakdown")
            refresh = asyncio.create_task(app.refresh_terminal_data())
            await asyncio.wait_for(consumer.stage_started.wait(), 2)

            app.exit()
            consumer.release_stage.set()
            await asyncio.wait_for(refresh, 2)

            self.assertEqual(
                (
                    app._last_data,
                    app._last_breakdown,
                    app._last_refresh_at,
                    tuple(app._gex_flow),
                ),
                baseline,
            )
        finally:
            await context.__aexit__(None, None, None)

    async def test_inflight_manual_refresh_does_not_publish_after_teardown(self):
        for stage in ("snapshot", "breakdown"):
            with self.subTest(stage=stage):
                consumer, app, context, _pilot = await self._ready_app()
                app._refresh_timer.pause()
                baseline = (
                    app._last_data,
                    app._last_breakdown,
                    app._last_latency_ms,
                    tuple(app._latencies),
                    app._last_refresh_at,
                    tuple(app._gex_flow),
                )
                consumer.block_next(stage)
                refresh = asyncio.create_task(app.refresh_terminal_data())
                await asyncio.wait_for(consumer.stage_started.wait(), 2)
                screen = app.screen

                await asyncio.wait_for(context.__aexit__(None, None, None), 2)
                self.assertFalse(app.is_running)
                self.assertFalse(screen.is_running)
                consumer.release_stage.set()
                await asyncio.wait_for(refresh, 2)

                self.assertEqual(
                    (
                        app._last_data,
                        app._last_breakdown,
                        app._last_latency_ms,
                        tuple(app._latencies),
                        app._last_refresh_at,
                        tuple(app._gex_flow),
                    ),
                    baseline,
                )
                self.assertIsNone(app._exception)

    async def test_missing_required_widget_still_raises_while_screen_is_current(self):
        _consumer, app, context, pilot = await self._ready_app()
        try:
            app._refresh_timer.pause()
            await pilot.pause()
            await app.query_one("#feed-websocket").remove()

            with self.assertRaises(NoMatches):
                await app.refresh_terminal_data()
        finally:
            await context.__aexit__(None, None, None)


if __name__ == "__main__":
    unittest.main()

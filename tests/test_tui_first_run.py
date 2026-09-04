import unittest
import json
from dataclasses import replace

from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.tui import GexTerminalApp
from gex_terminal.replay_catalog import replay_session_for_name


def _config(data_mode="demo"):
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ", "SPX", "QQQ"),
        data_mode=data_mode,
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="sample_data/demo_replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


class FirstRunTerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_assumptions_do_not_partially_mutate_runtime(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=50), data_mode="demo")
        config = _config()
        app = GexTerminalApp(consumer, config)
        with self.assertRaises(ValueError):
            await app._apply_terminal_assumptions(risk_free_rate=float("nan"), contract_multiplier=20)
        self.assertIs(app.config, config)
        self.assertEqual(consumer.risk_free_rate, .045)
        self.assertEqual(consumer.engine.multiplier, 50)
        with self.assertRaises(ValueError):
            await app._apply_terminal_assumptions(contract_multiplier=20.5)
        self.assertEqual(consumer.engine.multiplier, 50)

    def test_demo_mode_starts_with_zero_gamma_flip_as_next_replay(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=50), data_mode="demo")
        app = GexTerminalApp(consumer=consumer, config=_config())

        self.assertEqual(app._next_replay_session().name, "zero-gamma-flip")
        self.assertIn("Zero-Gamma Flip", app._replay_label())

    async def test_replay_selector_loads_bundled_session_in_terminal(self):
        config = replace(_config(), symbol="NQ", contract_multiplier=20)
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=config.contract_multiplier),
            target_underlying=config.symbol,
            risk_free_rate=config.risk_free_rate,
            data_mode=config.data_mode,
            stale_after_seconds=config.stale_after_seconds,
        )
        app = GexTerminalApp(consumer=consumer, config=config)

        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause(0.1)
            await app.action_cycle_replay_session()
            app.action_replay_browser_down()
            app.action_replay_browser_up()
            await app.action_select_replay_session()
            await pilot.pause(0.1)

        data = await consumer.process_latest_snapshot(days_to_expiry=config.days_to_expiry)

        self.assertNotIn("error", data)
        self.assertEqual(app.config.data_mode, "replay")
        self.assertEqual(
            app.config.replay_path,
            replay_session_for_name("zero-gamma-flip").path,
        )
        self.assertEqual(consumer.runtime_status, "REPLAY")
        self.assertEqual(consumer.target_underlying, "ES")
        self.assertEqual(app.config.contract_multiplier, 50)
        self.assertEqual(consumer.engine.multiplier, 50)

    async def test_replay_browser_can_browse_and_close_without_loading(self):
        config = _config()
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=config.contract_multiplier),
            target_underlying=config.symbol,
            risk_free_rate=config.risk_free_rate,
            data_mode=config.data_mode,
            stale_after_seconds=config.stale_after_seconds,
        )
        app = GexTerminalApp(consumer=consumer, config=config)

        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause(0.1)
            await app.action_cycle_replay_session()

            self.assertTrue(app._replay_browser_open)
            self.assertEqual(app._selected_replay_session().name, "zero-gamma-flip")

            app.action_replay_browser_down()

            self.assertEqual(app._selected_replay_session().name, "expiration-compression")

            app.action_close_replay_browser()

            self.assertFalse(app._replay_browser_open)
            self.assertEqual(app.config.data_mode, "demo")

    async def test_replay_switch_is_blocked_during_session_capture(self):
        config = _config(data_mode="replay")
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=config.contract_multiplier),
            target_underlying=config.symbol,
            data_mode=config.data_mode,
        )
        app = GexTerminalApp(
            consumer=consumer,
            config=config,
            allow_replay_switching=False,
        )
        original_path = app.config.replay_path

        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause(0.1)
            await app.action_cycle_replay_session()
            await app._load_replay_session(replay_session_for_name("trend-day"))

        self.assertFalse(app._replay_browser_open)
        self.assertEqual(app.config.replay_path, original_path)
        self.assertEqual(consumer.message_count, 0)
        self.assertTrue(
            any("active session capture" in event for event in app._events),
            app._events,
        )

    async def test_terminal_assumption_controls_recompute_loaded_replay(self):
        config = _config()
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=config.contract_multiplier),
            target_underlying=config.symbol,
            risk_free_rate=config.risk_free_rate,
            data_mode=config.data_mode,
            stale_after_seconds=config.stale_after_seconds,
        )
        app = GexTerminalApp(consumer=consumer, config=config)

        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.1)
            await app.action_cycle_replay_session()
            await app.action_select_replay_session()
            await pilot.pause(0.1)
            baseline = await consumer.process_latest_snapshot(
                days_to_expiry=app.config.days_to_expiry
            )

            await app.action_cycle_multiplier_assumption()
            multiplier_data = await consumer.process_latest_snapshot(
                days_to_expiry=app.config.days_to_expiry
            )
            await app.action_cycle_expiry_assumption()
            await app.action_cycle_rate_assumption()

        self.assertEqual(app.config.contract_multiplier, 20)
        self.assertAlmostEqual(app.config.days_to_expiry, 0.05)
        self.assertAlmostEqual(app.config.risk_free_rate, 0.05)
        self.assertAlmostEqual(consumer.risk_free_rate, 0.05)
        self.assertEqual(consumer.engine.multiplier, 20)
        self.assertAlmostEqual(
            multiplier_data["total_net_gex"] / baseline["total_net_gex"],
            0.4,
            places=6,
        )

    async def test_terminal_cycles_first_class_expiry_filter(self):
        config = _config()
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="demo",
            expiry_filter="all",
        )
        consumer.current_spot = 100.0
        for expiry, strike in (("0DTE", 100), ("2026-07-24", 105)):
            await consumer.update_market_state(json.dumps({
                "type": "options_volume_tick",
                "strike": strike,
                "option_type": "C",
                "volume": 100,
                "iv": 0.2,
                "expiry": expiry,
                "timestamp": "2026-07-17T15:00:00Z",
            }))
        app = GexTerminalApp(consumer=consumer, config=config)

        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.1)
            await app.action_cycle_expiry_filter()
            await pilot.pause(0.1)

        self.assertEqual(app.config.expiry_filter, "0dte")
        self.assertEqual(consumer.expiry_filter, "0dte")
        self.assertEqual(app._last_data["expiry_filter"], "0dte")
        self.assertEqual(app._last_data["strikes"], [100.0])


if __name__ == "__main__":
    unittest.main()

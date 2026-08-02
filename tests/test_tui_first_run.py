import unittest

from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.tui import GexTerminalApp


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
    def test_demo_mode_starts_with_zero_gamma_flip_as_next_replay(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=50), data_mode="demo")
        app = GexTerminalApp(consumer=consumer, config=_config())

        self.assertEqual(app._next_replay_session().name, "zero-gamma-flip")
        self.assertIn("Zero-Gamma Flip", app._replay_label())

    async def test_replay_selector_loads_bundled_session_in_terminal(self):
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
            app.action_replay_browser_down()
            app.action_replay_browser_up()
            await app.action_select_replay_session()
            await pilot.pause(0.1)

        data = await consumer.process_latest_snapshot(days_to_expiry=config.days_to_expiry)

        self.assertNotIn("error", data)
        self.assertEqual(app.config.data_mode, "replay")
        self.assertEqual(app.config.replay_path, "sample_data/es_zero_gamma_flip.jsonl")
        self.assertEqual(consumer.runtime_status, "REPLAY")
        self.assertEqual(consumer.target_underlying, "ES")

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


if __name__ == "__main__":
    unittest.main()

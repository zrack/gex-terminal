import time
import unittest
import json
from datetime import datetime, timezone

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.snapshot import build_snapshot


class StatefulGexConsumerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _v2_option(
        *,
        contract_id="ES-20260619-C-5950",
        expiry="2026-06-19",
        expiry_timestamp="2026-06-19T20:00:00Z",
        strike=5950,
        option_type="C",
        volume=100,
        sequence=1,
        volume_semantics="incremental",
        aggressor_side=None,
        direction_source=None,
    ):
        message = {
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "test",
            "contract_id": contract_id,
            "symbol": "ES",
            "expiry": expiry,
            "expiry_timestamp": expiry_timestamp,
            "strike": strike,
            "option_type": option_type,
            "volume": volume,
            "iv": 0.20,
            "iv_source": "provider",
            "instrument_class": "futures_option",
            "volume_semantics": volume_semantics,
            "position_source": "trade_volume",
            "event_time": "2026-06-18T14:00:00Z",
            "sequence": sequence,
        }
        if aggressor_side is not None:
            message["aggressor_side"] = aggressor_side
        if direction_source is not None:
            message["direction_source"] = direction_source
        return message

    def test_demo_mode_reports_sim(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="demo")

        self.assertEqual(consumer.runtime_status, "SIM")

    async def test_snapshot_preserves_mixed_multiplier_rows_and_fallback(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=50), data_mode="replay")
        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick", "symbol": "ES", "price": 5950,
        }))
        for index, multiplier in enumerate((100, 20, None)):
            message = self._v2_option(contract_id=f"contract-{index}", strike=5900 + index * 50)
            if multiplier is not None:
                message["contract_multiplier"] = multiplier
            await consumer.update_market_state(json.dumps(message))
        data = await consumer.process_latest_snapshot(0.25)
        snapshot = build_snapshot(
            symbol="ES", spot=5950, session_open=5950, days_to_expiry=0.25,
            contract_multiplier=50, risk_free_rate=0.045,
            data=data, chain_state=consumer.chain_state,
        )
        self.assertIsNone(snapshot["effective_contract_multiplier"])
        provenance = snapshot["model"]["multiplier_provenance"]
        self.assertEqual(provenance["effective_multipliers"], [20.0, 50.0, 100.0])
        self.assertEqual(provenance["fallback_row_count"], 1)
        self.assertEqual(
            {row["contract_id"]: (row["multiplier"], row["source"]) for row in provenance["rows"]},
            {"contract-0": (100.0, "contract"), "contract-1": (20.0, "contract"),
             "contract-2": (50.0, "configured_fallback")},
        )

    async def test_legacy_snapshot_reports_actual_configured_multiplier(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=20), data_mode="replay")
        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick", "symbol": "ES", "price": 5950,
        }))
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick", "strike": 5950,
            "option_type": "C", "volume": 10, "iv": 0.2,
        }))
        data = await consumer.process_latest_snapshot(0.25)
        self.assertEqual(data["multiplier_provenance"], {
            "status": "configured_fallback", "effective_multipliers": [20.0],
            "configured_fallback_multiplier": 20.0,
            "fallback_row_count": 1, "rows": [],
        })
        with self.assertRaisesRegex(ValueError, "calculation fallback"):
            build_snapshot(
                symbol="ES", spot=5950, session_open=5950, days_to_expiry=0.25,
                contract_multiplier=50, risk_free_rate=0.045,
                data=data, chain_state=consumer.chain_state,
            )

    async def test_contract_multiplier_enrichment_is_preserved_and_conflicts_rejected(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="replay")
        first = self._v2_option(sequence=1)
        await consumer.update_market_state(json.dumps(first))
        enriched = {**first, "sequence": 2, "contract_multiplier": 50}
        await consumer.update_market_state(json.dumps(enriched))
        await consumer.update_market_state(json.dumps({**first, "sequence": 3}))
        state = next(iter(consumer.contract_state.values()))
        self.assertEqual(state["contract_multiplier"], 50)
        self.assertEqual(state["accumulated_volume"], 300)
        for source in ("trade_volume", "open_interest"):
            await consumer.update_market_state(json.dumps({
                **enriched, "sequence": 4, "contract_multiplier": 100,
                "position_source": source,
            }))
        self.assertEqual(consumer.malformed_message_count, 2)
        self.assertEqual(len(consumer.contract_state), 1)
        self.assertEqual(state["contract_multiplier"], 50)
        self.assertEqual(state["accumulated_volume"], 300)

    def test_live_mode_reports_live_after_recent_message(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")
        consumer.mark_connected()
        consumer.last_message_at = time.monotonic()

        self.assertEqual(consumer.runtime_status, "LIVE")

    def test_live_mode_reports_stale_after_timeout(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(),
            data_mode="live",
            stale_after_seconds=1.0,
        )
        consumer.mark_connected()
        consumer.last_message_at = time.monotonic() - 2.0

        self.assertEqual(consumer.runtime_status, "STALE")

    def test_live_mode_reports_disconnected_after_connection_loss(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")

        consumer.mark_connected()
        consumer.mark_disconnected()
        quality = consumer.feed_quality_snapshot()

        self.assertEqual(consumer.runtime_status, "DISCONNECTED")
        self.assertEqual(quality["connection_state"], "DISCONNECTED")
        self.assertEqual(quality["health"], "down")

    async def test_first_underlying_tick_sets_session_open(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="replay")

        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick",
            "symbol": "ES",
            "price": 5943.25,
        }))
        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick",
            "symbol": "ES",
            "price": 5960.0,
        }))

        self.assertEqual(consumer.session_open, 5943.25)
        self.assertEqual(consumer.current_spot, 5960.0)

    async def test_reset_state_clears_market_and_quality_counters(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")
        consumer.mark_connected()
        consumer.mark_subscribed(4)
        consumer.record_dropped_message()
        await consumer.update_market_state(json.dumps({
            "type": "underlying_tick",
            "symbol": "ES",
            "price": 5943.25,
        }))
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick",
            "strike": 5950,
            "option_type": "C",
            "volume": 100,
            "iv": 0.15,
        }))

        await consumer.reset_state(data_mode="replay", target_underlying="NQ")

        self.assertEqual(consumer.data_mode, "REPLAY")
        self.assertEqual(consumer.target_underlying, "NQ")
        self.assertEqual(consumer.runtime_status, "CONNECTED")
        self.assertEqual(consumer.current_spot, 0.0)
        self.assertEqual(consumer.chain_state, {})
        self.assertEqual(consumer.message_count, 0)
        self.assertEqual(consumer.dropped_message_count, 0)
        self.assertEqual(consumer.subscription_status, "not_subscribed")

    def test_records_live_adapter_subscription_and_reconnect_diagnostics(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="live")

        consumer.mark_connected()
        consumer.mark_reconnected()
        consumer.mark_subscribed(12)

        quality = consumer.feed_quality_snapshot()

        self.assertEqual(quality["reconnect_count"], 1)
        self.assertEqual(quality["subscribed_symbol_count"], 12)
        self.assertEqual(quality["subscription_status"], "subscribed")

    async def test_v1_last_iv_and_scalar_calculation_remain_legacy_compatible(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="replay",
        )
        consumer.current_spot = 5950.0
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick",
            "strike": 5950,
            "option_type": "C",
            "volume": 100,
            "iv": 0.18,
        }))
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick",
            "strike": 5950,
            "option_type": "P",
            "volume": 40,
            "iv": 0.22,
        }))

        data = await consumer.process_latest_snapshot(days_to_expiry=0.25)

        self.assertEqual(consumer.chain_state[5950.0], {"C": 100, "P": 40, "iv": 0.22})
        self.assertEqual(data["calculation_mode"], "legacy_v1")
        self.assertEqual(data["pricing_models"], ["black_scholes"])
        self.assertEqual(data["contract_count"], 1)

    async def test_same_strike_across_expiries_remains_contract_separate(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        consumer.current_spot = 5950.0
        first = self._v2_option()
        second = self._v2_option(
            contract_id="ES-20260626-C-5950",
            expiry="2026-06-26",
            expiry_timestamp="2026-06-26T20:00:00Z",
            volume=75,
        )
        await consumer.update_market_state(json.dumps(first))
        await consumer.update_market_state(json.dumps(second))

        data = await consumer.process_latest_snapshot(
            days_to_expiry=0.25,
            as_of=datetime(2026, 6, 18, 14, tzinfo=timezone.utc),
        )

        self.assertEqual(len(consumer.contract_state), 2)
        self.assertEqual(consumer.chain_state[5950.0]["C"], 175)
        self.assertEqual(data["calculation_mode"], "contract_v2")
        self.assertEqual(data["contract_count"], 2)
        self.assertEqual(data["strikes"], [5950.0])
        self.assertEqual(data["available_expiries"], ["2026-06-19", "2026-06-26"])

    async def test_v2_iv_source_is_canonicalized_before_quality_accounting(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        consumer.mark_connected()
        message = {**self._v2_option(), "iv_source": "PROVIDER"}

        await consumer.update_market_state(json.dumps(message))

        state = next(iter(consumer.contract_state.values()))
        self.assertEqual(state["iv_source"], "provider")
        self.assertEqual(consumer.fallback_iv_tick_count, 0)
        self.assertEqual(consumer.feed_quality_snapshot()["health"], "healthy")

    async def test_expiry_timestamp_overrides_stale_dte_hints(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
        )
        consumer.current_spot = 5950.0
        message = {
            **self._v2_option(),
            "days_to_expiry": 99.0,
        }
        await consumer.update_market_state(json.dumps(message))

        as_of = datetime(2026, 6, 18, 14, tzinfo=timezone.utc)
        data = await consumer.process_latest_snapshot(
            days_to_expiry=0.25,
            as_of=as_of,
            expiry_days={"2026-06-19": 88.0},
        )
        exact_dte = (datetime(2026, 6, 19, 20, tzinfo=timezone.utc) - as_of).total_seconds() / 86_400
        expected = consumer.engine.compute_intraday_gex_matrix(
            spot_price=5950.0,
            strikes=[5950.0],
            days_to_expiry=[exact_dte],
            risk_free_rate=consumer.risk_free_rate,
            implied_vols=[0.20],
            accumulated_call_vol=[100.0],
            accumulated_put_vol=[0.0],
            pricing_model=["black_76"],
            contract_multipliers=[50.0],
        )

        self.assertAlmostEqual(data["total_net_gex"], expected["total_net_gex"])

    async def test_prior_date_only_expiry_is_not_priced_with_fallback_dte(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="SPY",
        )
        consumer.current_spot = 500.0
        message = {
            **self._v2_option(
                contract_id="SPY-20260618-C-500",
                expiry="2026-06-18",
                expiry_timestamp=None,
                strike=500,
            ),
            "symbol": "SPY",
            "instrument_class": "equity_option",
        }
        await consumer.update_market_state(json.dumps(message))

        data = await consumer.process_latest_snapshot(
            days_to_expiry=30.0,
            as_of=datetime(2026, 6, 19, 14, tzinfo=timezone.utc),
        )

        self.assertIn("No active option contracts", data["error"])

    async def test_cumulative_updates_replace_and_duplicates_are_ignored(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), target_underlying="ES")
        first = self._v2_option(volume=100, volume_semantics="cumulative", sequence=10)
        await consumer.update_market_state(json.dumps(first))
        await consumer.update_market_state(json.dumps({**first, "volume": 125, "sequence": 11}))
        await consumer.update_market_state(json.dumps({**first, "volume": 500, "sequence": 11}))
        await consumer.update_market_state(json.dumps({**first, "volume": 10, "sequence": 12}))

        state = next(iter(consumer.contract_state.values()))
        self.assertEqual(state["accumulated_volume"], 10)
        self.assertEqual(consumer.chain_state[5950.0]["C"], 10)
        self.assertEqual(consumer.duplicate_message_count, 1)
        self.assertEqual(consumer.cumulative_reset_count, 1)

    async def test_directionalized_volume_accumulates_beside_unchanged_default(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
        )
        consumer.current_spot = 5950.0
        buy = self._v2_option(
            volume=100,
            sequence=1,
            aggressor_side="buy",
            direction_source="provider",
        )
        sell = self._v2_option(
            volume=40,
            sequence=2,
            aggressor_side="sell",
            direction_source="provider",
        )
        await consumer.update_market_state(json.dumps(buy))
        await consumer.update_market_state(json.dumps(sell))

        data = await consumer.process_latest_snapshot(
            days_to_expiry=0.25,
            as_of=datetime(2026, 6, 18, 14, tzinfo=timezone.utc),
        )

        state = next(iter(consumer.contract_state.values()))
        self.assertEqual(state["accumulated_volume"], 140)
        self.assertEqual(state["directional_volume"], {
            "buy": 100,
            "sell": 40,
            "unknown": 0,
        })
        self.assertEqual(data["call_volume"], [140.0])
        self.assertGreater(data["total_net_gex"], 0.0)
        directional = data["directionalized"]
        self.assertEqual(directional["status"], "available")
        self.assertEqual(directional["directional_coverage"], 1.0)
        self.assertLess(directional["total_net_gex"], 0.0)
        self.assertEqual(directional["direction_sources"], ["provider"])

    async def test_missing_trade_side_is_reported_as_insufficient_coverage(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), target_underlying="ES")
        consumer.current_spot = 5950.0
        await consumer.update_market_state(json.dumps(self._v2_option(volume=100)))

        data = await consumer.process_latest_snapshot(
            days_to_expiry=0.25,
            as_of=datetime(2026, 6, 18, 14, tzinfo=timezone.utc),
        )

        directional = data["directionalized"]
        self.assertEqual(directional["status"], "insufficient_directional_coverage")
        self.assertEqual(directional["known_direction_volume"], 0.0)
        self.assertEqual(directional["unknown_direction_volume"], 100.0)

    async def test_mixed_v1_v2_session_reports_legacy_fallback(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
        )
        consumer.current_spot = 5950.0
        await consumer.update_market_state(json.dumps({
            "type": "options_volume_tick",
            "strike": 5900,
            "option_type": "P",
            "volume": 40,
            "iv": 0.20,
        }))
        await consumer.update_market_state(json.dumps(self._v2_option()))

        data = await consumer.process_latest_snapshot(days_to_expiry=0.25)

        self.assertEqual(data["calculation_mode"], "mixed_legacy_fallback")
        self.assertEqual(data["pricing_models"], ["black_scholes"])
        self.assertGreater(data["legacy_contract_fallback_count"], 0)

    async def test_trade_volume_and_open_interest_are_not_silently_summed(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
        )
        consumer.current_spot = 5950.0
        trade = self._v2_option(
            volume=25,
            volume_semantics="cumulative",
            sequence=1,
        )
        open_interest = {
            **trade,
            "volume": 500,
            "position_source": "open_interest",
            "sequence": 2,
        }
        await consumer.update_market_state(json.dumps(open_interest))
        await consumer.update_market_state(json.dumps(trade))

        data = await consumer.process_latest_snapshot(
            days_to_expiry=0.25,
            as_of=datetime(2026, 6, 18, 14, tzinfo=timezone.utc),
        )

        self.assertEqual(len(consumer.contract_state), 2)
        self.assertEqual(data["call_volume"], [25.0])
        self.assertEqual(data["position_sources"], ["trade_volume"])
        self.assertEqual(data["position_source_conflict_count"], 1)

    async def test_drop_strikes_removes_canonical_and_projected_state(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), target_underlying="ES")
        await consumer.update_market_state(json.dumps(self._v2_option()))

        removed = await consumer.drop_strikes([5950])

        self.assertEqual(removed, 1)
        self.assertEqual(consumer.contract_state, {})
        self.assertEqual(consumer.chain_state, {})


if __name__ == "__main__":
    unittest.main()

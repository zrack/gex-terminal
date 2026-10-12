"""Rollover isolation through normalized state and the Databento handler."""

import copy
import json
import unittest

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import validate_normalized_message
from tests.test_databento_regressions import adapter_for, definition, quote, statistics, trade
from tests.test_open_interest_reference import _oi_message


def underlying(provider="databento", contract_id="202", **updates):
    return {
        "schema_version": 2, "type": "underlying_tick", "provider": provider,
        "symbol": "ES", "price": 6000.0, "event_time": "2026-08-06T16:00:00Z",
        "contract_id": contract_id, **updates,
    }


class UnderlyingIdentityContractTests(unittest.TestCase):
    def test_optional_identifiers_are_validated(self):
        validate_normalized_message(underlying())
        validate_normalized_message(_oi_message(underlying_contract_id="202"))
        for invalid in (None, "", "  ", True, 1.5, {}, []):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "contract_id"):
                    validate_normalized_message(underlying(contract_id=invalid))
                with self.assertRaisesRegex(ValueError, "underlying_contract_id"):
                    validate_normalized_message(_oi_message(underlying_contract_id=invalid))

    def test_option_link_requires_v2_option_message(self):
        for message in (
            underlying(underlying_contract_id="202"),
            _oi_message(schema_version=1, underlying_contract_id="202"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, "schema-v2 option"):
                validate_normalized_message(message)


class UnderlyingIdentityConsumerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=50), target_underlying="ES")

    async def update(self, message):
        return await self.consumer.update_market_state(json.dumps(message))

    def selected(self):
        return self.consumer._select_position_states(list(self.consumer.contract_state.values()))[0]

    async def test_rollover_quarantines_both_position_sources_without_erasing_provenance(self):
        await self.update(underlying())
        await self.update(_oi_message(underlying_contract_id="202"))
        trade_message = _oi_message(underlying_contract_id="202", position_source="trade_volume",
                                    volume_semantics="incremental", volume=7)
        trade_message.pop("open_interest_reference_date")
        trade_message.pop("open_interest_update_action")
        await self.update(trade_message)
        retained = copy.deepcopy(self.consumer.contract_state)
        self.assertTrue(await self.update(underlying(contract_id="303", price=6100,
                                                   event_time="2026-08-06T16:01:00Z")))
        self.assertEqual(self.consumer.contract_state, retained)
        self.assertEqual(self.selected(), [])
        self.assertEqual(self.consumer.chain_state, {})
        self.assertEqual(await self.consumer.process_expiry_breakdown(14), {})
        self.assertIn("error", await self.consumer.process_latest_snapshot(14))
        self.assertEqual(self.consumer.underlying_identity_snapshot()["quarantined_option_states"], 2)

    async def test_current_future_exposure_replaces_quarantined_rows_in_snapshot(self):
        await self.update(underlying())
        await self.update(_oi_message(underlying_contract_id="202"))
        await self.update(underlying(contract_id="303", event_time="2026-08-06T16:01:00Z"))
        await self.update(_oi_message(contract_id="102", underlying_contract_id="303", volume=33))
        snapshot = await self.consumer.process_latest_snapshot(14)
        self.assertEqual(snapshot["selected_contract_count"], 1)
        self.assertEqual(snapshot["call_volume"], [33.0])
        self.assertEqual(self.consumer.chain_state[6050.0]["C"], 33)

    async def test_stale_equal_and_retired_quotes_cannot_restore_old_future(self):
        await self.update(underlying())
        await self.update(underlying(contract_id="303", price=6100,
                                     event_time="2026-08-06T16:01:00Z"))
        for publication in ("2026-08-06T16:00:30Z", "2026-08-06T16:01:00Z", "2026-08-06T16:02:00Z"):
            with self.subTest(publication=publication):
                self.assertFalse(await self.update(underlying(price=5900, event_time=publication)))
        self.assertEqual(self.consumer.current_spot, 6100)
        self.assertEqual(self.consumer.underlying_identity_snapshot()["current_contract_ids"], {"databento": "303"})

    async def test_same_identity_quote_updates_price_without_quarantining_state(self):
        await self.update(underlying())
        await self.update(_oi_message(underlying_contract_id="202"))
        self.assertTrue(await self.update(underlying(price=6010)))
        self.assertEqual(self.consumer.current_spot, 6010)
        self.assertEqual(len(self.selected()), 1)
        self.assertFalse(await self.update(underlying(price=5900, event_time="2026-08-06T15:59:59Z")))
        self.assertEqual(self.consumer.current_spot, 6010)

    async def test_nanosecond_ordering_preserves_valid_rollover_and_oi_revision(self):
        await self.update(underlying(event_time="2026-08-06T16:00:00.000000001Z"))
        await self.update(_oi_message(underlying_contract_id="202",
                                     event_time="2026-08-06T16:00:00.000000001Z"))
        self.assertTrue(await self.update(_oi_message(underlying_contract_id="202", volume=1300,
                                                     event_time="2026-08-06T16:00:00.000000002Z")))
        self.assertTrue(await self.update(underlying(contract_id="303",
                                                   event_time="2026-08-06T16:00:00.000000002Z")))
        self.assertEqual(self.selected(), [])
        self.assertEqual(self.consumer.underlying_identity_snapshot()["current_contract_ids"], {"databento": "303"})

    async def test_linked_rows_require_same_provider_identity(self):
        await self.update(underlying(provider="other", contract_id="202"))
        await self.update(_oi_message(underlying_contract_id="202"))
        self.assertEqual(self.selected(), [])
        await self.update(underlying())
        self.assertEqual(len(self.selected()), 1)
        await self.update(underlying(provider="other", contract_id="303", event_time="2026-08-06T16:01:00Z"))
        self.assertEqual(len(self.selected()), 1)

    async def test_identity_free_legacy_records_remain_compatible(self):
        tick = underlying()
        tick.pop("contract_id")
        self.assertTrue(await self.update(tick))
        self.assertTrue(await self.update(_oi_message()))
        self.assertEqual(len(self.selected()), 1)
        await self.update(underlying())
        self.assertFalse(await self.update({**tick, "price": 5900, "event_time": "2026-08-06T16:01:00Z"}))
        self.assertEqual(self.consumer.current_spot, 6000)

    async def test_link_metadata_omission_cannot_reactivate_quarantined_position(self):
        await self.update(underlying())
        await self.update(_oi_message(underlying_contract_id="202"))
        await self.update(underlying(contract_id="303", event_time="2026-08-06T16:01:00Z"))
        await self.update(_oi_message(volume=1250, event_time="2026-08-06T16:02:00Z"))
        state = self.consumer.contract_state[("databento", "101", "open_interest")]
        self.assertEqual(state["underlying_contract_id"], "202")
        self.assertFalse(self.consumer.is_contract_underlying_current(state))
        self.assertEqual(self.selected(), [])

    async def test_delete_tombstone_survives_rollover_and_stale_replay(self):
        await self.update(underlying())
        await self.update(_oi_message(underlying_contract_id="202"))
        await self.update(underlying(contract_id="303", event_time="2026-08-06T16:01:00Z"))
        self.assertTrue(await self.update(_oi_message(underlying_contract_id="202", volume=0,
                                                     open_interest_update_action="delete",
                                                     event_time="2026-08-06T16:02:00Z")))
        self.assertFalse(await self.update(_oi_message(underlying_contract_id="202")))
        state = self.consumer.contract_state[("databento", "101", "open_interest")]
        self.assertTrue(state["open_interest_invalidated"])
        self.assertEqual(state["underlying_contract_id"], "202")
        self.assertEqual(self.selected(), [])

    async def test_reset_starts_new_identity_session(self):
        await self.update(underlying())
        await self.update(underlying(contract_id="303", event_time="2026-08-06T16:01:00Z"))
        await self.consumer.reset_state()
        self.assertTrue(await self.update(underlying()))
        self.assertEqual(self.consumer.underlying_identity_snapshot()["retired_contract_ids"], {})


class DatabentoRolloverTests(unittest.IsolatedAsyncioTestCase):
    async def test_es_and_nq_rollover_reject_delayed_quote_adds_and_keep_delete_tombstone(self):
        for root in ("ES", "NQ"):
            with self.subTest(root=root):
                adapter, consumer = adapter_for(root)
                for row in (definition(root), quote(), trade(), statistics()):
                    await adapter._handle_live_record(row)
                await adapter._handle_live_record(quote(instrument_id=303, bid_px_00=6099.75,
                                                        ask_px_00=6100.25, ts_event="2026-08-06T16:01:00Z"))
                self.assertEqual(consumer.chain_state, {})
                for delayed in (quote(), trade(sequence=100), statistics(ts_event="2026-08-06T16:02:00Z")):
                    await adapter._handle_live_record(delayed)
                self.assertEqual(adapter.latest_underlying_instrument_id, 303)
                self.assertEqual(consumer.current_spot, 6100)
                self.assertEqual(consumer.chain_state, {})
                await adapter._handle_live_record(statistics(update_action=2, ts_event="2026-08-06T16:03:00Z"))
                oi = consumer.contract_state[("databento", "101", "open_interest")]
                self.assertTrue(oi["open_interest_invalidated"])
                self.assertEqual(oi["underlying_contract_id"], "202")
                self.assertEqual(adapter.diagnostics()["open_interest"]["current_observations"], 0)
                self.assertEqual(consumer.contract_state[("databento", "101", "trade_volume")]["accumulated_volume"], 7)

    async def test_adapter_emits_provider_scoped_future_identity(self):
        adapter, _ = adapter_for()
        quote_message = adapter._normalize_underlying_quote(quote())
        self.assertEqual(quote_message["contract_id"], "202")
        await adapter._handle_live_record(definition())
        trade_message = adapter._normalize_option_trade_record(trade(), adapter.contract_metadata)
        oi_message = adapter._normalize_statistics_record(statistics(), adapter.contract_metadata)
        self.assertEqual(trade_message["underlying_contract_id"], "202")
        self.assertEqual(oi_message["underlying_contract_id"], "202")

    async def test_raw_nanosecond_quotes_roll_forward_without_rounding_or_stale_cache(self):
        adapter, consumer = adapter_for()
        await adapter._handle_live_record(quote(ts_event=1786032000000000001))
        await adapter._handle_live_record(quote(instrument_id=303, ts_event=1786032000000000002))
        self.assertEqual(adapter.latest_underlying_instrument_id, 303)
        self.assertEqual(adapter.latest_underlying_event_time, "2026-08-06T16:00:00.000000002Z")
        await adapter._handle_live_record(quote(ts_event=1786032000000000001))
        self.assertEqual(adapter.latest_underlying_instrument_id, 303)
        self.assertEqual(consumer.underlying_identity_snapshot()["rejected_quotes"], 1)


if __name__ == "__main__":
    unittest.main()

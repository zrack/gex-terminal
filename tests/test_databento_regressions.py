"""Offline reproductions of issue #35 through provider, consumer and GEX paths."""

import unittest
from datetime import datetime

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from tests.test_databento_live import _FakeLiveClient


EVENT = "2026-08-06T16:00:00Z"
EXPIRY = "2026-08-20T20:00:00Z"
KEY = ("databento", "101", "open_interest")


def definition(root="ES", **overrides):
    return {
        "record_type": "definition", "instrument_id": 101,
        "raw_symbol": f"{root}Q6 C6000", "asset": root,
        "underlying": f"{root}Q6", "underlying_id": 202,
        "strike_price": 6000.0, "instrument_class": "C",
        "expiration": EXPIRY, "contract_multiplier": 2147483647,
        "unit_of_measure_qty": 50.0 if root == "ES" else 20.0,
        "unit_of_measure": "USD", **overrides,
    }


def quote(**overrides):
    return {
        "record_type": "mbp-1", "instrument_id": 202,
        "bid_px_00": 5999.75, "ask_px_00": 6000.25,
        "ts_event": EVENT, **overrides,
    }


def trade(**overrides):
    return {
        "record_type": "trades", "instrument_id": 101,
        "price": 100.0, "size": 7, "side": "B", "iv": 0.22,
        "ts_event": EVENT, **overrides,
    }


def statistics(**overrides):
    return {
        "record_type": "statistics", "instrument_id": 101,
        "stat_type": 9, "quantity": 1200, "update_action": 1,
        "ts_ref": "2026-08-05T00:00:00Z", "ts_event": EVENT,
        **overrides,
    }


def adapter_for(root="ES", **kwargs):
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=50 if root == "ES" else 20),
        target_underlying=root, data_mode="replay",
    )
    return DatabentoAdapter(consumer, target_underlying=root, **kwargs), consumer


class DatabentoIssue35Tests(unittest.IsolatedAsyncioTestCase):
    async def feed(self, adapter, *records):
        for record in records:
            await adapter._handle_live_record(record)

    async def test_deliverable_multiplier_never_scales_es_or_nq_gex(self):
        for root, dollar_multiplier in (("ES", 50), ("NQ", 20)):
            for provider_multiplier in (2147483647, 1, 999):
                with self.subTest(root=root, provider_multiplier=provider_multiplier):
                    adapter, consumer = adapter_for(root)
                    await self.feed(adapter, definition(root, contract_multiplier=provider_multiplier), quote(), trade())
                    snapshot = await consumer.process_latest_snapshot(days_to_expiry=14)
                    self.assertEqual(snapshot["multiplier_provenance"]["effective_multipliers"], [dollar_multiplier])
                    self.assertLess(abs(snapshot["total_net_gex"]), 1_000_000)

    async def test_missing_or_invalid_dollar_units_use_visible_configured_fallback(self):
        for units, quantity in ((None, None), ("MWH", 1), ("USD", 9223372036854775807), ("USD", 0), ("USD", -1)):
            with self.subTest(units=units, quantity=quantity):
                adapter, consumer = adapter_for()
                await self.feed(adapter, definition(unit_of_measure=units, unit_of_measure_qty=quantity), quote(), trade())
                snapshot = await consumer.process_latest_snapshot(days_to_expiry=14)
                self.assertEqual(snapshot["multiplier_provenance"]["effective_multipliers"], [50])
                self.assertEqual(snapshot["multiplier_provenance"]["fallback_row_count"], 1)

    async def test_index_point_units_supply_contract_dollar_multiplier(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(unit_of_measure="IPNT"), quote(), trade())
        snapshot = await consumer.process_latest_snapshot(days_to_expiry=14)
        self.assertEqual(snapshot["multiplier_provenance"]["effective_multipliers"], [50])
        self.assertEqual(snapshot["multiplier_provenance"]["fallback_row_count"], 0)

    async def test_subscriptions_include_quarterly_daily_weekly_and_month_end(self):
        for root, quarterly, monthly, weekly, daily in (
            ("ES", "ES", "EW", "EW", "E"),
            ("NQ", "NQ", "QNE", "QN", "Q"),
        ):
            with self.subTest(root=root):
                client = _FakeLiveClient([])
                adapter, _ = adapter_for(root, live_client_factory=lambda **kwargs: client)
                adapter.api_key = "offline-test-key"
                await adapter.stream_market_data()
                required = {f"{quarterly}.OPT", f"{monthly}.OPT"}
                required.update(f"{weekly}{week}.OPT" for week in range(1, 5))
                required.update(f"{daily}{week}{day}.OPT" for week in range(1, 6) for day in "ABCD")
                by_schema = {request["schema"]: request for request in client.subscriptions}
                for schema in ("trades", "statistics"):
                    self.assertEqual(set(by_schema[schema]["symbols"]), required)
                self.assertEqual(set(by_schema["definition"]["symbols"]), required | {f"{root}.FUT"})

    async def test_each_option_family_reaches_normalized_target_and_gex(self):
        for root, assets in (("ES", ("ES", "E2A", "EW3", "EW")), ("NQ", ("NQ", "Q2A", "QN3", "QNE"))):
            for asset in assets:
                with self.subTest(root=root, asset=asset):
                    adapter, consumer = adapter_for(root)
                    await self.feed(adapter, definition(root, asset=asset), quote(), trade(), statistics())
                    self.assertEqual(adapter._definition_count, 1)
                    for source in ("trade_volume", "open_interest"):
                        self.assertEqual(consumer.contract_state[("databento", "101", source)]["symbol"], root)
                    self.assertIsNotNone(await consumer.process_latest_snapshot(days_to_expiry=14))

    async def test_unrelated_product_and_other_future_month_are_not_priced(self):
        for metadata in (definition(asset="CL", underlying="CLQ6"), definition(asset="E2A", underlying_id=303)):
            with self.subTest(metadata=metadata):
                adapter, consumer = adapter_for()
                await self.feed(adapter, metadata, quote(), trade(), statistics())
                self.assertFalse(consumer.contract_state)

    async def test_declared_subset_is_used_for_every_option_schema(self):
        parents = ("E2A.OPT", "EW.OPT")
        client = _FakeLiveClient([])
        adapter, _ = adapter_for(option_parents=parents, live_client_factory=lambda **kwargs: client)
        adapter.api_key = "offline-test-key"
        await adapter.stream_market_data()
        for request in client.subscriptions:
            if request["schema"] in ("trades", "statistics"):
                self.assertEqual(tuple(request["symbols"]), parents)
            elif request["schema"] == "definition":
                self.assertEqual(tuple(request["symbols"]), (*parents, "ES.FUT"))

    async def test_undefined_oi_quantity_cannot_create_observed_position(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), statistics(quantity=9223372036854775807))
        self.assertNotIn(KEY, consumer.contract_state)
        self.assertEqual(adapter.diagnostics()["open_interest"]["observations"], 0)
        self.assertNotEqual(adapter.diagnostics()["open_interest"]["status"], "observed")

    async def test_oi_before_underlying_quote_cannot_create_exposure(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), statistics())
        self.assertNotIn(KEY, consumer.contract_state)
        await self.feed(adapter, quote())
        self.assertNotIn(KEY, consumer.contract_state)
        await self.feed(adapter, statistics())
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 1200)

    async def test_oi_delete_can_clear_state_without_a_current_underlying_quote(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), statistics())
        adapter.latest_underlying_instrument_id = None
        await self.feed(adapter, statistics(update_action=2, ts_event="2026-08-06T16:01:00Z"))
        self.assertTrue(consumer.contract_state[KEY]["open_interest_invalidated"])
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 0)

    async def test_delete_invalidates_oi_without_erasing_trade_position(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), trade(), statistics())
        await self.feed(adapter, statistics(update_action=2, quantity=9223372036854775807, ts_event="2026-08-06T16:01:00Z"))
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 0)
        self.assertTrue(consumer.contract_state[KEY]["open_interest_invalidated"])
        self.assertEqual(consumer.contract_state[("databento", "101", "trade_volume")]["accumulated_volume"], 7)
        await self.feed(adapter, statistics())
        self.assertTrue(consumer.contract_state[KEY]["open_interest_invalidated"])

    async def test_later_publication_for_older_reference_cannot_replace_oi(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), statistics())
        await self.feed(adapter, statistics(quantity=800, ts_ref="2026-08-04", ts_event="2026-08-06T16:01:00Z"))
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 1200)
        self.assertEqual(consumer.contract_state[KEY]["open_interest_reference_date"], "2026-08-05")

    async def test_same_reference_revision_and_next_session_are_ordered(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), statistics(sequence=50))
        await self.feed(adapter, statistics(quantity=1250, sequence=51, ts_event="2026-08-06T16:01:00Z"))
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 1250)
        await self.feed(adapter, statistics(quantity=1400, sequence=1, ts_ref="2026-08-06", ts_event="2026-08-07T16:00:00Z"))
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 1400)
        self.assertEqual(consumer.contract_state[KEY]["open_interest_reference_date"], "2026-08-06")

    async def test_zero_oi_is_valid_observation(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), statistics(quantity=0))
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 0)
        self.assertFalse(consumer.contract_state[KEY]["open_interest_invalidated"])
        self.assertEqual(adapter.diagnostics()["open_interest"]["status"], "observed")

    async def test_missing_invalid_future_reference_or_action_fails_closed(self):
        for overrides in ({"ts_ref": None}, {"ts_ref": "invalid"}, {"ts_ref": "2026-08-07"}, {"ts_ref": 18446744073709551615}, {"update_action": None}, {"update_action": 3}):
            with self.subTest(overrides=overrides):
                adapter, consumer = adapter_for()
                await self.feed(adapter, definition(), quote(), statistics(**overrides))
                self.assertNotIn(KEY, consumer.contract_state)

    async def test_real_sdk_unset_multiplier_and_fixed_point_contract_size(self):
        try:
            import databento_dbn as dbn
        except ImportError:
            self.skipTest("optional Databento SDK is not installed")
        nanos = lambda text: int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1e9)
        for root, size in (("ES", 50), ("NQ", 20)):
            with self.subTest(root=root):
                record = dbn.InstrumentDefMsg(
                    publisher_id=1, instrument_id=101, ts_event=nanos(EVENT), ts_recv=nanos(EVENT),
                    min_price_increment=250000000, display_factor=1000000000,
                    raw_symbol=f"{root}Q6 C6000", asset=root, security_type="OOF",
                    instrument_class=dbn.InstrumentClass.CALL,
                    security_update_action=dbn.SecurityUpdateAction.ADD,
                    expiration=nanos(EXPIRY), underlying_id=202,
                    unit_of_measure_qty=size * 1000000000, unit_of_measure="IPNT",
                    strike_price=6000000000000,
                )
                self.assertEqual(record.contract_multiplier, 2147483647)
                adapter, consumer = adapter_for(root)
                await self.feed(adapter, record, quote(), trade())
                snapshot = await consumer.process_latest_snapshot(days_to_expiry=14)
                self.assertEqual(snapshot["multiplier_provenance"]["effective_multipliers"], [size])
                self.assertEqual(snapshot["multiplier_provenance"]["fallback_row_count"], 0)

    async def test_real_sdk_statistics_preserve_reference_and_delete(self):
        try:
            import databento_dbn as dbn
        except ImportError:
            self.skipTest("optional Databento SDK is not installed")
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), statistics())
        record = dbn.StatMsg(
            publisher_id=1, instrument_id=101, ts_event=1786032060000000000,
            ts_recv=1786032060000000001, ts_ref=1785888000000000000,
            price=dbn.UNDEF_PRICE, quantity=dbn.UNDEF_STAT_QUANTITY,
            stat_type=dbn.StatType.OPEN_INTEREST,
            update_action=dbn.StatUpdateAction.DELETE, sequence=50,
        )
        await self.feed(adapter, record)
        self.assertEqual(consumer.contract_state[KEY]["open_interest_reference_date"], "2026-08-05")
        self.assertTrue(consumer.contract_state[KEY]["open_interest_invalidated"])
        self.assertEqual(consumer.contract_state[KEY]["accumulated_volume"], 0)


if __name__ == "__main__":
    unittest.main()

"""Bounded parameter matrices for issue #35, with scalar financial oracles.

These are offline software checks; generated coverage proves neither live
entitlement nor predictive trading value. Counts describe actual subtest cases.
"""

import itertools
import math
import os
import unittest
from unittest.mock import patch

from gex_terminal.market_data_adapter import AdapterConfigurationError
from tests.databento_test_cases import (
    EVENT, EXPIRIES, MULTIPLIERS, PRICES, PRODUCTS, adapter_for,
    as_datetime, definition, feed, nanos, quote, statistics, trade,
)


DECODED_MATRIX_CASES = 52 * 2 * 3 * 5
SDK_MATRIX_CASES = 2 * 2 * 3 * 2
EXPIRED_CASES = 52 * 2
UNIT_CASES = (
    ("USD", "USD", "valid"),
    ("IPNT", "IPNT", "valid"),
    ("missing", None, None),
    ("unrecognized", "MWH", "valid"),
    ("undefined", "USD", 9223372036854775807),
)


def scalar_atm_black76_gex(root, option_type, expiry):
    """Independent scalar ATM Black-76 gamma, dollars per one-percent move."""
    time_years = (as_datetime(expiry) - as_datetime(EVENT)).total_seconds() / (365 * 86400)
    sigma = 0.22
    density = math.exp(-0.5 * (0.5 * sigma * math.sqrt(time_years)) ** 2) / math.sqrt(2 * math.pi)
    gamma = math.exp(-0.045 * time_years) * density / (PRICES[root] * sigma * math.sqrt(time_years))
    dollars = 7 * gamma * PRICES[root] ** 2 * 0.01 * MULTIPLIERS[root]
    return dollars if option_type == "C" else -dollars


class DatabentoParameterTests(unittest.IsolatedAsyncioTestCase):
    async def assert_single_contract(self, root, option_type, expiry, provider_definition, fallback):
        adapter, consumer = adapter_for(root)
        await feed(adapter, provider_definition, quote(root), trade())
        state = consumer.contract_state[("databento", "101", "trade_volume")]
        self.assertEqual(state["symbol"], root)
        self.assertEqual(state["option_type"], option_type)
        self.assertEqual(state["expiry_timestamp"], expiry)
        snapshot = await consumer.process_latest_snapshot(days_to_expiry=99)
        expected = scalar_atm_black76_gex(root, option_type, expiry)
        self.assertAlmostEqual(snapshot["total_net_gex"], expected, delta=abs(expected) * 1e-10)
        self.assertEqual(snapshot["multiplier_provenance"]["effective_multipliers"], [MULTIPLIERS[root]])
        self.assertEqual(snapshot["multiplier_provenance"]["fallback_row_count"], int(fallback))
        await feed(adapter, statistics())
        self.assertEqual(consumer.contract_state[("databento", "101", "open_interest")]["symbol"], root)

    async def test_all_products_types_horizons_and_unit_sources(self):
        checked = 0
        for root, products in PRODUCTS.items():
            for product, option_type, expiry, unit_case in itertools.product(
                products, "CP", EXPIRIES, UNIT_CASES,
            ):
                name, unit, quantity = unit_case
                quantity = MULTIPLIERS[root] if quantity == "valid" else quantity
                with self.subTest(root=root, product=product, option_type=option_type, expiry=expiry, units=name):
                    await self.assert_single_contract(
                        root, option_type, expiry,
                        definition(root, product, option_type, expiration=expiry,
                                   unit_of_measure=unit, unit_of_measure_qty=quantity),
                        fallback=name not in {"USD", "IPNT"},
                    )
                checked += 1
        self.assertEqual(checked, DECODED_MATRIX_CASES)

    async def test_real_sdk_fixed_point_representatives(self):
        try:
            import databento_dbn as dbn
        except ImportError:
            self.skipTest("Optional SDK unavailable; 24 real-DBN cases not exercised")
        checked = 0
        for root, option_type, expiry, units in itertools.product(PRODUCTS, "CP", EXPIRIES, ("USD", "IPNT")):
            with self.subTest(root=root, option_type=option_type, expiry=expiry, units=units):
                record = dbn.InstrumentDefMsg(
                    publisher_id=1, instrument_id=101, ts_event=nanos(EVENT), ts_recv=nanos(EVENT),
                    min_price_increment=250000000, display_factor=1000000000,
                    raw_symbol=f"{root}U6 {option_type}{int(PRICES[root])}", asset=root,
                    underlying=f"{root}U6", security_type="OOF",
                    instrument_class=dbn.InstrumentClass.CALL if option_type == "C" else dbn.InstrumentClass.PUT,
                    security_update_action=dbn.SecurityUpdateAction.ADD,
                    expiration=nanos(expiry), underlying_id=202,
                    unit_of_measure_qty=int(MULTIPLIERS[root]) * 1_000_000_000,
                    unit_of_measure=units, strike_price=int(PRICES[root]) * 1_000_000_000,
                )
                await self.assert_single_contract(root, option_type, expiry, record, False)
            checked += 1
        self.assertEqual(checked, SDK_MATRIX_CASES)

    async def test_expired_contracts_cannot_supply_nonzero_gex(self):
        checked = 0
        for root, products in PRODUCTS.items():
            for product, option_type in itertools.product(products, "CP"):
                with self.subTest(root=root, product=product, option_type=option_type):
                    adapter, consumer = adapter_for(root)
                    await feed(adapter, definition(root, product, option_type,
                                                  expiration="2026-08-06T15:59:59Z"), quote(root), trade())
                    snapshot = await consumer.process_latest_snapshot(days_to_expiry=99)
                    self.assertTrue("error" in snapshot or snapshot["total_net_gex"] == 0)
                checked += 1
        self.assertEqual(checked, EXPIRED_CASES)

    def test_environment_parent_selection_boundaries(self):
        cases = ("", " ", ",", "ES.FUT", "NQ.OPT", "SPX.OPT", "EW.OPT,NQ.OPT", "EW.OPT,", "E6A.OPT")
        for value in cases:
            with self.subTest(value=value), patch.dict(os.environ, {"DATABENTO_OPTION_PARENTS": value}):
                with self.assertRaises(AdapterConfigurationError):
                    adapter_for("ES")
        for root, products in PRODUCTS.items():
            selected = f" {products[-1].lower()}.opt , {products[0]}.OPT,{products[-1]}.OPT "
            with self.subTest(root=root), patch.dict(os.environ, {"DATABENTO_OPTION_PARENTS": selected}):
                adapter, _ = adapter_for(root)
                self.assertEqual(adapter.option_parents, (f"{products[-1]}.OPT", f"{products[0]}.OPT"))

    async def test_oi_quantity_boundaries(self):
        cases = (
            (0, 0), (1, 1), ("0", 0), ("42", 42), (42.0, 42),
            (" +42 ", 42), (9223372036854775806, 9223372036854775806),
            ("9223372036854775806", 9223372036854775806),
            (None, None), (True, None), (-1, None), ("-1", None), (0.5, None),
            ("1.5", None), (float("nan"), None), (float("inf"), None),
            (float("-inf"), None), (9223372036854775807, None),
            ("9223372036854775807", None), (float(9223372036854775807), None),
            (1 << 128, None),
        )
        for quantity, expected in cases:
            with self.subTest(quantity=quantity):
                adapter, consumer = adapter_for()
                await feed(adapter, definition(), quote(), statistics(quantity=quantity))
                state = consumer.contract_state.get(("databento", "101", "open_interest"))
                if expected is None:
                    self.assertIsNone(state)
                    self.assertEqual(adapter._open_interest_count, 0)
                else:
                    self.assertEqual(state["accumulated_volume"], expected)
                    self.assertEqual(adapter._open_interest_count, 1)
        # Undefined quantity is unused on a deletion and cannot recreate exposure.
        for quantity in (None, -1, float("nan"), 9223372036854775807):
            with self.subTest(deletion_quantity=quantity):
                adapter, consumer = adapter_for()
                await feed(adapter, definition(), quote(), statistics(),
                           statistics(update_action=2, quantity=quantity, ts_event="2026-08-06T16:01:00Z"))
                state = consumer.contract_state[("databento", "101", "open_interest")]
                self.assertEqual(state["accumulated_volume"], 0)
                self.assertTrue(state["open_interest_invalidated"])

    async def test_dollar_unit_numeric_boundaries_keep_configured_fallback_visible(self):
        for root in PRODUCTS:
            size = MULTIPLIERS[root]
            cases = (
                ("USD", size, False), ("IPNT", size, False), (" usd ", size, False),
                ("USD", None, True), ("USD", 0, True), ("USD", -1, True),
                ("USD", size + 0.1, True), ("USD", float("nan"), True),
                ("USD", float("inf"), True), ("USD", float("-inf"), True),
                ("USD", 9223372036854775807, True),
                ("USD", 20 if root == "ES" else 50, True),
                (None, size, True), ("MWH", size, True),
            )
            for units, quantity, fallback in cases:
                with self.subTest(root=root, units=units, quantity=quantity):
                    adapter, consumer = adapter_for(root)
                    await feed(adapter, definition(root, unit_of_measure=units,
                                                  unit_of_measure_qty=quantity), quote(root), trade())
                    snapshot = await consumer.process_latest_snapshot(days_to_expiry=99)
                    self.assertEqual(snapshot["multiplier_provenance"]["effective_multipliers"], [size])
                    self.assertEqual(snapshot["multiplier_provenance"]["fallback_row_count"], int(fallback))

    async def test_update_action_boundaries(self):
        cases = ((1, "add"), ("ADD", "add"), ("add", "add"),
                 (2, "delete"), ("DELETE", "delete"), ("delete", "delete"),
                 (None, None), (0, None), (3, None), (True, None), (1.0, None))
        for action, expected in cases:
            with self.subTest(action=action):
                adapter, consumer = adapter_for()
                await feed(adapter, definition(), quote(), statistics(update_action=action))
                state = consumer.contract_state.get(("databento", "101", "open_interest"))
                if expected is None:
                    self.assertIsNone(state)
                else:
                    self.assertEqual(state["open_interest_update_action"], expected)
                    self.assertEqual(state["open_interest_invalidated"], expected == "delete")

    async def test_reference_date_and_publication_timezone_boundaries(self):
        cases = (
            ("2026-08-05", "2026-08-06T00:00:00Z", "2026-08-05"),
            ("2026-08-06", "2026-08-05T17:00:00-07:00", "2026-08-06"),
            ("2026-08-06T00:30:00+02:00", "2026-08-05T23:00:00Z", "2026-08-05"),
            ("2026-08-05T23:30:00-02:00", "2026-08-06T02:00:00Z", "2026-08-06"),
            (nanos("2026-08-05T00:00:00Z"), EVENT, "2026-08-05"),
            ("2026-08-06", "2026-08-05T23:59:59Z", None),
            ("2026-02-30", EVENT, None), ("2026-08-05T00:00:00", EVENT, None),
            (None, EVENT, None), (18446744073709551615, EVENT, None),
            ("2026-08-05", 18446744073709551615, None),
        )
        for reference, publication, expected in cases:
            with self.subTest(reference=reference, publication=publication):
                adapter, consumer = adapter_for()
                await feed(adapter, definition(), quote(), statistics(ts_ref=reference, ts_event=publication))
                state = consumer.contract_state.get(("databento", "101", "open_interest"))
                if expected is None:
                    self.assertIsNone(state)
                else:
                    self.assertEqual(state["open_interest_reference_date"], expected)


if __name__ == "__main__":
    unittest.main()

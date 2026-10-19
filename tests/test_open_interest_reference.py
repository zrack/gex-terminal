import copy
import json
import unittest

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.contracts import canonical_option_contract
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import validate_normalized_message


def _oi_message(**updates):
    message = {
        "schema_version": 2,
        "type": "options_volume_tick",
        "provider": "databento",
        "contract_id": "101",
        "symbol": "ES",
        "expiry": "2026-12-18",
        "expiry_timestamp": "2026-12-18T20:00:00Z",
        "strike": 6050,
        "option_type": "C",
        "volume": 1200,
        "iv": 0.16,
        "iv_source": "configured_default",
        "instrument_class": "futures_option",
        "pricing_model": "black_76",
        "contract_multiplier": 50,
        "volume_semantics": "cumulative",
        "position_source": "open_interest",
        "event_time": "2026-08-06T16:00:00Z",
        "open_interest_reference_date": "2026-08-05",
        "open_interest_update_action": "add",
        "sequence": 100,
    }
    message.update(updates)
    return message


class OpenInterestReferenceContractTests(unittest.TestCase):
    def test_fields_are_preserved_without_changing_publication_time(self):
        message = _oi_message()
        validate_normalized_message(message)
        contract = canonical_option_contract(message, target_underlying="ES")
        self.assertEqual(contract["open_interest_reference_date"], "2026-08-05")
        self.assertEqual(contract["open_interest_update_action"], "add")
        self.assertEqual(contract["event_time"], "2026-08-06T16:00:00Z")

    def test_reference_fields_must_be_supplied_together(self):
        for missing in ("open_interest_reference_date", "open_interest_update_action"):
            message = _oi_message()
            message.pop(missing)
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, missing):
                validate_normalized_message(message)

    def test_reference_date_requires_canonical_iso_date(self):
        for invalid in ("20260805", "2026-8-5", "2026-02-30", "2026-08-05T00:00:00Z", 20260805):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "ISO date"):
                validate_normalized_message(_oi_message(open_interest_reference_date=invalid))

    def test_reference_date_cannot_follow_publication_utc_date(self):
        # Although the local label says Aug 6, this instant is Aug 5 in UTC.
        with self.assertRaisesRegex(ValueError, "UTC date"):
            validate_normalized_message(_oi_message(
                open_interest_reference_date="2026-08-06",
                event_time="2026-08-06T00:30:00+02:00",
            ))
        validate_normalized_message(_oi_message(
            open_interest_reference_date="2026-08-06",
            event_time="2026-08-05T23:30:00-02:00",
        ))

    def test_reference_fields_require_cumulative_open_interest(self):
        for updates in ({"position_source": "trade_volume"}, {"volume_semantics": "incremental"}):
            with self.subTest(updates=updates), self.assertRaisesRegex(ValueError, "cumulative open_interest"):
                validate_normalized_message(_oi_message(**updates))

    def test_reference_fields_require_schema_v2_option_message(self):
        for updates in ({"schema_version": 1}, {"type": "underlying_tick"}):
            with self.subTest(updates=updates), self.assertRaisesRegex(ValueError, "schema-v2 option"):
                validate_normalized_message(_oi_message(**updates))

    def test_delete_requires_zero_but_zero_add_is_valid(self):
        validate_normalized_message(_oi_message(volume=0))
        validate_normalized_message(_oi_message(volume=0, open_interest_update_action="delete"))
        with self.assertRaisesRegex(ValueError, "volume=0"):
            validate_normalized_message(_oi_message(open_interest_update_action="delete"))
        with self.assertRaisesRegex(ValueError, "open_interest_update_action"):
            validate_normalized_message(_oi_message(open_interest_update_action="modify"))

    def test_legacy_normalized_open_interest_remains_valid(self):
        message = _oi_message()
        message.pop("open_interest_reference_date")
        message.pop("open_interest_update_action")
        validate_normalized_message(message)

    def test_multiplier_source_requires_provider_value_and_multiplier(self):
        message = _oi_message(contract_multiplier_source="provider_unit_of_measure")
        validate_normalized_message(message)
        contract = canonical_option_contract(message, target_underlying="ES")
        self.assertEqual(contract["contract_multiplier_source"], "provider_unit_of_measure")
        message.pop("contract_multiplier")
        with self.assertRaisesRegex(ValueError, "contract_multiplier"):
            validate_normalized_message(message)
        with self.assertRaisesRegex(ValueError, "contract_multiplier_source"):
            validate_normalized_message(_oi_message(contract_multiplier_source="configured_default"))


class OpenInterestReferenceConsumerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50), target_underlying="ES", data_mode="replay"
        )
        self.oi_key = ("databento", "101", "open_interest")

    async def _update(self, message):
        return await self.consumer.update_market_state(json.dumps(message))

    def _selected(self):
        return self.consumer._select_position_states(list(self.consumer.contract_state.values()))[0]

    async def test_state_preserves_reference_and_publication_metadata(self):
        self.assertTrue(await self._update(_oi_message()))
        state = self.consumer.contract_state[self.oi_key]
        self.assertEqual(state["open_interest_reference_date"], "2026-08-05")
        self.assertEqual(state["open_interest_update_action"], "add")
        self.assertEqual(state["event_time"], "2026-08-06T16:00:00Z")
        self.assertFalse(state["open_interest_invalidated"])
        self.assertEqual(state["accumulated_volume"], 1200)

    async def test_older_reference_correction_cannot_replace_newer_reference(self):
        await self._update(_oi_message())
        original = copy.deepcopy(self.consumer.contract_state[self.oi_key])
        self.assertFalse(await self._update(_oi_message(
            volume=800, open_interest_reference_date="2026-08-04",
            event_time="2026-08-06T16:01:00Z", sequence=101,
        )))
        self.assertEqual(self.consumer.contract_state[self.oi_key], original)
        self.assertEqual(self.consumer.message_count, 1)

    async def test_same_reference_newer_publication_accepts_revision(self):
        await self._update(_oi_message())
        # Publication ordering is authoritative for referenced statistics.
        self.assertTrue(await self._update(_oi_message(
            volume=1300, event_time="2026-08-06T16:01:00Z", sequence=99,
        )))
        self.assertEqual(self.consumer.contract_state[self.oi_key]["accumulated_volume"], 1300)

    async def test_same_reference_older_or_equal_publication_is_ignored(self):
        await self._update(_oi_message())
        for publication in ("2026-08-06T15:59:59Z", "2026-08-06T16:00:00Z"):
            with self.subTest(publication=publication):
                self.assertFalse(await self._update(_oi_message(
                    volume=999, event_time=publication, sequence=101,
                )))
        self.assertEqual(self.consumer.contract_state[self.oi_key]["accumulated_volume"], 1200)
        self.assertEqual(self.consumer.duplicate_message_count, 2)

    async def test_new_reference_can_reset_sequence(self):
        await self._update(_oi_message())
        self.assertTrue(await self._update(_oi_message(
            volume=1400, open_interest_reference_date="2026-08-06",
            event_time="2026-08-07T16:00:00Z", sequence=1,
        )))
        state = self.consumer.contract_state[self.oi_key]
        self.assertEqual(state["open_interest_reference_date"], "2026-08-06")
        self.assertEqual(state["last_sequence"], 1)
        self.assertEqual(state["accumulated_volume"], 1400)

    async def test_new_reference_takes_priority_over_publication_time(self):
        await self._update(_oi_message(open_interest_reference_date="2026-08-04"))
        self.assertTrue(await self._update(_oi_message(
            volume=1500, event_time="2026-08-06T15:00:00Z", sequence=1,
        )))
        self.assertEqual(self.consumer.contract_state[self.oi_key]["accumulated_volume"], 1500)
        self.assertEqual(self.consumer.market_time.isoformat(), "2026-08-06T16:00:00+00:00")

    async def test_delete_retains_tombstone_and_prevents_stale_resurrection(self):
        await self._update(_oi_message())
        self.assertTrue(await self._update(_oi_message(
            volume=0, open_interest_update_action="delete",
            event_time="2026-08-06T16:01:00Z", sequence=101,
        )))
        tombstone = copy.deepcopy(self.consumer.contract_state[self.oi_key])
        self.assertEqual(tombstone["accumulated_volume"], 0)
        self.assertTrue(tombstone["open_interest_invalidated"])
        self.assertEqual(self._selected(), [])
        self.assertEqual(self.consumer.chain_state, {})
        for updates in (
            {"event_time": "2026-08-06T16:00:30Z"},
            {"event_time": "2026-08-06T16:01:00Z"},
            {"open_interest_reference_date": "2026-08-04", "event_time": "2026-08-06T16:02:00Z"},
        ):
            with self.subTest(updates=updates):
                self.assertFalse(await self._update(_oi_message(sequence=102, **updates)))
        self.assertEqual(self.consumer.contract_state[self.oi_key], tombstone)
        self.assertTrue(await self._update(_oi_message(
            volume=1250, event_time="2026-08-06T16:02:00Z", sequence=102,
        )))
        self.assertFalse(self.consumer.contract_state[self.oi_key]["open_interest_invalidated"])
        self.assertEqual(self._selected()[0]["accumulated_volume"], 1250)

    async def test_zero_add_is_observed_position_not_deleted_tombstone(self):
        self.assertTrue(await self._update(_oi_message(volume=0)))
        state = self.consumer.contract_state[self.oi_key]
        self.assertFalse(state["open_interest_invalidated"])
        self.assertEqual(self._selected(), [state])
        self.assertEqual(self.consumer.chain_state[6050.0]["C"], 0)

    async def test_delete_does_not_change_independent_trade_state(self):
        trade = _oi_message(position_source="trade_volume", volume_semantics="incremental", volume=42)
        trade.pop("open_interest_reference_date")
        trade.pop("open_interest_update_action")
        self.assertTrue(await self._update(trade))
        trade_key = ("databento", "101", "trade_volume")
        original_trade = copy.deepcopy(self.consumer.contract_state[trade_key])
        await self._update(_oi_message())
        await self._update(_oi_message(
            volume=0, open_interest_update_action="delete",
            event_time="2026-08-06T16:01:00Z",
        ))
        self.assertEqual(self.consumer.contract_state[trade_key], original_trade)
        self.assertEqual(self._selected(), [original_trade])
        self.assertEqual(self.consumer.chain_state[6050.0]["C"], 42)

    async def test_legacy_observation_cannot_overwrite_reference_aware_state(self):
        legacy = _oi_message()
        legacy.pop("open_interest_reference_date")
        legacy.pop("open_interest_update_action")
        self.assertTrue(await self._update(legacy))
        self.assertTrue(await self._update(_oi_message(volume=1300)))
        self.assertFalse(await self._update({
            **legacy, "volume": 900, "sequence": 102,
            "event_time": "2026-08-06T16:02:00Z",
        }))
        self.assertEqual(self.consumer.contract_state[self.oi_key]["accumulated_volume"], 1300)

    async def test_multiplier_source_survives_later_metadata_omission(self):
        await self._update(_oi_message(contract_multiplier_source="provider_unit_of_measure"))
        revision = _oi_message(volume=1300, event_time="2026-08-06T16:01:00Z")
        revision.pop("contract_multiplier")
        self.assertTrue(await self._update(revision))
        state = self.consumer.contract_state[self.oi_key]
        self.assertEqual(state["contract_multiplier"], 50)
        self.assertEqual(state["contract_multiplier_source"], "provider_unit_of_measure")


if __name__ == "__main__":
    unittest.main()

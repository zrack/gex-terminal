"""Synthetic regressions for multiple native fills sharing one venue sequence."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gex_terminal.adapters.databento import DatabentoAdapter, _record_mapping
from gex_terminal.contracts import canonical_option_contract
from gex_terminal.market_data_adapter import validate_normalized_message
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, validate_checkpoint
from gex_terminal.session_capture import load_captured_session
from gex_terminal.session_intake import SessionIntake
from gex_terminal.cli import compute_snapshot
from scripts.databento_trial_replay import convert_sample
from tests.test_databento_regressions import adapter_for, definition, quote, trade
from tests.test_databento_trial_replay import _config, _files, _records


def sequenced_trade(**updates):
    return trade(**{
        "publisher_id": 1, "channel_id": 7, "sequence": 100,
        "ts_event": "2026-08-06T16:00:00.000000001Z",
        "ts_recv": "2026-08-06T16:00:00.000000101Z",
        "action": "T", "depth": 0, "flags": 0, "ts_in_delta": 25,
        **updates,
    })


def normalized(**updates):
    metadata = DatabentoAdapter._normalize_definition_record(definition())
    message = DatabentoAdapter._normalize_option_trade_record(
        sequenced_trade(), {101: metadata},
    )
    return {**message, **updates}


class NativeTradeIdentityTests(unittest.TestCase):
    def test_identity_is_deterministic_and_omitted_without_a_sequence(self):
        first = normalized()
        validate_normalized_message(first)
        self.assertEqual(first["provider_trade_event_id"], normalized()["provider_trade_event_id"])
        self.assertEqual(len(first["provider_trade_event_id"]), 64)
        metadata = DatabentoAdapter._normalize_definition_record(definition())
        message = DatabentoAdapter._normalize_option_trade_record(trade(), {101: metadata})
        self.assertNotIn("provider_trade_event_id", message)
        contract = canonical_option_contract(message, target_underlying="ES")
        self.assertNotIn("provider_trade_event_id", contract)

    def test_identity_covers_native_fill_fields_and_nanoseconds(self):
        metadata = DatabentoAdapter._normalize_definition_record(definition())
        original = sequenced_trade()
        identity = normalized()["provider_trade_event_id"]
        for field, value in (
            ("publisher_id", 2), ("channel_id", 8), ("instrument_id", 102),
            ("ts_event", "2026-08-06T16:00:00.000000002Z"),
            ("ts_recv", "2026-08-06T16:00:00.000000102Z"),
            ("price", 100.25), ("size", 8), ("side", "A"),
            ("action", "F"), ("depth", 1), ("flags", 128),
            ("ts_in_delta", 26), ("sequence", 101),
        ):
            with self.subTest(field=field):
                changed = DatabentoAdapter._normalize_option_trade_record(
                    {**original, field: value}, {101: metadata, 102: metadata},
                )
                self.assertNotEqual(identity, changed["provider_trade_event_id"])

    def test_native_fixed_price_and_decoded_aliases_share_an_identity(self):
        original = sequenced_trade()
        native = SimpleNamespace(**{
            **original, "price": 100_000_000_000,
            "ts_event": 1_786_032_000_000_000_001,
            "ts_recv": 1_786_032_000_000_000_101,
            "pretty_price": 100.0,
        })
        mapped = _record_mapping(native, "option_trade")
        self.assertEqual(mapped["_provider_trade_event_id"], normalized()["provider_trade_event_id"])
        changed = copy.copy(native)
        changed.price += 1  # Same pretty float, distinct native fixed-point price.
        self.assertNotEqual(
            mapped["_provider_trade_event_id"],
            _record_mapping(changed, "option_trade")["_provider_trade_event_id"],
        )
        aliases = sequenced_trade()
        for original, alias in (("ts_event", "event_time"), ("ts_recv", "received_time"),
                                ("price", "trade_price"), ("size", "quantity"),
                                ("side", "aggressor_side"), ("sequence", "seq")):
            aliases[alias] = aliases.pop(original)
        metadata = DatabentoAdapter._normalize_definition_record(definition())
        self.assertEqual(
            normalized()["provider_trade_event_id"],
            DatabentoAdapter._normalize_option_trade_record(aliases, {101: metadata})["provider_trade_event_id"],
        )

    def test_id_is_strictly_scoped_to_sequenced_databento_incremental_trades(self):
        for updates in (
            {"schema_version": 1}, {"type": "underlying_tick", "price": 6000},
            {"provider": "other"}, {"position_source": "open_interest"},
            {"volume_semantics": "cumulative"}, {"sequence": None},
            {"provider_trade_event_id": None}, {"provider_trade_event_id": "short"},
            {"provider_trade_event_id": "A" * 64}, {"provider_trade_event_id": 1},
        ):
            with self.subTest(updates=updates), self.assertRaisesRegex(ValueError, "provider_trade_event_id"):
                validate_normalized_message(normalized(**updates))


class NativeMultiFillConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_conversion_capture_and_app_replay_preserve_the_fill_identity(self):
        for root in ("ES", "NQ"):
            with self.subTest(root=root), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                records = _records(root)
                first = records[3]
                second = {**first, "price": first["price"] + .25, "size": 11}
                records.extend((second, dict(first)))
                result = await convert_sample(
                    files=_files(base, records), symbol=root, output_dir=base / "converted",
                )
                _, messages = load_captured_session(result["capture"])
                same_contract = [row for row in messages if row.get("contract_id") == str(first["instrument_id"])]
                self.assertEqual(len(same_contract), 3)
                ids = [row["provider_trade_event_id"] for row in same_contract]
                self.assertEqual(ids[0], ids[2])
                self.assertNotEqual(ids[0], ids[1])
                snapshot, consumer, _ = await compute_snapshot(_config(root, result["capture"]))
                checkpoint = await build_terminal_checkpoint(consumer, fallback_dte=.25)
                checkpoint_quantity = sum(row["accumulated_volume"] for row in checkpoint["rows"])
                expected_quantity = sum(row["size"] for row in _records(root) if row["record_type"] == "trades") + 11
                self.assertEqual(checkpoint_quantity, expected_quantity)
                self.assertEqual(consumer.duplicate_message_count, 1)
                serialized = json.dumps(snapshot)
                self.assertNotIn("_trade_event_ids", serialized)
                # Wind Tunnel's guided import projects calculation fields into
                # an opaque namespace before replay. Fill identity must survive
                # that projection or the same venue sequence loses volume again.
                intake = SessionIntake()
                inspected = intake.inspect(result["capture"].read_bytes())
                imported = validate_checkpoint(await intake.checkpoint(
                    inspected["intake_id"], inspected["default_sequence"],
                ))
                self.assertEqual(sum(row["accumulated_volume"] for row in imported["rows"]), expected_quantity)
                self.assertEqual(sum(row["accumulated_volume"] for row in imported["rows"]
                                     if row["option_type"] == "C"), 18)
                self.assertEqual(imported["source"]["quality"]["duplicate_message_count"], 1)
                self.assertNotIn("_trade_event_ids", json.dumps(imported))
                self.assertNotIn("provider_trade_event_id", json.dumps(imported))

    async def test_distinct_same_sequence_fills_count_and_a_b_a_retransmit_does_not(self):
        for root in ("ES", "NQ"):
            with self.subTest(root=root):
                adapter, consumer = adapter_for(root)
                first = sequenced_trade()
                second = {**first, "price": 99.75, "size": 11, "side": "A"}
                for record in (definition(root), quote(), first, second, first):
                    await adapter._handle_live_record(record)
                state = consumer.contract_state[("databento", "101", "trade_volume")]
                self.assertEqual(state["accumulated_volume"], 18)
                self.assertEqual(state["directional_volume"], {"buy": 7, "sell": 11, "unknown": 0})
                self.assertEqual(consumer.duplicate_message_count, 1)
                self.assertEqual(consumer.malformed_message_count, 0)
                self.assertEqual(adapter._option_trade_count, 3)  # Normalized records, including retransmit.
                snapshot = await consumer.process_latest_snapshot(14)
                self.assertEqual(snapshot["call_volume"], [18.0])
                self.assertEqual(len(state["_trade_event_ids"]), 2)
                checkpoint = await build_terminal_checkpoint(consumer, fallback_dte=.25)
                self.assertEqual(checkpoint["rows"][0]["accumulated_volume"], 18)
                self.assertNotIn("provider_trade_event_id", checkpoint["rows"][0])
                self.assertNotIn("_trade_event_ids", checkpoint["rows"][0])

    async def test_lower_sequences_still_reject_and_new_group_replaces_old_ids(self):
        adapter, consumer = adapter_for()
        for record in (definition(), quote(), sequenced_trade()):
            await adapter._handle_live_record(record)
        await adapter._handle_live_record(sequenced_trade(sequence=99, size=100))
        await adapter._handle_live_record(sequenced_trade(sequence=101, size=3))
        await adapter._handle_live_record(sequenced_trade(size=100))
        state = consumer.contract_state[("databento", "101", "trade_volume")]
        self.assertEqual(state["accumulated_volume"], 10)
        self.assertEqual(state["last_sequence"], 101)
        self.assertEqual(len(state["_trade_event_ids"]), 1)
        self.assertEqual(consumer.duplicate_message_count, 2)
        await consumer.reset_state()
        self.assertFalse(consumer.contract_state)

    async def test_old_captures_other_providers_and_cumulative_updates_keep_strict_ordering(self):
        _, consumer = adapter_for()
        for index, updates in enumerate(({}, {"provider": "other"}, {"volume_semantics": "cumulative"},
                                         {"position_source": "open_interest", "volume_semantics": "cumulative"})):
            with self.subTest(updates=updates):
                first = normalized(contract_id=str(index), **updates)
                first.pop("provider_trade_event_id")
                if first["volume_semantics"] == "cumulative":
                    first.update(aggressor_side="unknown", direction_source="unknown")
                self.assertTrue(await consumer.update_market_state(json.dumps(first)))
                self.assertFalse(await consumer.update_market_state(json.dumps({**first, "volume": 100})))
                state = consumer.contract_state[(first["provider"], str(index), first["position_source"])]
                self.assertEqual(state["accumulated_volume"], first["volume"])

    async def test_failed_identity_update_does_not_poison_native_deduplication(self):
        _, consumer = adapter_for()
        first = normalized()
        self.assertTrue(await consumer.update_market_state(json.dumps(first)))
        second = normalized(provider_trade_event_id="b" * 64, volume=11)
        with self.assertLogs("gex_terminal.consumer", level="ERROR"):
            self.assertFalse(await consumer.update_market_state(json.dumps({**second, "strike": 6100})))
        self.assertTrue(await consumer.update_market_state(json.dumps(second)))
        self.assertEqual(next(iter(consumer.contract_state.values()))["accumulated_volume"], 18)

    async def test_group_cache_is_bounded_and_never_evicts_duplicate_protection(self):
        _, consumer = adapter_for()
        with patch("gex_terminal.consumer.MAX_TRADE_IDENTITIES_PER_SEQUENCE", 2):
            first = normalized()
            second = normalized(provider_trade_event_id="b" * 64, volume=11)
            third = normalized(provider_trade_event_id="c" * 64, volume=20)
            for message in (first, second):
                self.assertTrue(await consumer.update_market_state(json.dumps(message)))
            with self.assertLogs("gex_terminal.consumer", level="ERROR"):
                self.assertFalse(await consumer.update_market_state(json.dumps(third)))
            self.assertFalse(await consumer.update_market_state(json.dumps(first)))
            self.assertEqual(next(iter(consumer.contract_state.values()))["accumulated_volume"], 18)
            self.assertEqual(len(next(iter(consumer.contract_state.values()))["_trade_event_ids"]), 2)
            self.assertTrue(await consumer.update_market_state(json.dumps({**third, "sequence": 101})))
            self.assertEqual(next(iter(consumer.contract_state.values()))["accumulated_volume"], 38)

    @unittest.skipUnless(importlib.util.find_spec("databento"), "optional Databento SDK not installed")
    async def test_native_dbn_trade_messages_preserve_multiple_fills(self):
        import databento_dbn as dbn
        adapter, consumer = adapter_for()
        for record in (definition(), quote()):
            await adapter._handle_live_record(record)
        first = dbn.TradeMsg(
            publisher_id=1, instrument_id=101, ts_event=1_786_032_000_000_000_001,
            ts_recv=1_786_032_000_000_000_101, price=100_000_000_000,
            size=7, action=dbn.Action.TRADE, side=dbn.Side.BID,
            flags=0, depth=0, ts_in_delta=25, sequence=100,
        )
        second = dbn.TradeMsg(
            publisher_id=1, instrument_id=101, ts_event=first.ts_event,
            ts_recv=first.ts_recv, price=99_750_000_000,
            size=11, action=dbn.Action.TRADE, side=dbn.Side.ASK,
            flags=0, depth=0, ts_in_delta=25, sequence=100,
        )
        for record in (first, second, first):
            await adapter._handle_live_record(record)
        state = consumer.contract_state[("databento", "101", "trade_volume")]
        self.assertEqual(state["accumulated_volume"], 18)
        self.assertEqual(consumer.duplicate_message_count, 1)


if __name__ == "__main__":
    unittest.main()

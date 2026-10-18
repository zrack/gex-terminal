import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.session_capture import CapturedSessionWriter, verify_captured_session_bytes
from gex_terminal.session_intake import IntakeError, MAX_CAPTURE_BYTES, SessionIntake
from gex_terminal.wind_tunnel import calculate
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, validate_checkpoint


def messages(symbol="ES", multiplier=50):
    base = {"schema_version": 2, "provider": "synthetic", "symbol": symbol}
    option = {**base, "type": "options_volume_tick", "contract_id": "call-5000", "strike": 5000,
              "option_type": "C", "iv": .2, "iv_source": "provider", "expiry": "2026-10-19",
              "expiry_timestamp": "2026-10-19T20:00:00Z", "instrument_class": "futures_option",
              "volume_semantics": "cumulative", "position_source": "open_interest",
              "contract_multiplier": multiplier}
    return [
        {**base, "type": "underlying_tick", "price": 5000.0, "event_time": "2026-10-18T15:30:00Z"},
        {**option, "volume": 100, "event_time": "2026-10-18T15:30:01Z", "sequence": 1},
        {**option, "volume": 7, "position_source": "trade_volume", "volume_semantics": "incremental",
         "event_time": "2026-10-18T15:30:02Z", "sequence": 2},
        {**base, "type": "underlying_tick", "price": 5200.0, "event_time": "2026-10-18T15:45:00Z"},
    ]


async def capture_bytes(events=None, *, source=None, model_inputs=None, quality=None):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.gex-session.jsonl"
        writer = CapturedSessionWriter(
            path, source=source if source is not None else {
                "provider": "replay", "mode": "replay", "symbol": "ES", "synthetic": True,
            },
            model_inputs=model_inputs if model_inputs is not None else {
                "days_to_expiry": .01, "risk_free_rate": .045, "contract_multiplier": 50,
                "expiry_filter": "all",
            },
            label="private-account-path-should-not-be-returned",
        )
        await writer.start()
        for event in messages() if events is None else events:
            await writer.append(event)
        await writer.finalize(feed_quality=quality)
        return path.read_bytes()


def changed_capture_header(data, **updates):
    """Build an integrity-valid envelope with intentionally unsupported metadata."""
    records = [json.loads(line) for line in data.splitlines()]
    records[0].update(updates)
    records[-1].pop("content_sha256")
    canonical = lambda record: json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    records[-1]["content_sha256"] = hashlib.sha256(b"".join(canonical(record) + b"\n" for record in records)).hexdigest()
    return b"".join(canonical(record) + b"\n" for record in records)


class SessionIntakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_prefix_matches_production_state_and_excludes_future_spot(self):
        events = messages()
        data = await capture_bytes(events)
        intake = SessionIntake()
        inspected = intake.inspect(data)
        opaque = await intake.checkpoint(inspected["intake_id"], 2)
        artifact = validate_checkpoint(opaque)
        consumer = StatefulGexConsumer(IntradayGexEngine(50.0), data_mode="demo")
        for event in events[:3]:
            projected = dict(event)
            if "contract_id" in projected:
                projected["contract_id"] = artifact["rows"][0]["contract_id"]
            await consumer.update_market_state(json.dumps(projected))
        expected = await build_terminal_checkpoint(consumer, fallback_dte=.01, source_label=artifact["source"]["label"])
        self.assertEqual(artifact, expected)
        self.assertEqual(artifact["parameters"]["spot"], 5000)
        self.assertEqual(artifact["source"]["as_of"], "2026-10-18T15:30:02Z")
        self.assertEqual(len(artifact["rows"]), 2)
        self.assertEqual(sum(row["accumulated_volume"] for row in artifact["rows"] if row["terminal_selected"]), 7)
        self.assertIn(inspected["content_sha256"], artifact["source"]["label"])
        self.assertTrue(artifact["source"]["label"].endswith("event 3"))
        self.assertIn('"spot":5000.0', opaque)
        final = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 3))
        self.assertEqual(final["parameters"]["spot"], 5200)
        self.assertEqual(artifact["parameters"]["spot"], 5000)

    async def test_private_labels_extensions_and_unknown_source_values_do_not_escape(self):
        secret = "ACCOUNT-SECRET-/Users/private/source"
        events = messages()
        events[1]["unknown_extension"] = {"account": secret}
        data = await capture_bytes(events, source={"name": secret, "provider": secret, "mode": secret,
                                                   "symbol": "ES", "capture_policy": {"owner": secret}},
                                   model_inputs={"contract_multiplier": 50, "private": secret},
                                   quality={"status": secret, "health": secret, "notes": secret,
                                            "message_count": 4, "malformed_count": -2})
        intake = SessionIntake()
        inspected = intake.inspect(data)
        self.assertNotIn(secret, json.dumps(inspected))
        self.assertEqual(inspected["source"], {"provider": "unknown", "mode": "unknown"})
        self.assertEqual(inspected["quality"], {"available": True, "scope": "recorded_end_of_session", "message_count": 4})
        self.assertFalse(inspected["synthetic"])
        opaque = await intake.checkpoint(inspected["intake_id"], 2)
        self.assertNotIn(secret, opaque)
        self.assertNotIn("private-account-path", opaque)
        self.assertEqual(validate_checkpoint(opaque)["source"]["data_mode"], "REPLAY")

    async def test_capture_quality_is_explicitly_end_of_session_and_not_prefix_quality(self):
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes(quality={"status": "REPLAY", "health": "degraded",
                                                                 "message_count": 400, "dropped_count": 12}))
        self.assertEqual(inspected["quality"]["scope"], "recorded_end_of_session")
        artifact = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 2))
        self.assertEqual(artifact["source"]["quality"]["message_count"], 3)
        self.assertEqual(artifact["source"]["quality"]["dropped_count"], 0)
        no_quality = SessionIntake().inspect(await capture_bytes())
        self.assertFalse(no_quality["quality"]["available"])

    async def test_incomplete_tampered_unknown_schema_and_invalid_json_are_safe(self):
        data = await capture_bytes()
        mutations = [b"\n".join(data.splitlines()[:-1]), data.replace(b'"volume":100', b'"volume":101'),
                     data.replace(b"captured-session.v1", b"captured-session.v9"), b"[]\n", b"\xff",
                     data.replace(b'"record_type":"header"', b'"record_type":"header","record_type":"header"')]
        for invalid in mutations:
            with self.subTest(invalid=invalid[:20]):
                with self.assertRaisesRegex(IntakeError, "verification failed") as caught:
                    SessionIntake().inspect(invalid)
                self.assertNotIn("private-account", str(caught.exception))

    async def test_nonfinite_private_extension_and_deep_json_are_rejected(self):
        events = messages()
        events[1]["private_number"] = float("nan")
        with self.assertRaisesRegex(IntakeError, "verification failed"):
            SessionIntake().inspect(await capture_bytes(events))
        events[1]["private_number"] = float("inf")
        overflowing = (await capture_bytes(events)).replace(b"Infinity", b"1e309")
        with self.assertRaisesRegex(IntakeError, "verification failed"):
            SessionIntake().inspect(overflowing)
        with self.assertRaisesRegex(IntakeError, "verification failed"):
            SessionIntake().inspect(b"[" * 2000 + b"]" * 2000)

    async def test_missing_true_market_time_never_uses_receipt_time(self):
        events = [{"type": "underlying_tick", "symbol": "ES", "price": 5000},
                  {"type": "options_volume_tick", "strike": 5000, "option_type": "C", "volume": 5}]
        with self.assertRaisesRegex(IntakeError, "genuine timezone-bearing"):
            SessionIntake().inspect(await capture_bytes(events))

    async def test_out_of_order_prefix_cutoff_is_latest_included_market_time(self):
        events = messages()
        events[2]["event_time"] = "2026-10-18T15:29:00Z"
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes(events))
        self.assertEqual(inspected["checkpoints"][2]["event_time"], "2026-10-18T15:30:01Z")
        self.assertTrue(any("out of market-time order" in warning for warning in inspected["warnings"]))
        artifact = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 2))
        self.assertEqual(artifact["source"]["as_of"], inspected["checkpoints"][2]["event_time"])
        self.assertTrue(all(row["event_time"] <= artifact["source"]["as_of"] for row in artifact["rows"]))

    async def test_invalid_checkpoint_or_unavailable_intake_does_not_mutate_valid_one(self):
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes())
        with self.assertRaisesRegex(IntakeError, "later event"):
            await intake.checkpoint(inspected["intake_id"], 0)
        for sequence in (-1, 4, True, 1.5, "2"):
            with self.assertRaisesRegex(IntakeError, "event sequence"):
                await intake.checkpoint(inspected["intake_id"], sequence)
        with self.assertRaisesRegex(IntakeError, "unavailable"):
            await intake.checkpoint("not-held", 2)
        self.assertTrue(await intake.checkpoint(inspected["intake_id"], 2))

    async def test_bounds_fail_before_retaining_new_capture(self):
        intake = SessionIntake()
        for data in (b"", b" " * (MAX_CAPTURE_BYTES + 1), "not bytes"):
            with self.assertRaisesRegex(IntakeError, "4 MiB"):
                intake.inspect(data)
        data = await capture_bytes()
        with patch("gex_terminal.session_intake.MAX_EVENTS", 2):
            with self.assertRaisesRegex(IntakeError, "verification failed"):
                intake.inspect(data)
        self.assertEqual(len(intake._sessions), 0)

    async def test_four_capture_quota_discard_and_shutdown_release_inputs(self):
        intake = SessionIntake()
        data = await capture_bytes()
        held = [intake.inspect(data) for _ in range(4)]
        self.assertEqual(len({item["intake_id"] for item in held}), 4)
        with self.assertRaisesRegex(IntakeError, "Four captures"):
            intake.inspect(data)
        self.assertTrue(await intake.checkpoint(held[0]["intake_id"], 2))
        intake.discard(held[0]["intake_id"])
        intake.discard(held[0]["intake_id"])
        intake.inspect(data)
        with self.assertRaisesRegex(IntakeError, "unavailable"):
            await intake.checkpoint(held[0]["intake_id"], 2)
        intake.clear()
        with self.assertRaisesRegex(IntakeError, "unavailable"):
            await intake.checkpoint(held[1]["intake_id"], 2)

    async def test_checkpoint_choices_are_bounded_but_any_valid_sequence_is_supported(self):
        events = messages() + [{**messages()[0], "event_time": f"2026-10-18T15:50:0{i}Z"} for i in range(3)]
        intake = SessionIntake()
        with patch("gex_terminal.session_intake.MAX_CHECKPOINT_CHOICES", 4):
            inspected = intake.inspect(await capture_bytes(events))
        self.assertEqual(len(inspected["checkpoints"]), 4)
        self.assertEqual(inspected["checkpoints"][0]["sequence"], 0)
        self.assertEqual(inspected["checkpoints"][-1]["sequence"], 6)
        self.assertEqual(inspected["default_sequence"], 6)
        self.assertNotIn(3, [item["sequence"] for item in inspected["checkpoints"]])
        self.assertTrue(await intake.checkpoint(inspected["intake_id"], 3))

    async def test_symbol_mixture_header_mismatch_and_unsupported_model_inputs_fail(self):
        for source, inputs, events in [
            ({"symbol": "NQ"}, {"contract_multiplier": 50}, messages()),
            ({}, {"contract_multiplier": 50, "risk_free_rate": 2}, messages()),
            ({}, {"contract_multiplier": 50, "days_to_expiry": 0}, messages()),
            ({}, {"contract_multiplier": 50, "expiry_filter": "private/path"}, messages()),
            ({}, {"contract_multiplier": 50}, messages() + [{**messages()[0], "symbol": "NQ"}]),
        ]:
            with self.subTest(source=source, inputs=inputs):
                with self.assertRaises(IntakeError):
                    SessionIntake().inspect(await capture_bytes(events, source=source, model_inputs=inputs))

    async def test_mixed_option_contract_generations_fail_closed(self):
        events = messages() + [{"type": "options_volume_tick", "strike": 5000, "option_type": "P",
                                "volume": 10, "timestamp": "2026-10-18T15:50:00Z"}]
        with self.assertRaisesRegex(IntakeError, "Mixed legacy and v2"):
            SessionIntake().inspect(await capture_bytes(events))

    async def test_integrity_valid_unsupported_normalized_contract_is_rejected(self):
        unsupported = changed_capture_header(await capture_bytes(), normalized_contract="gex-terminal.normalized-message.v9")
        # The shared byte integrity gate accepts the envelope; intake must still
        # enforce the supported interpretation of the verified bytes.
        verify_captured_session_bytes(unsupported)
        with self.assertRaisesRegex(IntakeError, "unsupported normalized message contract"):
            SessionIntake().inspect(unsupported)

    async def test_bundled_legacy_and_nq_v2_capture_prefixes_reproduce_without_source_file(self):
        for fixture, symbol, multiplier in (("es_zero_gamma_flip.jsonl", "ES", 50), ("nq_research_loop_v2.jsonl", "NQ", 20)):
            with self.subTest(fixture=fixture):
                path = Path(__file__).parents[1] / "gex_terminal" / "data" / "replays" / fixture
                events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                intake = SessionIntake()
                inspected = intake.inspect(await capture_bytes(events, source={"symbol": symbol, "provider": "replay",
                                                                               "mode": "replay", "source_kind": "synthetic_fixture"},
                                                               model_inputs={"contract_multiplier": multiplier}))
                opaque = await intake.checkpoint(inspected["intake_id"], inspected["default_sequence"])
                intake.clear()
                request = {"session": "terminal-checkpoint", "checkpoint": 0, "terminal_checkpoint": opaque,
                           "model": "terminal_selected"}
                result = await calculate(request)
                self.assertEqual(result["comparison"]["net_gex_delta"], 0)
                self.assertEqual(result["request"]["terminal_checkpoint"], opaque)
                self.assertEqual(validate_checkpoint(opaque)["parameters"]["contract_multiplier"], multiplier)

    async def test_unknown_provider_namespaces_remain_distinct_and_are_opaque(self):
        events = messages()
        events[1]["provider"] = "private-account-a"
        events[2]["provider"] = "private-account-b"
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes(events))
        opaque = await intake.checkpoint(inspected["intake_id"], 2)
        self.assertNotIn("private-account", opaque)
        self.assertEqual(len({row["provider"] for row in validate_checkpoint(opaque)["rows"]}), 2)

    async def test_conflicting_prefix_does_not_log_source_contract_labels(self):
        secret = "ACCOUNT-CONTRACT-PRIVATE"
        events = messages()
        events[1]["contract_id"] = secret
        events[2] = {**events[1], "strike": 5100, "sequence": 2,
                     "event_time": "2026-10-18T15:30:02Z"}
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes(events))
        with self.assertLogs("gex_terminal.consumer", level="ERROR") as logged:
            with self.assertRaisesRegex(IntakeError, "conflicting contract state"):
                await intake.checkpoint(inspected["intake_id"], 2)
        self.assertNotIn(secret, "\n".join(logged.output))
        self.assertNotIn(secret, await intake.checkpoint(inspected["intake_id"], 1))

    async def test_opaque_underlying_links_keep_rollover_quarantine_and_prefix_parity(self):
        events = messages()[:2]
        events[0]["contract_id"] = "private-front-future"
        events[1]["underlying_contract_id"] = "private-front-future"
        events += [
            {**events[0], "contract_id": "private-next-future", "price": 5100.0,
             "event_time": "2026-10-18T15:35:00Z"},
            {**events[1], "contract_id": "next-call", "underlying_contract_id": "private-next-future",
             "volume": 80, "event_time": "2026-10-18T15:35:01Z"},
        ]
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes(events))
        before = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 1))
        after_opaque = await intake.checkpoint(inspected["intake_id"], 3)
        after = validate_checkpoint(after_opaque)
        self.assertEqual([row["accumulated_volume"] for row in before["rows"]], [100])
        self.assertEqual([row["accumulated_volume"] for row in after["rows"]], [80])
        self.assertEqual(after["parameters"]["spot"], 5100)
        self.assertNotIn("private-front", after_opaque)
        self.assertNotIn("private-next", after_opaque)


class CaptureBytesVerifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_verifier_checks_complete_bytes_and_event_bound(self):
        data = await capture_bytes()
        header, footer, events = verify_captured_session_bytes(data)
        self.assertEqual(footer["event_count"], len(events))
        self.assertEqual(header["source"]["symbol"], "ES")
        with self.assertRaises(ValueError):
            verify_captured_session_bytes(data, max_events=2)
        with self.assertRaises(ValueError):
            verify_captured_session_bytes(data, max_bytes=len(data) - 1)


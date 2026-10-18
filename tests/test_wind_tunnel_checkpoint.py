"""Terminal parity, immutable transport and fail-closed offline handoff tests."""
import asyncio
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal import wind_tunnel as wind
from gex_terminal.wind_tunnel_checkpoint import (
    build_terminal_checkpoint, checkpoint_sha256, checkpoint_transport, read_checkpoint, validate_checkpoint, write_checkpoint,
)


AS_OF = "2026-09-04T13:35:00Z"


def option(contract_id, option_type="C", source="trade_volume", volume=10, **overrides):
    return {"schema_version": 2, "type": "options_volume_tick", "provider": "synthetic",
            "symbol": "ES", "contract_id": contract_id, "strike": 6000,
            "option_type": option_type, "volume": volume,
            "volume_semantics": "cumulative" if source == "open_interest" else "incremental",
            "position_source": source, "iv": .2, "iv_source": "provider",
            "instrument_class": "futures_option", "expiry": "2026-09-04",
            "expiry_timestamp": "2026-09-04T20:00:00Z", "event_time": AS_OF,
            "aggressor_side": "unknown", "direction_source": "unknown", **overrides}


async def emit(consumer, message):
    assert await consumer.update_market_state(json.dumps(message)), message


async def mixed_basis_consumer():
    consumer = StatefulGexConsumer(IntradayGexEngine(12), data_mode="replay", risk_free_rate=.017)
    await emit(consumer, {"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                          "symbol": "ES", "price": 6003.5, "event_time": AS_OF})
    await emit(consumer, option("call-trade", source="open_interest", volume=100, contract_multiplier=50))
    await emit(consumer, option("call-trade", volume=10, contract_multiplier=50,
                                aggressor_side="buy", direction_source="provider"))
    await emit(consumer, option("put-oi", "P", "open_interest", 50, strike=6050,
                                expiry="2026-09-05", expiry_timestamp="2026-09-05T20:00:00Z"))
    await emit(consumer, option("zero-trade", volume=0, strike=5950,
                                expiry="2026-09-06", expiry_timestamp=None, days_to_expiry=.6,
                                volume_semantics="cumulative"))
    await emit(consumer, option("zero-trade", source="open_interest", volume=30, strike=5950,
                                expiry="2026-09-06", expiry_timestamp=None, days_to_expiry=.6))
    await emit(consumer, option("fallback", volume=7, strike=5900, expiry="2026-09-06", expiry_timestamp=None))
    return consumer


class TerminalCheckpointTests(unittest.IsolatedAsyncioTestCase):
    def assert_matrix_equal(self, actual, expected):
        for key in ("strikes", "gammas", "call_volume", "put_volume", "call_gex", "put_gex", "net_gex",
                    "total_net_gex", "gamma_wall_strike", "zero_gamma_strike"):
            np.testing.assert_allclose(actual[key], expected[key], rtol=1e-12, atol=1e-8, err_msg=key)

    async def test_zero_shock_exact_terminal_parity_and_separate_quantity_models(self):
        consumer = await mixed_basis_consumer()
        for expiry_filter in ("all", "0dte", "2026-09-04", "2026-09-05"):
            with self.subTest(expiry_filter=expiry_filter):
                consumer.set_expiry_filter(expiry_filter)
                expected = await consumer.process_latest_snapshot(.7)
                artifact = await build_terminal_checkpoint(consumer, fallback_dte=.7)
                result = await wind.calculate({"terminal_checkpoint": artifact})
                self.assertEqual(result["request"]["model"], "terminal_selected")
                self.assertEqual(result["request"]["risk_free_rate"], .017)
                self.assertEqual(result["request"]["fallback_dte"], .7)
                self.assertEqual(result["source"]["expiry_filter"], expiry_filter)
                self.assertEqual(result["source"]["contract_multiplier"], 12)
                self.assertEqual(result["baseline"], result["scenario"])
                self.assert_matrix_equal(result["baseline"]["matrix"], expected)
        consumer.set_expiry_filter("all")
        core = wind.TerminalCheckpointCore(await build_terminal_checkpoint(consumer, fallback_dte=.7))
        selected = await core.calculate({})
        raw = await core.calculate({"model": "raw_trade_volume"})
        oi = await core.calculate({"model": "open_interest"})
        self.assertEqual(selected["baseline"]["summary"]["quantity"], 97)
        self.assertEqual(raw["baseline"]["summary"]["quantity"], 17)
        self.assertEqual(oi["baseline"]["summary"]["quantity"], 180)
        choices = {row["contract_id"]: row["position_source"] for row in selected["baseline"]["contracts"]}
        self.assertEqual(choices, {"call-trade": "trade_volume", "put-oi": "open_interest",
                                   "zero-trade": "open_interest", "fallback": "trade_volume"})
        directional = await core.calculate({"model": "directionalized_trade_volume", "minimum_directional_coverage": 0})
        self.assertEqual(directional["baseline"]["summary"]["quantity"], 17)

    async def test_legacy_filtered_projection_parity_includes_last_iv_behavior(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(9), data_mode="demo", risk_free_rate=.031)
        await emit(consumer, {"type": "underlying_tick", "symbol": "ES", "price": 6000, "timestamp": AS_OF})
        for expiry, strike, side, quantity, iv in (("2026-09-04", 6000, "C", 20, .18),
                ("2026-09-04", 6000, "P", 10, .2), ("2026-09-05", 6000, "C", 5, .25),
                ("2026-09-05", 6050, "P", 13, .24)):
            await emit(consumer, {"type": "options_volume_tick", "strike": strike, "option_type": side,
                                  "volume": quantity, "iv": iv, "expiry": expiry, "timestamp": AS_OF})
        for expiry_filter in ("all", "0dte", "2026-09-05"):
            consumer.set_expiry_filter(expiry_filter)
            artifact = await build_terminal_checkpoint(consumer, fallback_dte=.012)
            result = await wind.calculate({"terminal_checkpoint": artifact})
            self.assert_matrix_equal(result["baseline"]["matrix"], await consumer.process_latest_snapshot(.012))
            after = await wind.calculate({"terminal_checkpoint": artifact, "time_advance": 18})
            self.assertEqual(after["scenario"]["status"], "no_data")
        unsupported = await wind.calculate({"terminal_checkpoint": artifact, "model": "directionalized_trade_volume"})
        self.assertEqual(unsupported["scenario"]["status"], "insufficient_directional_coverage")

    async def test_rollover_invalidated_oi_and_expired_contracts_never_enter_artifact(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="replay")
        await emit(consumer, {"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                              "symbol": "ES", "contract_id": "old-future", "price": 6000, "event_time": AS_OF})
        await emit(consumer, option("old-option", underlying_contract_id="old-future"))
        await emit(consumer, option("deleted", source="open_interest", volume=0,
                                    open_interest_update_action="delete", open_interest_reference_date="2026-09-04"))
        await emit(consumer, option("expired", expiry_timestamp="2026-09-04T13:00:00Z"))
        await emit(consumer, option("current-option", underlying_contract_id="new-future"))
        await emit(consumer, {"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                              "symbol": "ES", "contract_id": "new-future", "price": 6010,
                              "event_time": "2026-09-04T13:36:00Z"})
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertEqual({row["contract_id"] for row in artifact["rows"]}, {"current-option"})
        self.assertEqual(len(consumer.contract_state), 4)
        self.assert_matrix_equal((await wind.calculate({"terminal_checkpoint": artifact}))["baseline"]["matrix"],
                                 await consumer.process_latest_snapshot(.25))

    async def test_capture_waits_for_lock_then_remains_detached_from_later_ticks_and_callers(self):
        consumer = await mixed_basis_consumer()
        async with consumer.state_lock:
            task = asyncio.create_task(build_terminal_checkpoint(consumer, fallback_dte=.7))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            consumer.current_spot = 6011
            consumer.risk_free_rate = .023
            consumer.engine.multiplier = 17
        artifact = await task
        self.assertEqual(artifact["parameters"], {"spot": 6011, "risk_free_rate": .023,
                                                 "contract_multiplier": 17, "fallback_dte": .7})
        core = wind.TerminalCheckpointCore(artifact)
        before = await core.calculate({})
        await emit(consumer, option("call-trade", volume=1000))
        consumer.current_spot = 6050
        artifact["rows"][0]["iv"] = .9
        catalog = core.catalog()
        copied_artifact = json.loads(catalog["sessions"][0]["terminal_checkpoint"])
        copied_artifact["rows"][0]["iv"] = 1.1
        catalog["sessions"][0]["terminal_checkpoint"] = json.dumps(copied_artifact)
        self.assertEqual(await core.calculate({}), before)

    async def test_receipt_reproduces_without_original_file_server_or_consumer(self):
        artifact = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        with tempfile.TemporaryDirectory() as directory:
            path = write_checkpoint(Path(directory) / "checkpoint.json", artifact)
            core = wind.TerminalCheckpointCore(read_checkpoint(path))
            result = await core.calculate({"spot_shift": 15, "iv_shift": 1, "time_advance": 5})
            path.unlink()
        receipt_request = json.loads(json.dumps(result))["request"]
        self.assertEqual(result, await wind.calculate(receipt_request))
        surface = await core.surface({"spot_shifts": [-5, 0, 5], "time_advances": [0, 15]})
        self.assertEqual(surface, await wind.surface(surface["request"]))
        search = await core.search({"x_values": [-500, -100, 0, 100, 500], "y_values": [-10, 0, 10], "claim": "model_disagreement"})
        self.assertEqual(search, await wind.search(search["request"]))
        self.assertEqual(search["outcome"], "break_found")
        self.assertIn("terminal_checkpoint", search["smallest_change"]["request"])
        self.assertEqual(search["smallest_change"]["scenario"],
                         (await wind.calculate(search["smallest_change"]["request"]))["scenario"])

    async def test_catalog_keeps_bundled_sessions_and_source_specific_defaults(self):
        artifact = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        core = wind.TerminalCheckpointCore(artifact)
        catalog = core.catalog()
        self.assertEqual(catalog["defaults"]["model"], "terminal_selected")
        self.assertEqual(catalog["bundled_defaults"], wind.DEFAULTS)
        self.assertEqual(catalog["sessions"][1:], wind.catalog()["sessions"])
        self.assertEqual(validate_checkpoint(catalog["sessions"][0]["terminal_checkpoint"]), artifact)
        self.assertEqual(core.checkpoints("terminal-checkpoint")["checkpoints"][0]["as_of"], AS_OF)
        self.assertEqual(await core.calculate({"session": "wind-tunnel-lab"}), await wind.calculate({}))
        self.assertEqual(core.examples("no-break"), wind.examples("no-break"))

    async def test_capture_rejects_live_missing_time_mixed_empty_and_oversized_state(self):
        for mode in ("live", "replay"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                await build_terminal_checkpoint(StatefulGexConsumer(IntradayGexEngine(50), data_mode=mode), fallback_dte=.25)
        consumer = await mixed_basis_consumer()
        await emit(consumer, {"type": "options_volume_tick", "strike": 6000, "option_type": "C",
                              "volume": 1, "iv": .2, "timestamp": AS_OF})
        with self.assertRaisesRegex(ValueError, "Mixed legacy"):
            await build_terminal_checkpoint(consumer, fallback_dte=.25)
        consumer = await mixed_basis_consumer()
        consumer.set_expiry_filter("absent")
        with self.assertRaisesRegex(ValueError, "between 1 and 5000"):
            await build_terminal_checkpoint(consumer, fallback_dte=.25)
        consumer = await mixed_basis_consumer()
        state = next(iter(consumer.contract_state.values()))
        consumer.contract_state.update({("synthetic", f"oversize-{n}", "trade_volume"): state for n in range(5001)})
        with self.assertRaisesRegex(ValueError, "5000-row"):
            await build_terminal_checkpoint(consumer, fallback_dte=.25)
        consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="replay")
        await emit(consumer, {"type": "underlying_tick", "symbol": "ES", "price": 6000, "timestamp": AS_OF})
        await emit(consumer, {"type": "options_volume_tick", "strike": 6000, "option_type": "C", "volume": 1})
        with self.assertRaisesRegex(ValueError, "missing market time"):
            await build_terminal_checkpoint(consumer, fallback_dte=.25)

    async def test_strict_artifact_validation_and_allowlist_strip_private_fields(self):
        consumer = await mixed_basis_consumer()
        for row in consumer.contract_state.values():
            row["secret"] = "must-never-serialize"
            row["iv_provenance"] = {"path": "/private/capture"}
        consumer.record_quality_note("must-never-serialize")
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.7)
        self.assertNotIn("must-never-serialize", json.dumps(artifact))
        self.assertNotIn("/private/capture", json.dumps(artifact))
        mutations = [
            lambda a: a.update(version=2), lambda a: a.update(secret="private"),
            lambda a: a["source"].update(path="/private"), lambda a: a["source"].update(data_mode="LIVE"),
            lambda a: a["source"].update(as_of="missing"), lambda a: a["source"]["quality"].update(notes=["private"]),
            lambda a: a["parameters"].update(spot=float("nan")), lambda a: a["parameters"].update(fallback_dte=0),
            lambda a: a["rows"][0].update(extra="private"), lambda a: a["rows"][0].update(event_time="2099-01-01T00:00:00Z"),
            lambda a: a["rows"][0].update(event_time=None), lambda a: a["rows"][0].update(accumulated_volume=True),
            lambda a: a["rows"][0].update(expiry_timestamp="2026-09-04T13:00:00Z"),
            lambda a: a["rows"][0].update(terminal_selected=1), lambda a: a["rows"][0].update(iv=6),
            lambda a: a["rows"].append(copy.deepcopy(a["rows"][0])),
            lambda a: a["rows"][0]["directional_volume"].update(unknown=999),
            lambda a: a["rows"][0].update(open_interest_reference_date="2099-01-01"),
            lambda a: a["rows"][0].update(terminal_selected=not a["rows"][0]["terminal_selected"]),
        ]
        for mutation in mutations:
            broken = copy.deepcopy(artifact)
            mutation(broken)
            try:
                broken["sha256"] = checkpoint_sha256(broken)
            except ValueError:
                pass
            with self.subTest(broken=str(broken)[:100]), self.assertRaises(ValueError):
                validate_checkpoint(broken)
        broken = copy.deepcopy(artifact)
        broken["parameters"]["spot"] += 1
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            validate_checkpoint(broken)

    async def test_invalid_requests_cannot_select_or_override_ambiguous_checkpoint_sources(self):
        artifact = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        for request in ({"terminal_checkpoint": artifact, "session": "wind-tunnel-lab"},
                        {"terminal_checkpoint": artifact, "checkpoint": 1},
                        {"terminal_checkpoint": artifact, "checkpoint": True},
                        {"terminal_checkpoint": None}, {"session": "terminal-checkpoint"},
                        {"model": "terminal_selected"}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                await wind.calculate(request)

    async def test_future_contract_mutation_fails_capture_and_file_limits_fail_closed(self):
        consumer = await mixed_basis_consumer()
        next(iter(consumer.contract_state.values()))["event_time"] = "2099-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future event"):
            await build_terminal_checkpoint(consumer, fallback_dte=.7)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for content in (b"x" * 2_000_001, b'{"broken":', b"\xff"):
                path.write_bytes(content)
                with self.assertRaises(ValueError):
                    read_checkpoint(path)

    async def test_checkpoint_file_io_rejects_overwrite_links_nonregular_and_duplicate_keys(self):
        artifact = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        with tempfile.TemporaryDirectory() as directory:
            path = write_checkpoint(Path(directory) / "checkpoint.json", artifact)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_checkpoint(path, artifact)
            self.assertEqual(path.read_bytes(), original)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_checkpoint(link)
            with self.assertRaises(FileExistsError):
                write_checkpoint(link, artifact)
            with self.assertRaises(ValueError):
                read_checkpoint(directory)
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):
                read_checkpoint(duplicate)
            if hasattr(os, "mkfifo"):
                fifo = Path(directory) / "fifo.json"
                os.mkfifo(fifo)
                with self.assertRaises(ValueError):
                    read_checkpoint(fifo)

    async def test_opaque_checkpoint_survives_actual_javascript_json_roundtrip(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable for browser JSON transport regression")
        artifact = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        request = wind.normalize_request({"terminal_checkpoint": artifact})
        self.assertIsInstance(request["terminal_checkpoint"], str)
        result = subprocess.run([node, "-e", "process.stdin.on('data', d => process.stdout.write(JSON.stringify(JSON.parse(d))))"],
                                input=json.dumps(request), capture_output=True, text=True, check=True)
        returned_request = json.loads(result.stdout)
        self.assertEqual(returned_request["terminal_checkpoint"], request["terminal_checkpoint"])
        self.assertEqual(validate_checkpoint(returned_request["terminal_checkpoint"]), artifact)
        self.assertEqual(await wind.calculate(request), await wind.calculate(returned_request))
        with self.assertRaises(ValueError):
            validate_checkpoint('{"schema":1,"schema":2}')

    async def test_conflicting_quantity_expiry_metadata_fails_before_filtering(self):
        for changed in ({"expiry": "2026-09-05"},
                        {"expiry_timestamp": "2026-09-04T13:00:00Z"},
                        {"days_to_expiry": .1}):
            for expiry_filter in ("all", "0dte", "2026-09-04"):
                consumer = await mixed_basis_consumer()
                state = consumer.contract_state[("synthetic", "call-trade", "trade_volume")]
                state.update(changed)
                consumer.set_expiry_filter(expiry_filter)
                with self.subTest(changed=changed, expiry_filter=expiry_filter), self.assertRaisesRegex(ValueError, "conflicting contract identity"):
                    await build_terminal_checkpoint(consumer, fallback_dte=.7)
        artifact = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        artifact["source"]["expiry_filter"] = "0dte"
        artifact["sha256"] = checkpoint_sha256(artifact)
        with self.assertRaisesRegex(ValueError, "expiry filter"):
            validate_checkpoint(artifact)


if __name__ == "__main__":
    unittest.main()

"""Saved launch preparation uses one verified capture and no remote provider."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gex_terminal import saved_workspace
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.wind_tunnel import calculate
from gex_terminal.wind_tunnel_checkpoint import read_checkpoint
from tests.test_pricing_coverage import unavailable
from tests.test_session_intake import capture_bytes, messages
from tests.test_wind_tunnel_checkpoint import AS_OF, option


def python_command():
    command = [sys.executable]
    if sys.pycache_prefix:
        command.extend(["-X", f"pycache_prefix={sys.pycache_prefix}"])
    return command


class SavedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gex saved workspaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.capture = self.root / "original session.gex-session.jsonl"

    def make_capture(self, *, symbol="ES", model_inputs=None, events=None, source=None):
        self.capture.write_bytes(asyncio.run(capture_bytes(
            events=messages(symbol, 50 if symbol == "ES" else 20) if events is None else events,
            source=source if source is not None else {"provider": "synthetic", "mode": "replay", "symbol": symbol},
            model_inputs=model_inputs,
        )))
        return self.capture

    def prepare(self, symbol="ES", name="workspace"):
        return saved_workspace.prepare_saved_workspace(self.capture, symbol, self.root / name)

    def test_explicit_assumptions_frozen_bytes_and_final_parameters(self):
        self.make_capture(model_inputs={"contract_multiplier": 12, "risk_free_rate": .017,
                                        "days_to_expiry": .7, "expiry_filter": "0dte"})
        original = self.capture.read_bytes()
        with patch.dict(os.environ, {"GEX_DATA_MODE": "live", "GEX_SYMBOL": "NQ",
                                      "GEX_RISK_FREE_RATE": "bad", "DATABENTO_API_KEY": "must-not-use"}):
            plan = self.prepare()
        self.assertEqual(Path(plan["capture_path"]).read_bytes(), original)
        self.assertEqual(plan["capture_sha256"], hashlib.sha256(original).hexdigest())
        self.capture.write_text("external original changed after preparation")
        self.assertEqual(Path(plan["capture_path"]).read_bytes(), original)
        checkpoint = read_checkpoint(plan["checkpoint_path"])
        self.assertEqual(plan["checkpoint_sha256"], checkpoint["sha256"])
        self.assertEqual(checkpoint["parameters"], {"spot": 5200., "risk_free_rate": .017,
                                                   "fallback_dte": .7, "contract_multiplier": 12})
        self.assertEqual(checkpoint["source"]["as_of"], "2026-10-18T15:45:00Z")
        self.assertEqual(checkpoint["source"]["data_mode"], "REPLAY")
        self.assertEqual(checkpoint["source"]["expiry_filter"], "all")
        self.assertEqual(plan["assumptions"]["sources"], {"contract_multiplier": "capture",
                                                         "risk_free_rate": "capture", "days_to_expiry": "capture"})
        self.assertEqual(plan["assumptions"]["captured_expiry_filter"], "0dte")
        self.assertIn(str(Path(plan["capture_path"])), plan["terminal_args"])
        self.assertEqual(plan["terminal_args"][0:2], ["--mode", "replay"])
        self.assertNotIn("--replay-session", plan["terminal_args"])
        self.assertEqual(stat.S_IMODE((self.root / "workspace").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(Path(plan["capture_path"]).stat().st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(Path(plan["checkpoint_path"]).stat().st_mode), 0o600)

    def test_missing_assumptions_are_recorded_and_nq_multiplier_is_twenty(self):
        self.make_capture(symbol="NQ", model_inputs={})
        plan = self.prepare("NQ")
        self.assertEqual((plan["contract_multiplier"], plan["risk_free_rate"], plan["fallback_dte"]), (20, .045, .25))
        self.assertEqual(set(plan["assumptions"]["defaults_applied"]),
                         {"contract_multiplier", "risk_free_rate", "days_to_expiry"})
        self.assertEqual(read_checkpoint(plan["checkpoint_path"])["parameters"]["contract_multiplier"], 20)

    def test_invalid_supplied_assumptions_are_not_replaced(self):
        cases = [("risk_free_rate", None), ("risk_free_rate", True), ("risk_free_rate", "0.04"),
                 ("risk_free_rate", 1.1), ("days_to_expiry", 0), ("days_to_expiry", 31),
                 ("contract_multiplier", 20.0), ("contract_multiplier", 0), ("contract_multiplier", True)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.make_capture(model_inputs={key: value})
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse((self.root / "workspace").exists())

    def test_incomplete_tampered_raw_and_wrong_symbol_fail_before_workspace_exists(self):
        self.make_capture()
        original = self.capture.read_bytes()
        candidates = [b"\n".join(original.splitlines()[:-1]),
                      original.replace(b'"volume":100', b'"volume":101'),
                      json.dumps(messages()[0]).encode()]
        for invalid in candidates:
            with self.subTest(invalid=invalid[:30]):
                self.capture.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse((self.root / "workspace").exists())
        self.capture.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "symbol"):
            self.prepare("NQ")
        self.make_capture(events=messages("NQ", 20))
        with self.assertRaisesRegex(ValueError, "symbol"):
            self.prepare()

    def test_symlink_oversized_and_existing_destination_are_rejected(self):
        self.make_capture()
        link = self.root / "symlink.jsonl"
        link.symlink_to(self.capture)
        with self.assertRaises(OSError):
            saved_workspace.prepare_saved_workspace(link, "ES", self.root / "workspace")
        self.capture.write_bytes(b"x" * (saved_workspace.MAX_CAPTURE_BYTES + 1))
        with self.assertRaises(ValueError):
            self.prepare()
        self.make_capture()
        (self.root / "workspace").mkdir()
        marker = self.root / "workspace" / "keep.txt"
        marker.write_text("preserve prior research")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(marker.read_text(), "preserve prior research")

    def test_checkpoint_failure_cleans_only_new_destination(self):
        self.make_capture()
        with patch.object(saved_workspace, "write_checkpoint", side_effect=ValueError("unsupported checkpoint")):
            with self.assertRaisesRegex(ValueError, "unsupported checkpoint"):
                self.prepare()
        self.assertTrue(self.capture.is_file())
        self.assertFalse((self.root / "workspace").exists())

    def test_unpriced_contract_and_coverage_match_production_final_state(self):
        events = [{"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                   "symbol": "NQ", "price": 6000, "event_time": AS_OF},
                  option("priced", volume=10, symbol="NQ", contract_multiplier=20),
                  unavailable("unpriced", symbol="NQ", contract_multiplier=20)]
        self.make_capture(symbol="NQ", model_inputs={"contract_multiplier": 20, "risk_free_rate": .037,
                                                     "days_to_expiry": .5}, events=events)
        plan = self.prepare("NQ")
        checkpoint = read_checkpoint(plan["checkpoint_path"])
        self.assertIsNone(next(row for row in checkpoint["rows"] if row["contract_id"] == "unpriced")["iv"])

        async def compare():
            consumer = StatefulGexConsumer(IntradayGexEngine(20), target_underlying="NQ",
                                           data_mode="replay", risk_free_rate=.037)
            for event in events:
                await consumer.update_market_state(json.dumps(event))
            expected = await consumer.process_latest_snapshot(.5)
            calculated = await calculate({"terminal_checkpoint": checkpoint})
            self.assertEqual(calculated["baseline"]["pricing_coverage"], expected["pricing_coverage"])
            self.assertEqual(calculated["baseline"]["pricing_coverage"]["unpriced_quantity"], 7)
            self.assertEqual(calculated["baseline"]["pricing_coverage"]["priced_contract_count"], 1)
            self.assertEqual(calculated["baseline"]["excluded_contracts"][0]["contract_id"], "unpriced")
        asyncio.run(compare())

    def test_all_unpriced_capture_retains_its_checkpoint(self):
        self.make_capture(events=[{"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                                   "symbol": "ES", "price": 6000, "event_time": AS_OF}, unavailable()])
        checkpoint = read_checkpoint(self.prepare()["checkpoint_path"])
        self.assertEqual(len(checkpoint["rows"]), 1)
        self.assertIsNone(checkpoint["rows"][0]["iv"])

    def test_module_prints_one_json_plan(self):
        self.make_capture()
        result = subprocess.run([*python_command(), "-m", "gex_terminal.saved_workspace", str(self.capture),
                                 "ES", str(self.root / "module workspace")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(json.loads(result.stdout)["symbol"], "ES")


class SavedNetworkGuardTests(unittest.TestCase):
    def test_remote_dns_connect_and_udp_are_blocked_while_loopback_remains_usable(self):
        code = '''
import socket
from gex_terminal.saved_workspace import restrict_network_to_loopback
restrict_network_to_loopback()
def connect(method):
    with socket.socket() as client:
        return getattr(client, method)(('203.0.113.1', 443))
def send_datagram():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        return client.sendto(b'x', ('203.0.113.1', 123))
blocked = 0
for operation in (lambda: socket.getaddrinfo('example.invalid', 443),
                  lambda: socket.gethostbyname('example.invalid'),
                  lambda: connect('connect'), lambda: connect('connect_ex'), send_datagram):
    try:
        operation()
    except PermissionError:
        blocked += 1
assert blocked == 5, blocked
assert socket.getaddrinfo('127.0.0.1', 0)
with socket.socket() as server:
    server.bind(('127.0.0.1', 0))
    server.listen()
    with socket.create_connection(server.getsockname(), timeout=1):
        accepted, _ = server.accept()
        accepted.close()
print('guard passed')
'''
        result = subprocess.run([*python_command(), "-c", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "guard passed")


if __name__ == "__main__":
    unittest.main()

"""Only explicitly supplied and registered local checkpoints reach the picker."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gex_terminal import wind_tunnel as wind
from gex_terminal import wind_tunnel_sources as sources
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, checkpoint_sha256, write_checkpoint
from tests.test_wind_tunnel_checkpoint import mixed_basis_consumer


class SavedCheckpointSourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="private saved input ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.es = await build_terminal_checkpoint(await mixed_basis_consumer(), fallback_dte=.7)
        self.nq = copy.deepcopy(self.es)
        self.nq["source"]["symbol"] = "NQ"
        self.nq["parameters"]["contract_multiplier"] = 20
        for row in self.nq["rows"]:
            row["symbol"] = "NQ"
        self.nq["sha256"] = checkpoint_sha256(self.nq)
        self.es_path = write_checkpoint(self.root / "es.json", self.es)
        self.nq_path = write_checkpoint(self.root / "nq.json", self.nq)

    async def test_catalog_preserves_primary_defaults_and_integrity_and_omits_operator_paths(self):
        with patch.dict("os.environ", {"DATABENTO_API_KEY": "private-key-never-read"}):
            core = sources.checkpoint_core(self.es_path, [self.nq_path, self.es_path])
            catalog = core.catalog()
        self.assertEqual(catalog["defaults"]["session"], "terminal-checkpoint")
        self.assertEqual(catalog["sessions"][0]["symbol"], "ES")
        self.assertEqual([item["symbol"] for item in catalog["saved_checkpoints"]], ["ES", "NQ"])
        self.assertEqual([json.loads(item["artifact"])["sha256"] for item in catalog["saved_checkpoints"]],
                         [self.es["sha256"], self.nq["sha256"]])
        digest = catalog.pop("result_sha256")
        self.assertEqual(digest, wind._sha(catalog))
        serialized = json.dumps(catalog)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("private-key-never-read", serialized)
        self.assertEqual(core.calculation_identity(), wind.calculation_identity())
        primary = await core.calculate({})
        other = await core.calculate({"session": "terminal-checkpoint",
                                      "terminal_checkpoint": catalog["saved_checkpoints"][1]["artifact"]})
        self.assertEqual(primary["source"]["symbol"], "ES")
        self.assertEqual(other["source"]["symbol"], "NQ")

    async def test_new_core_operations_delegate_with_primary_injection(self):
        core = sources.checkpoint_core(self.es_path, [self.nq_path])

        async def future_operation(instance, request):
            return instance._request(request)

        with patch.object(wind.TerminalCheckpointCore, "future_operation", future_operation, create=True):
            result = await core.future_operation({"spot_shift": 25})
        self.assertEqual(result["terminal_checkpoint"], self.es)
        self.assertEqual(result["spot_shift"], 25)

    async def test_bounds_and_every_explicit_input_fail_closed(self):
        self.assertIsNone(sources.checkpoint_core(None))
        with self.assertRaisesRegex(ValueError, "require --checkpoint"):
            sources.checkpoint_core(None, [self.nq_path])
        with self.assertRaisesRegex(ValueError, "at most two"):
            sources.checkpoint_core(self.es_path, [self.nq_path] * 3)
        corrupt = self.root / "corrupt.json"
        corrupt.write_text('{"sha256":"wrong"}')
        link = self.root / "linked.json"
        link.symlink_to(self.es_path)
        for invalid in (corrupt, link, self.root):
            with self.subTest(invalid=invalid.name), self.assertRaises(ValueError):
                sources.checkpoint_core(self.es_path, [invalid])
        # Validate duplicate inputs before deduplication, including a symlink to
        # the otherwise valid primary file.
        with self.assertRaises(ValueError):
            sources.checkpoint_core(self.es_path, [self.es_path, link])

    async def test_registered_checkpoint_detects_changed_capture_or_checkpoint_without_replay(self):
        capture = self.root / "frozen.gex-session.jsonl"
        raw = b"previously verified frozen capture bytes"
        capture.write_bytes(raw)
        checksum = hashlib.sha256(raw).hexdigest()
        check = lambda: sources.validate_registered_checkpoint(
            self.nq_path, capture, "NQ", self.nq["sha256"], checksum)
        with patch("gex_terminal.saved_workspace._checkpoint", side_effect=AssertionError("must not replay")):
            self.assertEqual(check(), {"symbol": "NQ", "checkpoint_sha256": self.nq["sha256"]})
        capture.write_bytes(raw + b"changed")
        with self.assertRaisesRegex(ValueError, "capture changed"):
            check()
        capture.unlink()
        capture.symlink_to(self.es_path)
        with self.assertRaises(OSError):
            check()
        capture.unlink()
        capture.write_bytes(raw)
        self.nq_path.write_text("{}")
        with self.assertRaises(ValueError):
            check()

    async def test_registered_checkpoint_rejects_wrong_symbol_and_stale_binding(self):
        for symbol, digest in (("ES", self.nq["sha256"]), ("NQ", "0" * 64), ("OTHER", self.nq["sha256"])):
            with self.subTest(symbol=symbol, digest=digest), self.assertRaises(ValueError):
                sources.validate_registered_checkpoint(self.nq_path, self.root / "unused", symbol, digest, "1" * 64)


if __name__ == "__main__":
    unittest.main()

"""Command dispatch and refusal checks; no credentialed network is used."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from gex_terminal import cli
from tests.test_capture_governance import _valid_policy


class TradovateCaptureCLITests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, arguments, collector):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["gex-terminal", *arguments]), \
                patch.object(cli, "capture_tradovate_payloads", collector), \
                patch.object(cli, "configure_logging"), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                await cli.main()
            except SystemExit as error:
                return error.code, stdout.getvalue(), stderr.getvalue()
        return 0, stdout.getvalue(), stderr.getvalue()

    async def test_routes_explicit_limits_without_model_config_or_capture_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(json.dumps(_valid_policy()))
            output = Path(directory) / "private-output"
            collector = AsyncMock(return_value={"status": "complete"})
            with patch.dict(os.environ, {"GEX_RISK_FREE_RATE": "bad-model-value",
                                         "GEX_CONTRACT_MULTIPLIER": "bad-model-value"}):
                code, stdout, stderr = await self.invoke([
                    "tradovate-capture", str(output), "--capture-policy", str(policy_path),
                    "--ack-live-network", "--symbol", "NQ", "--tradovate-environment", "demo",
                    "--capture-duration", "30", "--max-option-contracts", "6",
                    "--capture-max-maturities", "3", "--capture-max-requests", "9",
                    "--capture-max-frames", "40", "--capture-max-bytes", "65536",
                    "--capture-max-frame-bytes", "4096",
                ], collector)
            self.assertEqual((code, stderr), (0, ""))
            self.assertIn("Issue #4 remains open", stdout)
            self.assertNotIn(directory, stdout)
            self.assertFalse(output.exists())  # Mock call; CLI does not create raw output.
            collector.assert_awaited_once_with(
                str(output), symbol="NQ", environment="demo", capture_policy=_valid_policy(),
                ack_live_network=True, duration_seconds=30.0, max_option_contracts=6,
                max_maturities=3, max_requests=9, max_frames=40,
                max_total_bytes=65536, max_frame_bytes=4096,
            )

    async def test_missing_network_ack_policy_or_new_output_refuses_before_collector(self):
        cases = [
            ["tradovate-capture"],
            ["tradovate-capture", "private"],
            ["tradovate-capture", "private", "--ack-live-network"],
            ["tradovate-capture", "private", "extra", "--ack-live-network"],
            ["tradovate-capture", "private", "--ack-live-network", "--capture-policy", "missing.json"],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                collector = AsyncMock()
                code, stdout, _ = await self.invoke(arguments, collector)
                self.assertNotEqual(code, 0)
                self.assertEqual(stdout, "")
                collector.assert_not_called()

    async def test_rejects_conflicting_normalized_recording_and_runtime_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / "policy.json"
            policy.write_text(json.dumps(_valid_policy()))
            for flags in (["--record-session"], ["--capture-path", "normalized.jsonl"],
                          ["--export", "snapshot.json"], ["--demo"], ["--mode", "live"],
                          ["--provider", "tradovate"], ["--wind-tunnel-checkpoint", "checkpoint.json"]):
                with self.subTest(flags=flags):
                    collector = AsyncMock()
                    code, _, _ = await self.invoke([
                        "tradovate-capture", str(Path(directory) / "output"),
                        "--ack-live-network", "--capture-policy", str(policy), *flags,
                    ], collector)
                    self.assertNotEqual(code, 0)
                    collector.assert_not_called()

    async def test_partial_failure_has_nonzero_exit_without_echoing_provider_values(self):
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / "policy.json"
            policy.write_text(json.dumps(_valid_policy()))
            arguments = ["tradovate-capture", str(Path(directory) / "output"),
                         "--ack-live-network", "--capture-policy", str(policy)]
            for result in ({"status": "partial"}, {"status": "failed"}):
                code, stdout, _ = await self.invoke(arguments, AsyncMock(return_value=result))
                self.assertEqual(code, 2)
                self.assertIn("review manifest.json", stdout)
            code, stdout, stderr = await self.invoke(
                arguments, AsyncMock(side_effect=ValueError("private-provider-value")),
            )
            self.assertNotEqual(code, 0)
            self.assertNotIn("private-provider-value", str(code) + stdout + stderr)

    async def test_safe_parser_error_for_rejected_numeric_value(self):
        collector = AsyncMock()
        code, stdout, stderr = await self.invoke(
            ["tradovate-capture", "private", "--capture-duration", "private-value"], collector,
        )
        self.assertEqual(code, 2)
        self.assertNotIn("private-value", stdout + stderr)
        collector.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gex_terminal import wind_tunnel_cli as cli
from tests.test_wind_tunnel_server import SmallCore


class WindTunnelCLITests(unittest.TestCase):
    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = cli.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_example_portable_round_trip_and_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, "core_module", return_value=SmallCore), \
                patch("gex_terminal.wind_tunnel_server.core_module", return_value=SmallCore):
            artifact = Path(directory) / "Named scenario.json"
            code, _, stderr = self.invoke(["example", "example", "--output", str(artifact)])
            self.assertEqual((code, stderr), (0, ""))
            original = artifact.read_bytes()
            code, output, stderr = self.invoke(["verify", str(artifact)])
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(json.loads(output)["status"], "verified")
            report = Path(directory) / "Reproduction.json"
            code, _, _ = self.invoke(["reproduce", str(artifact), "--output", str(report)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(report.read_text())["status"], "verified")
            code, _, stderr = self.invoke(["example", "example", "--output", str(artifact)])
            self.assertEqual(code, 1)
            self.assertIn("already exists", stderr)
            self.assertEqual(artifact.read_bytes(), original)

    def test_invalid_inputs_are_bounded_without_path_or_secret_leaks(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, "core_module", return_value=SmallCore):
            artifact = Path(directory) / "private-account.json"
            artifact.write_text('{"secret":"do-not-echo"}')
            code, output, stderr = self.invoke(["verify", str(artifact)])
            self.assertEqual(code, 1)
            self.assertEqual(output, "")
            self.assertNotIn(directory, stderr)
            self.assertNotIn("do-not-echo", stderr)
            link = Path(directory) / "linked.json"
            link.symlink_to(artifact)
            code, _, _ = self.invoke(["verify", str(link)])
            self.assertEqual(code, 1)

    def test_default_serve_options_are_explicit_and_no_browser_is_respected(self):
        calls = []

        async def fake_serve(workspace, *, port, no_browser):
            calls.append((workspace, port, no_browser))
            return 0

        with patch.object(cli, "core_module", return_value=SmallCore), patch.object(cli, "serve", fake_serve):
            self.assertEqual(self.invoke([])[0], 0)
            self.assertEqual(self.invoke(["--port", "0", "--no-browser", "--workspace", "Research Folder"])[0], 0)
        self.assertEqual(calls, [(Path("wind_tunnel_research"), 8765, False),
                                 (Path("Research Folder"), 0, True)])

    def test_real_cli_examples_reproduce_from_fresh_directory_with_polluted_configuration(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("GEX_DATA_PROVIDER=databento\nGEX_RISK_FREE_RATE=not-a-number\nDATABENTO_API_KEY=private-test-value\n")
            env = {**os.environ, "PYTHONPATH": str(repository), "GEX_DATA_MODE": "live",
                   "GEX_DATA_PROVIDER": "databento", "GEX_CONTRACT_MULTIPLIER": "bad"}
            for example, expected in (("discovered-break", "break_found"), ("no-break", "no_break_found"),
                                      ("expiry-exclusion", "available")):
                output = root / (example + ".json")
                command = [sys.executable, "-m", "gex_terminal.cli", "wind-tunnel", "example", example, "--output", str(output)]
                result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads(output.read_text())
                actual = receipt["result"].get("outcome") or receipt["result"]["scenario"]["status"]
                self.assertEqual(actual, expected)
                if example == "expiry-exclusion":
                    self.assertGreater(receipt["result"]["scenario"]["counts"]["excluded_nearest_rows"], 0)
                    self.assertGreater(receipt["result"]["scenario"]["counts"]["selected_rows"], 0)
                command = [sys.executable, "-m", "gex_terminal.wind_tunnel_cli", "verify", str(output)]
                checked = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(json.loads(checked.stdout)["status"], "verified")
                self.assertNotIn("private-test-value", output.read_text())
            help_result = subprocess.run([sys.executable, "-m", "gex_terminal.wind_tunnel_cli", "--help"],
                                         cwd=root, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("reproduce", help_result.stdout)


if __name__ == "__main__":
    unittest.main()

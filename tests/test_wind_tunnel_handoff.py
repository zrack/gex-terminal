import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from aiohttp import ClientSession

from gex_terminal.cli import seed_demo_session
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.tui import GexTerminalApp
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, read_checkpoint
from gex_terminal.wind_tunnel_handoff import TerminalHandoff
from gex_terminal.wind_tunnel_server import reproduce_receipt
from tests.test_tui_lifecycle import _config


async def seeded_checkpoint():
    consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="demo")
    await seed_demo_session(consumer)
    return await build_terminal_checkpoint(consumer, fallback_dte=.01)


class TerminalHandoffIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_cleanup_keeps_every_runner_owned_for_retry(self):
        for interruption in (asyncio.CancelledError(), OSError("cleanup interrupted")):
            with self.subTest(interruption=type(interruption).__name__), tempfile.TemporaryDirectory() as directory:
                owner = TerminalHandoff(directory)
                old = type("Runner", (), {"cleanup": AsyncMock(side_effect=[interruption, None])})()
                new = type("Runner", (), {"cleanup": AsyncMock()})()
                artifact = await seeded_checkpoint()
                with patch("gex_terminal.wind_tunnel_handoff.start_server", side_effect=[(old, "http://old"), (new, "http://new")]), \
                        patch("gex_terminal.wind_tunnel_handoff.webbrowser.open", return_value=True):
                    await owner.open(artifact)
                    with self.assertRaises(type(interruption)):
                        await owner.open(artifact)
                self.assertIn(old, owner._runners)
                self.assertNotIn(new, owner._runners)
                new.cleanup.assert_awaited_once()
                await owner.close()
                self.assertEqual(old.cleanup.await_count, 2)
                self.assertEqual(owner._runners, [])

    async def test_cancelled_close_retains_ownership_until_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = TerminalHandoff(directory)
            runner = type("Runner", (), {"cleanup": AsyncMock(side_effect=[asyncio.CancelledError(), None])})()
            with patch("gex_terminal.wind_tunnel_handoff.start_server", return_value=(runner, "http://local")), \
                    patch("gex_terminal.wind_tunnel_handoff.webbrowser.open", return_value=True):
                await owner.open(await seeded_checkpoint())
            with self.assertRaises(asyncio.CancelledError):
                await owner.close()
            self.assertIs(owner._runner, runner)
            self.assertIn(runner, owner._runners)
            await owner.close()
            self.assertEqual(owner._runners, [])

    async def test_real_http_save_and_portable_reproduction_after_owner_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = TerminalHandoff(Path(directory) / "local handoff")
            artifact = await seeded_checkpoint()
            with patch("gex_terminal.wind_tunnel_handoff.webbrowser.open", return_value=True):
                self.assertTrue(await owner.open(artifact))
            url = urlsplit(owner.launch_url)
            origin = f"{url.scheme}://{url.netloc}"
            headers = {"Origin": origin, "X-GEX-Capability": url.fragment.removeprefix("cap=")}
            try:
                async with ClientSession(headers=headers) as client:
                    async with client.get(origin + "/api/catalog") as response:
                        self.assertEqual(response.status, 200)
                        catalog = await response.json()
                    source = next(s for s in catalog["sessions"] if s["name"] == "terminal-checkpoint")
                    request = source["defaults"]
                    self.assertEqual(request["model"], "terminal_selected")
                    async with client.post(origin + "/api/calculate", json=request) as response:
                        self.assertEqual(response.status, 200)
                        baseline = await response.json()
                    self.assertEqual(baseline["comparison"]["net_gex_delta"], 0)
                    async with client.post(origin + "/api/receipts", json={
                        "name": "Frozen terminal", "kind": "calculate", "request": request,
                    }) as response:
                        self.assertEqual(response.status, 200)
                        saved = await response.json()
                    async with client.get(origin + "/api/receipts/" + saved["receipt_sha256"] + "/export") as response:
                        receipt = json.loads(await response.text())
                checkpoint_path = owner.checkpoint_path
                self.assertEqual(read_checkpoint(checkpoint_path), artifact)
                self.assertNotIn(headers["X-GEX-Capability"], checkpoint_path.read_text())
            finally:
                await owner.close()
            checkpoint_path.unlink()
            self.assertEqual((await reproduce_receipt(receipt))["status"], "verified")
            with self.assertRaisesRegex(ValueError, "stopped"):
                await owner.open(artifact)

    async def test_failed_replacement_preserves_old_service_and_browser_failure_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = TerminalHandoff(directory)
            artifact = await seeded_checkpoint()
            with patch("gex_terminal.wind_tunnel_handoff.webbrowser.open", return_value=False):
                self.assertFalse(await owner.open(artifact))
            old_runner, old_url = owner._runner, owner.launch_url
            with patch("gex_terminal.wind_tunnel_handoff.start_server", side_effect=OSError("local port unavailable")):
                with self.assertRaises(OSError):
                    await owner.open(artifact)
            self.assertIs(owner._runner, old_runner)
            self.assertEqual(owner.launch_url, old_url)
            with patch("gex_terminal.wind_tunnel_handoff.webbrowser.open", return_value=True):
                await owner.open(artifact)
            self.assertIsNot(owner._runner, old_runner)
            self.assertEqual(old_runner.sites, set())
            await owner.close()
            await owner.close()

    async def test_cancelled_browser_open_cleans_owned_service(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = TerminalHandoff(directory)
            with patch("gex_terminal.wind_tunnel_handoff.asyncio.to_thread", side_effect=asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await owner.open(await seeded_checkpoint())
            self.assertIsNone(owner._runner)
            self.assertIsNone(owner.launch_url)
            await owner.close()


class TerminalHandoffKeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_failure_after_terminal_exit_does_not_publish_to_closed_screen(self):
        started, release = asyncio.Event(), asyncio.Event()

        class BlockedHandoff:
            async def open(self, artifact):
                started.set()
                await release.wait()
                raise OSError("port unavailable after exit")

            async def close(self):
                pass

        consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="demo")
        await seed_demo_session(consumer)
        app = GexTerminalApp(consumer, _config())
        with patch("gex_terminal.wind_tunnel_handoff.TerminalHandoff", return_value=BlockedHandoff()):
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                task = asyncio.create_task(app.action_open_wind_tunnel())
                await asyncio.wait_for(started.wait(), 2)
            with patch.object(app, "notify") as notify, patch.object(app, "_render_events") as render:
                release.set()
                await asyncio.wait_for(task, 2)
                notify.assert_not_called()
                render.assert_not_called()
            self.assertIsNone(app._exception)

    async def test_focused_table_handoff_and_owner_cleanup_without_changing_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = TerminalHandoff(directory)
            runner = type("Runner", (), {"cleanup": AsyncMock()})()
            consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="demo")
            await seed_demo_session(consumer)
            before = await consumer.process_latest_snapshot(.01)
            app = GexTerminalApp(consumer, _config())
            with patch("gex_terminal.wind_tunnel_handoff.TerminalHandoff", return_value=owner), \
                    patch("gex_terminal.wind_tunnel_handoff.start_server", return_value=(runner, "http://127.0.0.1:8765/#cap=test")), \
                    patch("gex_terminal.wind_tunnel_handoff.webbrowser.open", return_value=True):
                async with app.run_test(size=(160, 48)) as pilot:
                    await pilot.pause()
                    app.query_one("#gex-table").focus()
                    await pilot.press("w")
                    await pilot.pause()
                    self.assertIs(app._wind_tunnel_handoff, owner)
                    self.assertTrue(owner.checkpoint_path.is_file())
                    self.assertTrue(any("frozen checkpoint" in e for e in app._events))
                    await pilot.press("v")
                    await pilot.pause()
                    saved_path = owner.checkpoint_path
                    await pilot.press("w")
                    self.assertEqual(owner.checkpoint_path, saved_path)
                    self.assertEqual(runner.cleanup.await_count, 0)
                runner.cleanup.assert_awaited_once()
            after = await consumer.process_latest_snapshot(.01)
            self.assertEqual(before["total_net_gex"], after["total_net_gex"])
            self.assertEqual(list(before["net_gex"]), list(after["net_gex"]))

    async def test_live_action_fails_closed_without_starting_service(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="live")
        await seed_demo_session(consumer)
        app = GexTerminalApp(consumer, _config())
        with patch("gex_terminal.wind_tunnel_handoff.start_server") as start:
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                await pilot.press("w")
                await pilot.pause()
                self.assertIsNone(app._wind_tunnel_handoff)
                self.assertTrue(any("unavailable" in e for e in app._events))
            start.assert_not_called()


class CheckpointCLIHandoffTests(unittest.TestCase):
    def test_public_cli_export_then_portable_receipt_in_fresh_process(self):
        root = Path(__file__).resolve().parents[1]
        env = {key: value for key, value in os.environ.items() if not key.startswith("GEX_")}
        env["PYTHONPATH"] = str(root)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "Frozen checkpoint.json"
            command = [sys.executable, "-m", "gex_terminal.cli", "--demo", "--wind-tunnel-checkpoint", str(target)]
            result = subprocess.run(command, cwd=directory, env=env, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = target.read_bytes()
            artifact = read_checkpoint(target)
            receipt_path = Path(directory) / "receipt.json"
            from gex_terminal.wind_tunnel import TerminalCheckpointCore
            from gex_terminal.wind_tunnel_server import canonical_bytes, make_receipt
            core = TerminalCheckpointCore(artifact)
            source = next(s for s in core.catalog()["sessions"] if s["name"] == "terminal-checkpoint")
            receipt = asyncio.run(make_receipt("CLI checkpoint", "calculate", source["defaults"], core=core))
            receipt_path.write_bytes(canonical_bytes(receipt))
            target.unlink()
            reproduced = subprocess.run([sys.executable, "-m", "gex_terminal.cli", "wind-tunnel", "verify", str(receipt_path)],
                                        cwd=directory, env=env, text=True, capture_output=True, timeout=30)
            self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
            self.assertEqual(json.loads(reproduced.stdout)["status"], "verified")
            target.write_bytes(original)
            duplicate = subprocess.run(command, cwd=directory, env=env, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

"""Offline starter behavior exercised with inert, independently running children."""

import contextlib
import io
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import install_app
from tests.test_install_app import CLI, SOURCE, make_wheel


class TTYInput(io.StringIO):
    def isatty(self):
        return True


class StarterChoiceTests(unittest.TestCase):
    def choose(self, text, *, wind=True):
        output = TTYInput()
        with patch.object(install_app.sys, "stdin", TTYInput(text)), patch.object(install_app.sys, "stdout", output):
            result = install_app.choose_action(wind)
        return result, output.getvalue()

    def test_explicit_choices_and_invalid_input_retry(self):
        for text, expected in (("1\n", "terminal"), ("2\n", "wind"), ("3\n", "both"),
                               ("not a choice\n3\n", "both")):
            with self.subTest(text=text):
                selected, output = self.choose(text)
                self.assertEqual(selected, expected)
                for label in ("Terminal", "Wind Tunnel", "Both"):
                    self.assertIn(label, output)

    def test_empty_eof_and_cancel_never_choose_an_application(self):
        for text in ("", "\n", "q\n"):
            with self.subTest(text=text):
                self.assertIsNone(self.choose(text)[0])

    def test_legacy_wheel_cannot_choose_missing_interface(self):
        self.assertEqual(self.choose("1\n", wind=False)[0], "terminal")
        for text in ("2\nq\n", "3\nq\n"):
            with self.subTest(text=text):
                self.assertIsNone(self.choose(text, wind=False)[0])

    def test_either_noninteractive_stream_rejects_before_consuming_input(self):
        for stdin, stdout in ((io.StringIO("1\n"), TTYInput()), (TTYInput("1\n"), io.StringIO())):
            with patch.object(install_app.sys, "stdin", stdin), patch.object(install_app.sys, "stdout", stdout):
                with self.assertRaises(ValueError):
                    install_app.choose_action(True)
            self.assertEqual(stdin.tell(), 0)

    def test_saved_option_requires_support_and_symbol_selection_is_explicit(self):
        output = TTYInput()
        with patch.object(install_app.sys, "stdin", TTYInput("4\n")), patch.object(install_app.sys, "stdout", output):
            self.assertEqual(install_app.choose_action(True, saved_data=True), "saved")
        self.assertIn("no provider requests", output.getvalue())
        self.assertIsNone(self.choose("4\nq\n")[0])
        for text, expected in (("ES\n", "ES"), ("2\n", "NQ"), ("oops\nNQ\n", "NQ"), ("\n", None), ("", None)):
            with patch.object(install_app.sys, "stdin", TTYInput(text)), patch.object(install_app.sys, "stdout", TTYInput()):
                self.assertEqual(install_app.choose_saved_symbol(), expected)


class StarterSavedDataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gex saved starter's ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.research = self.root / "research"
        self.research.mkdir()
        self.capture = self.root / "original.gex-session.jsonl"
        self.capture.write_bytes(b"test frozen source")
        self.plan = {"capture_path": str(self.capture), "checkpoint_path": str(self.root / "checkpoint.json"),
                     "symbol": "NQ", "contract_multiplier": 20, "risk_free_rate": .035,
                     "fallback_dte": .5, "capture_sha256": install_app.digest(self.capture),
                     "replay_policy": "event_time_60x", "event_count": 875,
                     "first_event_time": "2026-10-16T13:34:58Z", "last_event_time": "2026-10-16T13:40:00Z",
                     "duration_seconds": 302,
                     "terminal_args": ["--mode", "replay", "--captured-session", str(self.capture),
                                       "--symbol", "NQ", "--multiplier", "20", "--expiry-filter", "all",
                                       "--replay-clock", "event", "--replay-speed", "60"]}
        self.receipt = {"research_dir": str(self.research), "active": {"payload_sha256": {
            "gex_terminal/wind_tunnel_cli.py": "1" * 64, "gex_terminal/saved_workspace.py": "2" * 64}}}
        for name, value in (("owned_target", self.receipt), ("active_environment", self.root / "environment"),
                            ("verify_payload", "verified")):
            patcher = patch.object(install_app, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def launch(self, **options):
        with patch.object(install_app.sys, "stdin", TTYInput()), patch.object(install_app.sys, "stdout", TTYInput()):
            return install_app.launch(self.root / "app", **options)

    def test_registration_and_remembered_launch_bind_both_children_to_same_frozen_source(self):
        with patch.object(install_app, "prepare_saved_data", return_value=self.plan) as prepare, \
                patch.object(install_app, "run_both", return_value=0) as both:
            self.assertEqual(self.launch(register_saved_data="NQ", captured_session=self.capture), 0)
            both.assert_not_called()
            record = install_app.saved_sources(self.research)
            self.assertEqual(record["sessions"]["NQ"]["capture_sha256"], self.plan["capture_sha256"])
            self.assertEqual((self.research / install_app.SAVED_DATA).stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.launch(saved_data="NQ", no_browser=True), 0)
        self.assertEqual(prepare.call_args.kwargs["expected_sha256"], self.plan["capture_sha256"])
        terminal, wind = both.call_args.args
        self.assertIn(install_app.SAVED_BOOTSTRAP, terminal)
        self.assertEqual(terminal[:7], wind[:7])
        self.assertEqual(terminal[4:7], ["0.035", "0.5", str(self.research)])
        self.assertEqual(terminal[-len(self.plan["terminal_args"]):], self.plan["terminal_args"])
        self.assertEqual(wind[wind.index("--checkpoint") + 1], self.plan["checkpoint_path"])
        self.assertTrue(both.call_args.kwargs["no_browser"])
        self.assertIn("final frozen", both.call_args.kwargs["source_note"])

    def test_launch_reports_saved_period_and_actual_playback_policy(self):
        for policy, clock, expected in (("fast_load", "none", "fast-loads"),
                                        ("event_time_60x", "event", "at 60x")):
            with self.subTest(policy=policy):
                plan = {**self.plan, "replay_policy": policy,
                        "event_count": 123456 if policy == "fast_load" else 875,
                        "terminal_args": list(self.plan["terminal_args"])}
                plan["terminal_args"][plan["terminal_args"].index("--replay-clock") + 1] = clock
                output = TTYInput()
                with patch.object(install_app.sys, "stdin", TTYInput()), \
                        patch.object(install_app.sys, "stdout", output), \
                        patch.object(install_app, "prepare_saved_data", return_value=plan), \
                        patch.object(install_app, "run_both", return_value=0) as both:
                    self.assertEqual(install_app.launch(self.root / "app", saved_data="NQ",
                                                       captured_session=self.capture, no_browser=True), 0)
                text = output.getvalue()
                self.assertIn("2026-10-16T13:34:58Z to 2026-10-16T13:40:00Z", text)
                self.assertIn(f"{plan['event_count']:,} events", text)
                note = both.call_args.kwargs["source_note"]
                self.assertIn(expected, note)
                if policy == "fast_load":
                    self.assertNotIn("60x", note)
                terminal, wind = both.call_args.args
                self.assertEqual(terminal[terminal.index("--replay-clock") + 1], clock)
                self.assertEqual(wind[wind.index("--checkpoint") + 1], plan["checkpoint_path"])

    def test_unknown_playback_policy_stops_before_remembering_or_launching(self):
        plan = {**self.plan, "replay_policy": "unknown"}
        with patch.object(install_app, "prepare_saved_data", return_value=plan), \
                patch.object(install_app, "run_both") as both:
            with self.assertRaisesRegex(ValueError, "unsupported playback policy"):
                self.launch(saved_data="NQ", captured_session=self.capture)
        both.assert_not_called()
        self.assertFalse((self.research / install_app.SAVED_DATA).exists())

    def test_older_saved_helper_without_policy_keeps_short_replay_disclosure(self):
        plan = dict(self.plan)
        plan.pop("replay_policy")
        self.assertIn("at 60x", install_app.saved_source_note(plan))

    def test_first_use_menu_selects_nq_and_registers_provided_capture(self):
        with patch.object(install_app.sys, "stdin", TTYInput(f"4\n2\n'{self.capture}'\n")), \
                patch.object(install_app.sys, "stdout", TTYInput()), \
                patch.object(install_app, "prepare_saved_data", return_value=self.plan) as prepare, \
                patch.object(install_app, "run_both", return_value=0):
            self.assertEqual(install_app.launch(self.root / "app", choose=True), 0)
        self.assertEqual(prepare.call_args.args[2:4], (self.capture, "NQ"))
        self.assertIn("NQ", install_app.saved_sources(self.research)["sessions"])

    def test_saved_mode_cannot_fall_back_when_preparation_fails(self):
        with patch.object(install_app, "prepare_saved_data", side_effect=ValueError("invalid capture")), \
                patch.object(install_app, "run_both") as both, patch.object(install_app.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "invalid capture"):
                self.launch(saved_data="NQ", captured_session=self.capture)
        both.assert_not_called()
        run.assert_not_called()
        self.assertFalse((self.research / install_app.SAVED_DATA).exists())

    def test_legacy_wheel_and_noninteractive_saved_launch_fail_before_preparation(self):
        with patch.object(install_app, "prepare_saved_data") as prepare:
            del self.receipt["active"]["payload_sha256"]["gex_terminal/saved_workspace.py"]
            with self.assertRaisesRegex(ValueError, "no saved-data starter"):
                self.launch(saved_data="ES", captured_session=self.capture)
            self.receipt["active"]["payload_sha256"]["gex_terminal/saved_workspace.py"] = "2" * 64
            with patch.object(install_app.sys, "stdin", io.StringIO()), self.assertRaisesRegex(ValueError, "interactive terminal"):
                install_app.launch(self.root / "app", saved_data="ES", captured_session=self.capture)
        prepare.assert_not_called()

    def test_cancelled_capture_prompt_does_not_prepare_or_launch(self):
        with patch.object(install_app, "prepare_saved_data") as prepare, patch.object(install_app, "run_both") as both:
            self.assertEqual(self.launch(saved_data="NQ"), 0)
        prepare.assert_not_called()
        both.assert_not_called()

    def test_supplied_capture_cannot_be_silently_ignored_by_chooser(self):
        with patch.object(install_app.sys, "stdin", TTYInput("3\n")), \
                patch.object(install_app.sys, "stdout", TTYInput()), \
                patch.object(install_app, "run_both") as both, \
                self.assertRaisesRegex(ValueError, "no synthetic workspace"):
            install_app.launch(self.root / "app", choose=True, captured_session=self.capture)
        both.assert_not_called()

    def test_bad_registry_and_unrelated_capture_argument_fail_closed(self):
        path = self.research / install_app.SAVED_DATA
        path.symlink_to(self.capture)
        with self.assertRaises(ValueError):
            self.launch(saved_data="NQ")
        path.unlink()
        path.write_text(json.dumps({"schema": install_app.SAVED_SCHEMA, "sessions": {"ES": {"capture_path": "relative"}}}))
        with self.assertRaises(ValueError):
            install_app.saved_sources(self.research)
        with self.assertRaisesRegex(ValueError, "Use --captured-session"):
            self.launch(captured_session=self.capture)

    def test_preparation_has_no_inherited_provider_settings_and_rejects_changed_source(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps(self.plan), "")
        with patch.dict(os.environ, {"GEX_DATA_MODE": "live", "DATABENTO_API_KEY": "private-test-key"}), \
                patch.object(install_app.subprocess, "run", return_value=completed) as run:
            plan = install_app.prepare_saved_data(self.root / "env", self.research, self.capture, "NQ", self.root)
            self.assertEqual(plan, self.plan)
            self.assertNotIn("GEX_DATA_MODE", run.call_args.kwargs["env"])
            self.assertNotIn("DATABENTO_API_KEY", run.call_args.kwargs["env"])
            self.assertIn("restrict_network_to_loopback", run.call_args.args[0][3])
            with self.assertRaisesRegex(ValueError, "Remembered saved data changed"):
                install_app.prepare_saved_data(self.root / "env", self.research, self.capture, "NQ", self.root,
                                               expected_sha256="0" * 64)


CHILD = r'''
import json, os, signal, socket, sys, time
from pathlib import Path
role, mode = sys.argv[1:]
root = Path.cwd()
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
def save(name, data):
    target = root / name
    scratch = target.with_suffix('.tmp')
    scratch.write_text(json.dumps(data))
    scratch.replace(target)
def wait_for(name):
    deadline = time.monotonic() + 15
    while not (root / name).exists():
        if time.monotonic() > deadline:
            raise RuntimeError('test child timed out')
        time.sleep(.01)
if role == 'wind':
    if mode == 'ignore-signals':
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        server.listen()
        save('wind.json', {'pid': os.getpid(), 'port': server.getsockname()[1]})
        if mode == 'startup-failure':
            sys.exit(17)
        if mode == 'startup-timeout':
            time.sleep(30)
        if mode == 'noisy':
            sys.stdout.write(('startup diagnostic ' + 'x' * 1000 + '\n') * 1024)
        print('http://127.0.0.1:%s/#cap=%s' % (server.getsockname()[1], 'a' * 64), flush=True)
        if mode == 'crash':
            wait_for('terminal.json')
            sys.exit(23)
        if mode == 'noisy':
            sys.stdout.write(('ongoing diagnostic ' + 'y' * 1000 + '\n') * 4096)
            sys.stdout.flush()
            save('noise-drained.json', True)
        while True:
            time.sleep(.02)
else:
    wind = json.loads((root / 'wind.json').read_text())
    with socket.create_connection(('127.0.0.1', wind['port']), timeout=2):
        pass
    save('terminal.json', {'pid': os.getpid(), 'stdin_tty':sys.stdin.isatty(), 'stdout_tty':sys.stdout.isatty()})
    if mode == 'noisy':
        wait_for('noise-drained.json')
    if mode in ('normal', 'noisy', 'ignore-signals'):
        sys.exit(7)
    while True:
        time.sleep(.02)
'''


class StarterLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gex starter child ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.child = self.root / "inert child.py"
        self.child.write_text(CHILD)

    def commands(self, mode):
        return ([sys.executable, "-I", str(self.child), "terminal", mode],
                [sys.executable, "-I", str(self.child), "wind", mode])

    def read_marker(self, name, timeout=8):
        deadline = time.monotonic() + timeout
        path = self.root / name
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(path.exists(), f"Child never reached {name}")
        return json.loads(path.read_text())

    def assert_children_reaped(self):
        for name in ("wind.json", "terminal.json"):
            if (self.root / name).exists():
                pid = json.loads((self.root / name).read_text())["pid"]
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                # Contain even a failing regression: never leave a test child.
                os.kill(pid, signal.SIGKILL)
                self.fail(f"Owned child {name} ({pid}) was left running or unreaped")

    def run_both(self, mode, *, startup_timeout=3):
        terminal, wind = self.commands(mode)
        handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return install_app.run_both(terminal, wind, cwd=self.root,
                                            no_browser=True, startup_timeout=startup_timeout)
        finally:
            self.assertEqual({s: signal.getsignal(s) for s in handlers}, handlers)

    def test_terminal_exit_returns_its_status_and_preserves_independent_server(self):
        independent = subprocess.Popen([sys.executable, "-I", "-c",
            "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); time.sleep(30)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertEqual(self.run_both("normal"), 7)
            self.assertTrue((self.root / "terminal.json").is_file())
            self.assertIsNone(independent.poll())
            self.assert_children_reaped()
        finally:
            independent.kill()
            independent.wait(timeout=5)

    def test_wind_startup_failure_and_timeout_never_start_terminal(self):
        for mode in ("startup-failure", "startup-timeout"):
            with self.subTest(mode=mode):
                with self.assertRaises(RuntimeError):
                    self.run_both(mode, startup_timeout=.3)
                self.assertFalse((self.root / "terminal.json").exists())
                self.assert_children_reaped()
                (self.root / "wind.json").unlink()

    def test_wind_failure_after_readiness_stops_terminal(self):
        with self.assertRaises(RuntimeError):
            self.run_both("crash")
        self.assertTrue((self.root / "terminal.json").exists())
        self.assert_children_reaped()

    def test_terminal_creation_failure_reaps_ready_wind(self):
        _, wind = self.commands("active")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(OSError):
            install_app.run_both([str(self.root / "missing terminal executable")], wind,
                                 cwd=self.root, no_browser=True, startup_timeout=3)
        self.assertFalse((self.root / "terminal.json").exists())
        self.assert_children_reaped()

    def test_browser_failure_does_not_start_terminal_and_reaps_ready_wind(self):
        terminal, wind = self.commands("normal")
        for failure in (subprocess.TimeoutExpired("browser", 5),
                        subprocess.CompletedProcess(["browser"], 1)):
            with self.subTest(failure=type(failure).__name__):
                options = ({"side_effect": failure} if isinstance(failure, Exception)
                           else {"return_value": failure})
                with patch.object(install_app.subprocess, "run", **options), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    install_app.run_both(terminal, wind, cwd=self.root, startup_timeout=3)
                self.assertFalse((self.root / "terminal.json").exists())
                self.assert_children_reaped()
                (self.root / "wind.json").unlink()

    def test_signal_during_failed_browser_open_keeps_interrupt_exit_status(self):
        terminal, wind = self.commands("normal")
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum):
                def interrupted_browser(_url):
                    os.kill(os.getpid(), signum)
                    return False
                with patch.object(install_app, "open_browser", side_effect=interrupted_browser), \
                        contextlib.redirect_stdout(io.StringIO()):
                    status = install_app.run_both(terminal, wind, cwd=self.root, startup_timeout=3)
                self.assertEqual(status, 128 + signum)
                self.assertFalse((self.root / "terminal.json").exists())
                self.assert_children_reaped()
                (self.root / "wind.json").unlink()

    def test_noisy_wind_output_is_drained_before_and_after_terminal_starts(self):
        self.assertEqual(self.run_both("noisy"), 7)
        self.assertTrue((self.root / "noise-drained.json").exists())
        self.assert_children_reaped()

    def test_cleanup_escalates_when_owned_child_ignores_interrupt_and_terminate(self):
        before = time.monotonic()
        self.assertEqual(self.run_both("ignore-signals"), 7)
        self.assertLess(time.monotonic() - before, 12)
        self.assert_children_reaped()

    def test_signals_during_startup_and_active_session_reap_owned_children(self):
        driver = self.root / "supervisor.py"
        driver.write_text(
            "import pathlib,sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
            "from scripts.install_app import run_both\n"
            "root=pathlib.Path(__file__).parent\n"
            "cmd=[sys.executable,'-I',str(root/'inert child.py')]\n"
            "raise SystemExit(run_both(cmd+['terminal',sys.argv[1]],cmd+['wind',sys.argv[1]],cwd=root,no_browser=True,startup_timeout=10))\n"
        )
        for mode, marker in (("startup-timeout", "wind.json"), ("active", "terminal.json")):
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                with self.subTest(mode=mode, signal=signum):
                    process = subprocess.Popen([sys.executable, "-I", str(driver), mode],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        self.read_marker(marker)
                        process.send_signal(signum)
                        stdout, stderr = process.communicate(timeout=12)
                        self.assertNotEqual(process.returncode, 0, (stdout, stderr))
                        self.assert_children_reaped()
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate(timeout=5)
                        for name in ("wind.json", "terminal.json"):
                            (self.root / name).unlink(missing_ok=True)


class StarterShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="gex starter's install ")
        cls.root = Path(cls.temporary.name).resolve()
        cls.target = cls.root / "GEX App"
        cls.research = cls.root / "GEX App Research"
        wheelhouse = cls.root / "empty wheels"
        wheelhouse.mkdir()
        cli = CLI.replace('if "doctor" in arguments:',
                          'if "wind-tunnel" in arguments:\n    print("synthetic wind")\nelif "doctor" in arguments:')
        wheel = make_wheel(cls.root, version="0.6.0", wind_tunnel=True, cli=cli)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.receipt = install_app.install(wheel, install_app.digest(wheel), SOURCE,
                                              cls.target, wheelhouse=wheelhouse)
        cls.caller = cls.root / "unrelated caller"
        cls.caller.mkdir()
        (cls.caller / ".env").write_text("GEX_DATA_MODE=live\n")
        (cls.research / ".env").write_text("GEX_DATA_MODE=live\n")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_shortcut(self, name, *args, choice=None):
        master, slave = pty.openpty()
        process = None
        output = bytearray()
        try:
            process = subprocess.Popen([str(self.target / name), *args], cwd=self.caller,
                                       stdin=slave, stdout=slave, stderr=slave,
                                       env={**os.environ, "GEX_DATA_MODE":"live", "DATABENTO_API_KEY":"must-not-leak"})
            if choice is not None:
                os.write(master, choice)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    output.extend(os.read(master, 65536))
                if process.poll() is not None:
                    while select.select([master], [], [], .05)[0]:
                        output.extend(os.read(master, 65536))
                    return process.returncode, output.decode(errors="replace")
            self.fail("Shortcut did not settle after explicit input")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(master)
            os.close(slave)

    def test_new_starter_routes_explicit_choices_and_cancel(self):
        for choice, expected in ((b"1\n", "synthetic terminal"), (b"2\n", "synthetic wind"),
                                 (b"q\n", None), (b"\n", None), (b"\x04", None)):
            with self.subTest(choice=choice):
                status, output = self.run_shortcut("Start GEX.command", choice=choice)
                self.assertEqual(status, 0, output)
                self.assertIn("Both", output)
                if expected:
                    self.assertIn(expected, output)
                else:
                    self.assertNotIn("synthetic terminal", output)
                    self.assertNotIn("synthetic wind", output)

    def test_direct_shortcuts_and_explicit_arguments_do_not_prompt(self):
        for name, args, expected in (("Start Terminal.command", (), "synthetic terminal"),
                                     ("run-gex", (), "synthetic terminal"),
                                     ("Start GEX.command", ("--doctor",), "gex-terminal.doctor.v1"),
                                     ("Start Wind Tunnel.command", ("--no-browser",), "synthetic wind")):
            with self.subTest(name=name, args=args):
                status, output = self.run_shortcut(name, *args)
                self.assertEqual(status, 0, output)
                self.assertIn(expected, output)
                self.assertNotIn("Both", output)

    def test_explicit_chooser_and_both_reject_noninteractive_invocation(self):
        for flag in ("--choose", "--both"):
            result = subprocess.run([sys.executable, "-I", str(self.target / "launcher.py"),
                                     "--launch", "--target", str(self.target), flag, "--no-browser"],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("synthetic terminal", result.stdout)
            self.assertNotIn("synthetic wind", result.stdout)
        direct = subprocess.run([str(self.target / "Start GEX.command")], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(direct.returncode, 0)
        self.assertNotIn("synthetic terminal", direct.stdout)
        self.assertNotIn("synthetic wind", direct.stdout)


if __name__ == "__main__":
    unittest.main()

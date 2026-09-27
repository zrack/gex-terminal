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

import hashlib
import json
import os
from pathlib import Path
import pty
import select
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.build_app_bundle import build_bundle


class AppBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gex bundle ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wheel = self.root / "gex_terminal-0.5.0-py3-none-any.whl"
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr("gex_terminal/cli.py", "# synthetic wheel for bundle-only tests")
        self.installer = self.root / "install_app.py"
        self.installer.write_text("# inert setup test")
        self.installer_patch = patch("scripts.build_app_bundle.INSTALLER", self.installer)
        self.installer_patch.start()
        self.addCleanup(self.installer_patch.stop)

    def test_new_bundle_has_exact_bytes_identity_and_valid_quoted_launcher(self):
        output = build_bundle(self.wheel, self.root / "User's GEX folder", "a" * 40)
        manifest = json.loads((output / "bundle.json").read_text())
        self.assertEqual(manifest["wheel_sha256"], hashlib.sha256(self.wheel.read_bytes()).hexdigest())
        for name, record in manifest["files"].items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), record["sha256"])
        self.assertFalse((output / "INCOMPLETE").exists())
        self.assertFalse(manifest["dependencies_included"])
        subprocess.run(["sh", "-n", str(output / "Install.command")], check=True)
        self.assertTrue((output / "Install.command").stat().st_mode & 0o100)

    def test_existing_handoff_is_never_overwritten(self):
        output = self.root / "existing"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("important")
        with self.assertRaises(FileExistsError):
            build_bundle(self.wheel, output, "a" * 40)
        self.assertEqual(marker.read_text(), "important")
        self.assertEqual(list(output.iterdir()), [marker])

    def test_wind_tunnel_bundle_explains_both_launchers(self):
        with zipfile.ZipFile(self.wheel, "a") as archive:
            archive.writestr("gex_terminal/wind_tunnel_cli.py", "# bundled local browser entry")
        output = build_bundle(self.wheel, self.root / "wind", "b" * 40)
        instructions = (output / "START HERE.txt").read_text()
        self.assertIn("Start Wind Tunnel.command", instructions)
        self.assertIn("GEX App Research/wind-tunnel", instructions)
        self.assertIn("Control-C", instructions)
        subprocess.run(["sh", "-n", str(output / "Install.command")], check=True)

    def test_setup_wrapper_passes_paths_with_spaces_and_apostrophes_intact(self):
        self.installer.write_text(
            "import json, pathlib, sys\n"
            "pathlib.Path(__file__).with_name('invocation.json').write_text(json.dumps(sys.argv[1:]))\n"
        )
        output = build_bundle(self.wheel, self.root / "User's GEX folder", "a" * 40)
        bin_dir = self.root / "test-bin"
        bin_dir.mkdir()
        interpreter = bin_dir / "python3"
        interpreter.write_text(
            '#!/bin/sh\nif [ "$2" = "-c" ]; then exit 0; fi\n'
            f'exec {shlex.quote(sys.executable)} "$@"\n'
        )
        interpreter.chmod(0o755)
        # The selected supported interpreter must win over another available
        # minor, including the runner's system Python in a hosted matrix.
        alternate = bin_dir / "python3.12"
        alternate.write_text('#!/bin/sh\nif [ "$2" = "-c" ]; then exit 0; fi\nexit 77\n')
        alternate.chmod(0o755)
        subprocess.run(["sh", str(output / "Install.command")],
                       input="", text=True, capture_output=True, check=True,
                       env={**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        args = json.loads((output / "invocation.json").read_text())
        self.assertEqual(args[args.index("--wheel") + 1], str(output / self.wheel.name))
        self.assertEqual(args[args.index("--target") + 1], str(output / "GEX App"))

    def test_interactive_update_does_not_execute_unlisted_wind_launcher(self):
        # Model the setup helper's successful return for an existing installation
        # whose completed receipt still owns only the original three launchers.
        self.installer.write_text(
            "import json, pathlib, sys\n"
            "root = pathlib.Path(__file__).parent\n"
            "receipt = json.loads((root / 'GEX App' / 'installation.json').read_text())\n"
            "assert set(receipt['launcher_sha256']) == {'launcher.py', 'run-gex', 'Start GEX.command'}\n"
            "if '--launch' in sys.argv:\n"
            "    (root / 'trusted-launch.json').write_text(json.dumps(sys.argv[1:]))\n"
        )
        with zipfile.ZipFile(self.wheel, "a") as archive:
            archive.writestr("gex_terminal/wind_tunnel_cli.py", "# current bundle supports Wind Tunnel")
        output = build_bundle(self.wheel, self.root / "existing installation handoff", "c" * 40)
        target = output / "GEX App"
        target.mkdir()
        hashes = {}
        for name in ("launcher.py", "run-gex", "Start GEX.command"):
            data = b"# original launcher bytes\n"
            (target / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        original = json.dumps({"launcher_sha256": hashes}).encode()
        (target / "installation.json").write_bytes(original)
        unwanted = output / "unlisted-was-executed"
        unlisted = target / "Start Wind Tunnel.command"
        unlisted.write_text(f'#!/bin/sh\ntouch {shlex.quote(str(unwanted))}\n')
        unlisted.chmod(0o755)
        master, slave = pty.openpty()
        process = None
        captured = bytearray()
        try:
            process = subprocess.Popen(["sh", str(output / "Install.command")],
                                       stdin=slave, stdout=slave, stderr=slave,
                                       env={**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]})
            # Drain while the slave is open: macOS may discard unread PTY bytes
            # when its final slave descriptor closes.
            for _ in range(300):
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    captured.extend(os.read(master, 65536))
                if process.poll() is not None:
                    break
            self.assertEqual(process.poll(), 0, captured.decode(errors="replace"))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(master)
            os.close(slave)
        self.assertFalse(unwanted.exists())
        invocation = json.loads((output / "trusted-launch.json").read_text())
        self.assertEqual(invocation, ["--launch", "--wind-tunnel", "--target", str(target)])
        self.assertEqual((target / "installation.json").read_bytes(), original)
        self.assertTrue(unlisted.is_file())

    def test_invalid_inputs_do_not_create_destination(self):
        output = self.root / "not-created"
        with self.assertRaises(ValueError):
            build_bundle(self.wheel, output, "bad;source")
        self.assertFalse(output.exists())
        link = self.root / "linked.whl"
        link.symlink_to(self.wheel)
        with self.assertRaises(ValueError):
            build_bundle(link, output, "a" * 40)
        self.assertFalse(output.exists())

    def test_wheelhouse_copies_only_regular_wheels(self):
        wheelhouse = self.root / "wheelhouse"
        wheelhouse.mkdir()
        (wheelhouse / "dependency-1-py3-none-any.whl").write_bytes(b"dependency")
        (wheelhouse / "private.txt").write_text("do not package")
        output = build_bundle(self.wheel, self.root / "offline", "a" * 40, wheelhouse)
        manifest = json.loads((output / "bundle.json").read_text())
        self.assertTrue(manifest["dependencies_included"])
        self.assertEqual([p.name for p in (output / "wheelhouse").iterdir()], ["dependency-1-py3-none-any.whl"])
        self.assertIn('--wheelhouse "$BUNDLE_DIR/wheelhouse"', (output / "Install.command").read_text())


if __name__ == "__main__":
    unittest.main()

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import install_app


SOURCE = "1" * 40
CLI = r'''
import json,sys
from pathlib import Path
from . import config
arguments=sys.argv[1:]
if "doctor" in arguments:
    print(json.dumps({"schema":"gex-terminal.doctor.v1","execution":{"network_used":False}}))
elif "list-replays" in arguments:
    print("zero-gamma-flip")
elif "--export" in arguments:
    Path(arguments[arguments.index("--export")+1]).write_text(json.dumps({"schema":"gex-terminal.snapshot.v2","symbol":"ES","cwd":str(Path.cwd())}))
else:
    print("synthetic terminal")
'''
CONFIG = r'''
import os
from pathlib import Path
if "GEX_DATA_MODE" in os.environ or "DATABENTO_API_KEY" in os.environ:
    raise RuntimeError("ambient configuration leaked")
if Path(".env").exists():
    raise RuntimeError("working directory configuration leaked")
'''


def make_wheel(directory: Path, version="0.5.0", name="gex-terminal", broken=False) -> Path:
    path = directory / f"gex_terminal-{version}-py3-none-any.whl"
    metadata_dir = f"gex_terminal-{version}.dist-info"
    records = {
        "gex_terminal/__init__.py": f"__version__={version!r}\n",
        "gex_terminal/config.py": CONFIG,
        "gex_terminal/cli.py": "raise RuntimeError('deliberate synthetic failure')\n" if broken else CLI,
        f"{metadata_dir}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nRequires-Python: >=3.11\n",
        f"{metadata_dir}/WHEEL": "Wheel-Version: 1.0\nGenerator: installer-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    records[f"{metadata_dir}/RECORD"] = "".join(f"{filename},,\n" for filename in records)
    with zipfile.ZipFile(path, "w") as wheel:
        for filename, content in records.items():
            wheel.writestr(filename, content)
    return path


class InstallAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gex installer tests ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / "GEX App"
        self.research = self.root / "GEX App Research"
        self.wheelhouse = self.root / "empty wheelhouse"
        self.wheelhouse.mkdir()
        self.wheel = make_wheel(self.root)

    def install(self, wheel=None):
        wheel = wheel or self.wheel
        with contextlib.redirect_stdout(io.StringIO()):
            return install_app.install(wheel, install_app.digest(wheel), SOURCE, self.target,
                                       wheelhouse=self.wheelhouse)

    def test_validated_input_rejects_wrong_checksum_package_and_source_before_target_creation(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            install_app.install(self.wheel, "0" * 64, SOURCE, self.target)
        with self.assertRaisesRegex(ValueError, "Source commit"):
            install_app.install(self.wheel, install_app.digest(self.wheel), "main", self.target)
        wrong = make_wheel(self.root, version="0.6.0", name="other-package")
        with self.assertRaisesRegex(ValueError, "only gex-terminal"):
            self.install(wrong)
        corrupt = self.root / "gex_terminal-0.7.0-py3-none-any.whl"
        corrupt.write_bytes(b"not a wheel")
        with self.assertRaisesRegex(ValueError, "valid wheel"):
            self.install(corrupt)
        self.assertFalse(self.target.exists())

    def test_unowned_and_symlinked_targets_are_preserved(self):
        self.target.mkdir()
        sentinel = self.target / "keep.txt"
        sentinel.write_text("existing user data")
        with self.assertRaisesRegex(ValueError, "not owned"):
            self.install()
        self.assertEqual(sentinel.read_text(), "existing user data")
        alias = self.root / "alias"
        alias.symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            install_app.install(self.wheel, install_app.digest(self.wheel), SOURCE, alias)

    def test_research_inside_application_or_missing_wheelhouse_fails_without_installation(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            install_app.install(self.wheel, install_app.digest(self.wheel), SOURCE, self.target,
                                research_dir=self.target / "research")
        with self.assertRaisesRegex(ValueError, "Wheelhouse"):
            install_app.install(self.wheel, install_app.digest(self.wheel), SOURCE, self.target,
                                wheelhouse=self.root / "missing")
        self.assertFalse(self.target.exists())

    def test_real_isolated_install_reuse_launch_and_failed_update_preserve_research(self):
        self.research.mkdir()
        sentinel = self.research / "valuable.json"
        sentinel.write_text('{"keep":"all bytes"}\n')
        (self.research / ".env").write_text("GEX_DATA_MODE=live\n")
        initial_data = {path.name: path.read_bytes() for path in self.research.iterdir()}
        with patch.dict(os.environ, {"GEX_DATA_MODE": "live", "DATABENTO_API_KEY": "DO_NOT_PASS"}):
            receipt = self.install()
            self.assertFalse(receipt["reused"])
            self.assertEqual(receipt["active"]["wheel_sha256"], install_app.digest(self.wheel))
            self.assertEqual(receipt["active"]["source_commit"], SOURCE)
            self.assertEqual(receipt["active"]["verification"]["doctor"], "passed")
            active_before = (self.target / install_app.RECEIPT).read_bytes()
            launchers_before = {name: (self.target / name).read_bytes() for name in install_app.LAUNCH_FILES}
            with patch.object(install_app.venv, "EnvBuilder", side_effect=AssertionError("reuse created an environment")):
                reused = self.install()
            self.assertTrue(reused["reused"])
            self.assertEqual((self.target / install_app.RECEIPT).read_bytes(), active_before)
            installed_python = self.target / "environments" / receipt["active"]["environment"] / "bin/python"
            library = subprocess.run([str(installed_python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                     text=True, capture_output=True, check=True).stdout.strip()
            installed_config = Path(library) / "gex_terminal/config.py"
            original_config = installed_config.read_bytes()
            installed_config.write_bytes(original_config + b"\nraise RuntimeError('must not import altered application')\n")
            with patch.object(install_app.venv, "EnvBuilder", side_effect=AssertionError("reuse rebuilt an environment")):
                with self.assertRaisesRegex(ValueError, "payload differs"):
                    self.install()
            self.assertEqual((self.target / install_app.RECEIPT).read_bytes(), active_before)
            installed_config.write_bytes(original_config)
            caller = self.root / "unrelated caller"
            caller.mkdir()
            (caller / ".env").write_text("GEX_DATA_MODE=live\n")
            exported = self.root / "portable snapshot.json"
            for launcher in ("run-gex", "Start GEX.command"):
                result = subprocess.run([str(self.target / launcher), "--export", str(exported)],
                                        cwd=caller, env=os.environ.copy(), text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                snapshot = json.loads(exported.read_text())
                self.assertEqual(snapshot["symbol"], "ES")
                self.assertEqual(snapshot["cwd"], str(self.research))
            resize_request = b"\x1b[8;40;120t"
            for launcher, arguments, should_resize in (
                ("Start GEX.command", [], True),
                ("Start GEX.command", ["--doctor"], False),
                ("run-gex", [], False),
            ):
                master, slave = pty.openpty()
                try:
                    completed = subprocess.run(
                        [str(self.target / launcher), *arguments], cwd=caller,
                        stdin=slave, stdout=slave, stderr=slave, timeout=30,
                    )
                    output = b""
                    # Drain before closing our slave descriptor: Darwin can
                    # discard unread terminal output after the final close.
                    while select.select([master], [], [], 0.1)[0]:
                        try:
                            part = os.read(master, 65536)
                        except OSError:
                            break
                        if not part:
                            break
                        output += part
                    self.assertEqual(completed.returncode, 0, output.decode(errors="replace"))
                    self.assertEqual(resize_request in output, should_resize, output)
                finally:
                    os.close(slave)
                    os.close(master)
            noninteractive = subprocess.run(
                [str(self.target / "Start GEX.command")], cwd=caller,
                stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
            )
            self.assertEqual(noninteractive.returncode, 0, noninteractive.stderr)
            self.assertNotIn(resize_request, noninteractive.stdout)
            broken = make_wheel(self.root, version="0.6.0", broken=True)
            with self.assertRaisesRegex(RuntimeError, "Offline doctor"):
                self.install(broken)
            self.assertEqual((self.target / install_app.RECEIPT).read_bytes(), active_before)
            self.assertEqual({name: (self.target / name).read_bytes() for name in install_app.LAUNCH_FILES}, launchers_before)
            self.assertEqual({path.name: path.read_bytes() for path in self.research.iterdir()}, initial_data)
            old = subprocess.run([str(self.target / "run-gex"), "--doctor"], text=True, capture_output=True, timeout=30)
            self.assertEqual(old.returncode, 0, old.stderr)
            # A completed folder is validated even when the requested wheel is
            # different. Never reinterpret malformed records as a new install.
            receipt_path = self.target / install_app.RECEIPT
            for invalid in ({}, {**receipt, "schema": "unknown"}, {**receipt, "root": "/wrong/root"}):
                receipt_path.write_text(json.dumps(invalid))
                with self.subTest(invalid=invalid.get("schema")), self.assertRaisesRegex(ValueError, "receipt"):
                    self.install(broken)
                self.assertEqual(json.loads(receipt_path.read_text()), invalid)
                self.assertEqual({name: (self.target / name).read_bytes() for name in install_app.LAUNCH_FILES}, launchers_before)
            receipt_path.write_bytes(active_before)
            newer = make_wheel(self.root, version="0.7.0")
            original_write = install_app.atomic_write
            def fail_receipt(path, data, **options):
                if path.name == install_app.RECEIPT:
                    raise OSError("simulated receipt publication failure")
                return original_write(path, data, **options)
            with patch.object(install_app, "atomic_write", side_effect=fail_receipt):
                with self.assertRaisesRegex(OSError, "publication failure"):
                    self.install(newer)
            self.assertEqual(receipt_path.read_bytes(), active_before)
            self.assertEqual({name: (self.target / name).read_bytes() for name in install_app.LAUNCH_FILES}, launchers_before)
            updated = self.install(newer)
            self.assertNotEqual(updated["active"]["environment"], receipt["active"]["environment"])
            self.assertEqual(updated["previous"]["environment"], receipt["active"]["environment"])
            self.assertTrue(install_app.active_environment(self.target, receipt).is_dir())
            self.assertEqual({name: (self.target / name).read_bytes() for name in install_app.LAUNCH_FILES}, launchers_before)
            self.assertEqual({path.name: path.read_bytes() for path in self.research.iterdir()}, initial_data)

    def test_existing_customized_launcher_is_preserved(self):
        # Avoid a second real install: represent an owned installation whose
        # custom launcher must be rejected before any environment is touched.
        self.target.mkdir()
        (self.target / install_app.OWNER).write_text(json.dumps({"schema": install_app.SCHEMA, "root": str(self.target)}))
        receipt = {"schema": install_app.SCHEMA, "root": str(self.target), "research_dir": str(self.research),
                   "active": {"environment": "env-" + "1" * 12 + "-" + "2" * 12,
                              "version": "0.5.0", "wheel_sha256": "1" * 64, "source_commit": SOURCE,
                              "payload_sha256": {"gex_terminal/__init__.py": "1" * 64}},
                   "launcher_sha256": {"launcher.py": "0" * 64}}
        (self.target / "environments" / receipt["active"]["environment"]).mkdir(parents=True)
        (self.target / install_app.RECEIPT).write_text(json.dumps(receipt))
        custom = self.target / "launcher.py"
        custom.write_text("user-owned modification")
        with self.assertRaisesRegex(ValueError, "launcher has changed"):
            self.install()
        self.assertEqual(custom.read_text(), "user-owned modification")

    def test_incomplete_owned_state_with_launcher_is_preserved(self):
        self.target.mkdir()
        (self.target / install_app.OWNER).write_text(json.dumps({"schema": install_app.SCHEMA, "root": str(self.target)}))
        custom = self.target / "run-gex"
        custom.write_text("preserve incomplete launcher")
        with self.assertRaisesRegex(ValueError, "Incomplete installation"):
            self.install()
        self.assertEqual(custom.read_text(), "preserve incomplete launcher")


if __name__ == "__main__":
    unittest.main()

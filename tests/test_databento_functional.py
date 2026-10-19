"""Failure gates for the installed-application functional evidence harness."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_databento_functional import verify_installed_wheel


class InstalledFunctionalEvidenceTests(unittest.TestCase):
    def test_candidate_identity_checks_installed_source_and_packaged_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            package = directory / "gex_terminal"
            package.mkdir()
            (package / "__init__.py").write_text("candidate = True\n")
            (package / "example.json").write_text('{"synthetic": true}\n')
            wheel = directory / "candidate.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.write(package / "__init__.py", "gex_terminal/__init__.py")
                archive.write(package / "example.json", "gex_terminal/example.json")
            self.assertEqual(verify_installed_wheel(package, wheel)["package_members_verified"], 2)
            (package / "example.json").write_text('{"synthetic": false}\n')
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_installed_wheel(package, wheel)
            (package / "example.json").unlink()
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_installed_wheel(package, wheel)

    def test_wrong_or_unsafe_wheel_cannot_claim_application_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            wheel = directory / "wrong.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("another_package/__init__.py", "")
            with self.assertRaisesRegex(ValueError, "no application"):
                verify_installed_wheel(directory, wheel)
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("gex_terminal/../outside.py", "")
            with self.assertRaisesRegex(ValueError, "invalid wheel"):
                verify_installed_wheel(directory, wheel)

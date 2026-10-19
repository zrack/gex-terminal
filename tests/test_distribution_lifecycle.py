import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.verify_distribution_lifecycle import verify, wheel_version


class DistributionLifecycleTests(unittest.TestCase):
    def _wheel(self, root, version, name="gex-terminal"):
        path = root / f"gex_terminal-{version}-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                f"gex_terminal-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            )
        return path

    def test_wheel_identity_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(wheel_version(self._wheel(root, "0.5.0")), "0.5.0")
            with self.assertRaisesRegex(ValueError, "only gex-terminal"):
                wheel_version(self._wheel(root, "0.6.0", "unrelated"))

    def test_reversed_equal_and_prerelease_versions_fail_before_environment_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = self._wheel(root, "0.5.0")
            for candidate_version in ("0.4.0", "0.5.0", "0.5.0rc1"):
                candidate = self._wheel(root, candidate_version)
                with self.subTest(candidate=candidate_version), patch(
                    "scripts.verify_distribution_lifecycle.venv.EnvBuilder"
                ) as environment:
                    with self.assertRaisesRegex(ValueError, "newer than previous"):
                        verify(previous, candidate)
                    environment.assert_not_called()

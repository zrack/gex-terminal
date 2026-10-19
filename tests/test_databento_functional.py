"""Failure gates for the installed-application functional evidence harness."""

import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from scripts.verify_databento_functional import (expected_gex, expected_pricing_coverage,
                                                scenario, verify_installed_wheel, verify_report)


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


class FunctionalPricingPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_functional_oracle_prices_observed_iv_and_reconciles_unpriced_oi(self):
        from gex_terminal.databento_offline import replay_databento_records
        from tests.test_databento_offline import _config
        for root in ("ES", "NQ"):
            config = replace(_config(), symbol=root, symbols=(root,),
                             contract_multiplier=50 if root == "ES" else 20)
            for stage, records in scenario(root).items():
                with self.subTest(root=root, stage=stage):
                    report = await replay_databento_records(records, config=config)
                    verify_report(report, root, stage)
                    if stage == "rollover":
                        self.assertIsNone(report["snapshot"])
                        continue
                    coverage = report["snapshot"]["model"]["pricing_coverage"]
                    self.assertEqual(coverage["priced_quantity"], 11)
                    self.assertEqual(coverage["unpriced_quantity"],
                                     expected_pricing_coverage(stage)["unpriced_quantity"])
                    self.assertLess(abs(expected_gex(root, stage)), 200000)
                    # A verifier that silently loses the unavailable OI is not
                    # acceptable even when its priced GEX still agrees.
                    coverage["selected_quantity"] += 1
                    with self.assertRaises(AssertionError):
                        verify_report(report, root, stage)

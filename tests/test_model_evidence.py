import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.model_evidence import (
    build_model_evidence_report,
    write_model_evidence_report,
)


class ModelEvidenceTests(unittest.TestCase):
    def test_report_passes_deterministic_checks_without_claiming_predictive_validity(self):
        report = build_model_evidence_report()

        self.assertEqual(report["schema"], "gex-terminal.model-evidence.v1")
        self.assertTrue(report["result"]["passed"])
        self.assertEqual(report["evidence"]["numerical_validity"]["status"], "passed")
        self.assertEqual(
            report["evidence"]["predictive_market_validity"]["status"],
            "unmeasured",
        )

    def test_deterministic_evidence_is_repeatable(self):
        first = build_model_evidence_report()
        second = build_model_evidence_report()

        self.assertEqual(first["result"], second["result"])
        self.assertEqual(first["evidence"], second["evidence"])

    def test_writes_json_and_markdown_with_evidence_ceiling(self):
        report = build_model_evidence_report()

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            json_path = write_model_evidence_report(report, str(base / "evidence.json"))
            markdown_path = write_model_evidence_report(
                report,
                str(base / "evidence.md"),
            )

            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertTrue(loaded["result"]["passed"])
        self.assertEqual(
            loaded["evidence"]["predictive_market_validity"]["status"],
            "unmeasured",
        )
        self.assertIn("Model Evidence", markdown)
        self.assertIn("unmeasured", markdown.lower())


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from gex_terminal.fixture_validator import (
    format_fixture_validation_report,
    validate_fixture,
)
from gex_terminal.replay_catalog import bundled_replay_sessions


class FixtureValidatorTests(unittest.TestCase):
    def test_validates_bundled_replay_sessions(self):
        for session in bundled_replay_sessions():
            with self.subTest(session=session.name):
                report = validate_fixture(session.path)

                self.assertTrue(report.ok, format_fixture_validation_report(report))
                self.assertGreater(report.message_count, 0)

    def test_reports_invalid_json_and_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text(
                "\n".join((
                    '{"type":"underlying_tick","symbol":"ES","price":5943.25}',
                    '{"type":"options_volume_tick","strike":5950,"volume":100}',
                    '{"type":"underlying_tick",',
                )),
                encoding="utf-8",
            )

            report = validate_fixture(path)

        self.assertFalse(report.ok)
        self.assertEqual(len(report.issues), 2)
        rendered = format_fixture_validation_report(report)
        self.assertIn("FAILED", rendered)
        self.assertIn("line 2", rendered)


if __name__ == "__main__":
    unittest.main()

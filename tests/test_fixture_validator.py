import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.fixture_validator import (
    format_fixture_validation_report,
    validate_fixture,
)
from gex_terminal.replay_catalog import bundled_replay_sessions


class FixtureValidatorTests(unittest.TestCase):
    def test_explicit_unavailable_iv_preserves_a_valid_quantity_without_crashing(self):
        message = {
            "schema_version": 2, "type": "options_volume_tick", "provider": "databento",
            "contract_id": "synthetic-unpriced", "symbol": "ES", "strike": 6000,
            "option_type": "C", "expiry": "2026-08-20", "instrument_class": "futures_option",
            "volume_semantics": "incremental", "position_source": "trade_volume", "volume": 7,
            "pricing_model": "black_76", "iv": None, "iv_source": "unavailable",
            "iv_provenance": {"status": "missing_inversion_input"},
            "event_time": "2026-08-06T16:00:00Z",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unpriced.jsonl"
            path.write_text(json.dumps(message) + "\n")
            report = validate_fixture(path)
            self.assertTrue(report.ok, format_fixture_validation_report(report))
            self.assertEqual(report.option_ticks, 1)
            path.write_text(json.dumps({**message, "iv_source": "provider"}) + "\n")
            invalid = validate_fixture(path)
            self.assertFalse(invalid.ok)

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

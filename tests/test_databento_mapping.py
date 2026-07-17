import json
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.adapters.databento import (
    DATABENTO_SCHEMAS,
    DEFAULT_DATABENTO_DATASET,
    DatabentoAdapter,
    databento_option_parent_symbol,
)
from gex_terminal.market_data_adapter import (
    AdapterConfigurationError,
    validate_normalized_message,
)
from gex_terminal.fixture_validator import (
    format_fixture_validation_report,
    validate_fixture,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class DatabentoMappingTests(unittest.TestCase):
    def test_documents_expected_dataset_and_schemas(self):
        self.assertEqual(DEFAULT_DATABENTO_DATASET, "GLBX.MDP3")
        self.assertEqual(DATABENTO_SCHEMAS["definitions"], "definition")
        self.assertEqual(DATABENTO_SCHEMAS["option_trades"], "trades")
        self.assertEqual(DATABENTO_SCHEMAS["underlying_quotes"], "mbp-1")
        self.assertEqual(DATABENTO_SCHEMAS["open_interest"], "statistics")

    def test_option_parent_symbol(self):
        self.assertEqual(databento_option_parent_symbol("ES"), "ES.OPT")
        self.assertEqual(databento_option_parent_symbol("nq"), "NQ.OPT")
        self.assertEqual(databento_option_parent_symbol("ES.OPT"), "ES.OPT")

    def test_definition_records_build_option_metadata(self):
        payload = _load_fixture("databento_definition_records.json")
        metadata = [
            DatabentoAdapter._normalize_definition_record(record)
            for record in payload["records"]
        ]

        self.assertEqual(payload["dataset"], DEFAULT_DATABENTO_DATASET)
        self.assertEqual(payload["schema"], DATABENTO_SCHEMAS["definitions"])
        self.assertEqual(
            [item["option_type"] for item in metadata if item],
            ["C", "P", "C"],
        )
        self.assertEqual(metadata[0]["strike"], 5950.0)
        self.assertEqual(metadata[1]["expiry"], "2026-06-19")
        self.assertIsNone(metadata[3])

    def test_trades_normalize_to_option_volume_ticks(self):
        definitions = _load_fixture("databento_definition_records.json")
        trades = _load_fixture("databento_trade_records.json")
        metadata = {
            item["instrument_id"]: item
            for item in (
                DatabentoAdapter._normalize_definition_record(record)
                for record in definitions["records"]
            )
            if item
        }

        messages = [
            DatabentoAdapter._normalize_option_trade_record(record, metadata)
            for record in trades["records"]
        ]

        for message in messages:
            validate_normalized_message(message)

        self.assertEqual(
            messages,
            [
                {
                    "type": "options_volume_tick",
                    "strike": 5950.0,
                    "option_type": "C",
                    "volume": 42,
                    "expiry": "2026-06-19",
                },
                {
                    "type": "options_volume_tick",
                    "strike": 5900.0,
                    "option_type": "P",
                    "volume": 31,
                    "expiry": "2026-06-19",
                },
                {
                    "type": "options_volume_tick",
                    "strike": 6000.0,
                    "option_type": "C",
                    "volume": 24,
                    "expiry": "2026-06-19",
                },
            ],
        )

    def test_expected_normalized_jsonl_fixture_is_valid(self):
        path = FIXTURE_DIR / "databento_normalized_expected.jsonl"

        report = validate_fixture(path)

        self.assertTrue(report.ok, format_fixture_validation_report(report))
        self.assertEqual(report.underlying_ticks, 1)
        self.assertEqual(report.option_ticks, 3)
        self.assertEqual(report.strikes, {5900.0, 5950.0, 6000.0})

    def test_mbp1_underlying_quote_uses_mid_price(self):
        payload = _load_fixture("databento_underlying_mbp1_record.json")
        adapter = DatabentoAdapter(consumer=None, target_underlying="ES")

        message = adapter._normalize_underlying_quote(payload["record"])

        validate_normalized_message(message)
        self.assertEqual(
            message,
            {
                "type": "underlying_tick",
                "symbol": "ES",
                "price": 5943.25,
            },
        )

    def test_statistics_open_interest_extraction(self):
        payload = _load_fixture("databento_statistics_records.json")

        open_interest = DatabentoAdapter._open_interest_from_statistics(
            payload["records"][0]
        )

        self.assertEqual(open_interest, (9001001, 1200))

    def test_live_validation_still_requires_sdk_ingestion(self):
        with patch.dict("os.environ", {"DATABENTO_API_KEY": "db-test-key"}, clear=True):
            adapter = DatabentoAdapter(consumer=None)

            with self.assertRaises(AdapterConfigurationError) as exc:
                adapter.validate()

        self.assertIn("databento-python ingestion", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

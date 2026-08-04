import json
import unittest
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TradovateOptionChainFixtureTests(unittest.TestCase):
    def test_option_chain_fixture_exists_and_is_valid_json(self):
        path = FIXTURE_DIR / "tradovate_option_chain.json"
        self.assertTrue(path.exists(), f"Fixture missing: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["provider"], "tradovate")
        self.assertEqual(payload["schema"], "option_chain")
        self.assertIn("records", payload)
        self.assertGreater(len(payload["records"]), 0)

    def test_option_chain_records_have_required_fields(self):
        payload = json.loads(
            (FIXTURE_DIR / "tradovate_option_chain.json").read_text(encoding="utf-8")
        )
        required_fields = {
            "symbol",
            "strike",
            "expiration",
            "optionType",
            "volume",
            "impliedVolatility",
        }

        for record in payload["records"]:
            for field in required_fields:
                self.assertIn(
                    field,
                    record,
                    f"Record missing required field '{field}': {record}",
                )

    def test_option_chain_records_cover_es_and_nq(self):
        payload = json.loads(
            (FIXTURE_DIR / "tradovate_option_chain.json").read_text(encoding="utf-8")
        )
        symbols = {record["symbol"] for record in payload["records"]}

        self.assertIn("ES", symbols)
        self.assertIn("NQ", symbols)

    def test_option_chain_records_have_valid_option_types(self):
        payload = json.loads(
            (FIXTURE_DIR / "tradovate_option_chain.json").read_text(encoding="utf-8")
        )

        for record in payload["records"]:
            self.assertIn(
                record["optionType"],
                ("C", "P"),
                f"Invalid optionType '{record['optionType']}' for strike {record['strike']}",
            )

    def test_option_chain_fixture_contains_no_credentials(self):
        payload = json.loads(
            (FIXTURE_DIR / "tradovate_option_chain.json").read_text(encoding="utf-8")
        )
        serialized = json.dumps(payload)

        sensitive_patterns = [
            "accountId",
            "account_id",
            "token",
            "credential",
            "password",
            "secret",
            "apiKey",
            "api_key",
        ]

        for pattern in sensitive_patterns:
            self.assertNotIn(
                pattern,
                serialized,
                f"Sensitive field '{pattern}' found in fixture",
            )


if __name__ == "__main__":
    unittest.main()

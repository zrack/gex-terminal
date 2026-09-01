import asyncio
import io
import logging
import os
import subprocess
import sys
import unittest
from pathlib import Path

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.logging_config import configure_logging, resolve_log_level
from gex_terminal.redaction import REDACTED, redact_sensitive, redact_text


class RecursiveRedactionTests(unittest.TestCase):
    def test_redacts_nested_credentials_and_private_identifiers_without_mutation(self):
        payload = {
            "provider": "fixture",
            "api_key": "db-secret-value",
            "nested": [
                {
                    "accountId": "account-42",
                    "subscription_ids": ["subscription-17", "subscription-18"],
                    "subscription_status": "subscribed",
                }
            ],
            "licensed_payload": {"price": 5000.0},
        }

        result = redact_sensitive(payload)

        self.assertEqual(result["api_key"], REDACTED)
        self.assertEqual(result["nested"][0]["accountId"], REDACTED)
        self.assertEqual(result["nested"][0]["subscription_ids"], REDACTED)
        self.assertEqual(result["nested"][0]["subscription_status"], "subscribed")
        self.assertEqual(result["licensed_payload"], REDACTED)
        self.assertEqual(payload["api_key"], "db-secret-value")
        self.assertEqual(payload["nested"][0]["accountId"], "account-42")

    def test_redacts_secret_substrings_assignments_and_bearer_tokens(self):
        text = (
            'failure api_key="visible-key" account-id=acct-1 '
            "subscription_id=sub-2 Authorization: Bearer bearer-secret "
            "opaque=prefix-exact-secret-suffix"
        )

        result = redact_text(text, secrets=("exact-secret",))

        for forbidden in (
            "visible-key",
            "acct-1",
            "sub-2",
            "bearer-secret",
            "exact-secret",
        ):
            self.assertNotIn(forbidden, result)
        self.assertGreaterEqual(result.count(REDACTED), 5)

    def test_redacts_serialized_and_embedded_private_payloads_completely(self):
        serialized = redact_text(
            '{"licensed_payload":{"price":5000,"symbol":"ES"},"safe":"retained"}'
        )
        embedded = redact_text(
            "provider failed raw_payload=[1,2,3] after decode"
        )
        truncated = redact_text("provider failed raw_payload=[1,2,3")

        self.assertIn("retained", serialized)
        self.assertNotIn("5000", serialized)
        self.assertNotIn('"ES"', serialized)
        self.assertNotIn("1,2,3", embedded)
        self.assertIn("after decode", embedded)
        self.assertNotIn("1,2,3", truncated)
        self.assertEqual(redact_text(embedded), embedded)

    def test_marks_recursive_containers_without_recursing_forever(self):
        payload = []
        payload.append(payload)
        self.assertEqual(redact_sensitive(payload), ["[recursive]"])


class LoggingControlTests(unittest.TestCase):
    def test_defaults_to_warning_and_validates_environment_level(self):
        self.assertEqual(resolve_log_level(environ={}), "WARNING")
        self.assertEqual(resolve_log_level(environ={"GEX_LOG_LEVEL": "info"}), "INFO")
        self.assertEqual(resolve_log_level("debug", environ={}), "DEBUG")
        self.assertEqual(
            resolve_log_level("info", environ={"GEX_LOG_LEVEL": "trace"}), "INFO"
        )
        with self.assertRaisesRegex(ValueError, "must be one of"):
            resolve_log_level(environ={"GEX_LOG_LEVEL": "trace"})

    def test_cli_and_environment_log_levels_fail_closed(self):
        environment = dict(os.environ)
        environment["GEX_LOG_LEVEL"] = "trace"
        invalid_environment = subprocess.run(
            [sys.executable, "-m", "gex_terminal.cli", "list-replays"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(invalid_environment.returncode, 0)
        self.assertIn("must be one of", invalid_environment.stderr)

        environment.pop("GEX_LOG_LEVEL", None)
        invalid_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "gex_terminal.cli",
                "--log-level",
                "trace",
                "list-replays",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(invalid_cli.returncode, 0)
        self.assertIn("invalid choice", invalid_cli.stderr)

    def test_configured_handler_redacts_structured_and_embedded_values(self):
        stream = io.StringIO()
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            level = configure_logging(
                "INFO",
                environ={"DATABENTO_API_KEY": "environment-secret"},
                stream=stream,
            )
            logging.getLogger("gex-test").warning(
                "provider failure %s account_id=%s",
                {"apiKey": "nested-secret", "safe": "retained"},
                "account-7",
            )
            logging.getLogger("gex-test").warning(
                'quoted api_key="%s"', "quoted-secret"
            )
            logging.getLogger("gex-test").warning(
                "exception contained environment-secret"
            )
            logging.getLogger("gex-test").warning(
                "raw_payload=[1,2,3] safe-suffix"
            )
            try:
                raise RuntimeError(
                    "traceback carried api_key=environment-secret"
                )
            except RuntimeError:
                logging.getLogger("gex-test").exception("provider exception")
        finally:
            root.handlers.clear()
            root.handlers.extend(original_handlers)
            root.setLevel(original_level)

        output = stream.getvalue()
        self.assertEqual(level, "INFO")
        self.assertIn("retained", output)
        self.assertNotIn("nested-secret", output)
        self.assertNotIn("account-7", output)
        self.assertNotIn("quoted-secret", output)
        self.assertNotIn("environment-secret", output)
        self.assertIn("RuntimeError", output)
        self.assertNotIn("1,2,3", output)
        self.assertIn("safe-suffix", output)

    def test_consumer_never_logs_the_raw_malformed_payload(self):
        stream = io.StringIO()
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        try:
            configure_logging(
                "ERROR",
                environ={"DATABENTO_API_KEY": "payload-secret"},
                stream=stream,
            )
            consumer = StatefulGexConsumer(IntradayGexEngine())
            asyncio.run(
                consumer.update_market_state(
                    '{"type":"not-supported","api_key":"payload-secret"}'
                )
            )
        finally:
            root.handlers.clear()
            root.handlers.extend(original_handlers)
            root.setLevel(original_level)

        self.assertNotIn("payload-secret", stream.getvalue())


if __name__ == "__main__":
    unittest.main()

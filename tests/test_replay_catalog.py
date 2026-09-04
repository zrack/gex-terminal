import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.replay_catalog import (
    ReplaySession,
    bundled_replay_sessions,
    config_for_replay_session,
    replay_session_for_name,
)
from gex_terminal.session_store import load_session_records
from gex_terminal.demo_lab_receipt import inspect_portable_replay, load_portable_replay


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _config(*, symbol: str = "NQ", multiplier: int = 20) -> GexConfig:
    return GexConfig(
        symbol=symbol,
        symbols=(symbol, "ES", "SPX", "QQQ"),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=multiplier,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="unused.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


def _run_cli(
    *arguments: str,
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith("GEX_"):
            environment.pop(key)
    environment.update(environment_updates or {})
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT), existing_pythonpath) if part
    )
    return subprocess.run(
        [sys.executable, "-m", "gex_terminal.cli", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class ReplayCatalogTests(unittest.TestCase):
    def test_fifth_positional_argument_remains_public_reference(self):
        session = ReplaySession(
            "custom",
            "custom.jsonl",
            "Custom",
            "Custom session.",
            "public:custom",
        )

        self.assertEqual(session.public_ref, "public:custom")
        self.assertEqual(session.symbol, "ES")
        self.assertEqual(session.contract_multiplier, 50)

    def test_bundled_sessions_declare_catalog_identity(self):
        self.assertTrue(bundled_replay_sessions())
        for session in bundled_replay_sessions():
            with self.subTest(session=session.name):
                expected = ("NQ", 20) if session.name == "nq-research-loop" else ("ES", 50)
                self.assertEqual(
                    (session.symbol, session.contract_multiplier),
                    expected,
                )

    def test_nq_research_loop_has_exact_schema_v2_position_evidence(self):
        session = replay_session_for_name("nq-research-loop")
        observations = inspect_portable_replay(
            load_portable_replay(session.path),
            session=session,
        )

        self.assertEqual(session.symbol, "NQ")
        self.assertEqual(session.contract_multiplier, 20)
        self.assertTrue(session.research_loop)
        self.assertEqual(observations["normalized_schema_versions"], [2])
        self.assertEqual(
            observations["position_sources"],
            ["open_interest", "trade_volume"],
        )
        self.assertEqual(observations["direction_sources"], ["provider"])
        self.assertEqual(observations["missing_event_time_count"], 0)
        self.assertEqual(observations["missing_received_time_count"], 0)
        self.assertEqual(observations["missing_expiry_time_count"], 0)

    def test_catalog_identity_replaces_ambient_workflow_defaults(self):
        session = replay_session_for_name("trend-day")

        replay_config = config_for_replay_session(_config(), session)

        self.assertEqual(replay_config.symbol, "ES")
        self.assertEqual(replay_config.symbols[0], "ES")
        self.assertEqual(replay_config.contract_multiplier, 50)
        self.assertEqual(replay_config.data_mode, "replay")
        self.assertEqual(replay_config.data_provider, "replay")
        self.assertEqual(replay_config.replay_path, session.path)

    def test_custom_session_identity_is_preserved(self):
        session = ReplaySession(
            name="custom-nq",
            path="custom-nq.jsonl",
            label="Custom NQ",
            description="Caller-created NQ session.",
            symbol="NQ",
            contract_multiplier=20,
        )

        replay_config = config_for_replay_session(_config(symbol="ES", multiplier=50), session)

        self.assertEqual(replay_config.symbol, "NQ")
        self.assertEqual(replay_config.contract_multiplier, 20)
        self.assertEqual(replay_config.replay_path, "custom-nq.jsonl")

    def test_explicit_conflicts_fail_without_echoing_override_values(self):
        session = replay_session_for_name("trend-day")

        with self.assertRaises(ValueError) as symbol_error:
            config_for_replay_session(
                _config(),
                session,
                explicit_symbol="private-symbol-token",
            )
        with self.assertRaises(ValueError) as multiplier_error:
            config_for_replay_session(
                _config(),
                session,
                explicit_multiplier=987654321,
            )

        self.assertIn("requires symbol ES", str(symbol_error.exception))
        self.assertIn("explicit symbol override conflicts", str(symbol_error.exception))
        self.assertNotIn("private-symbol-token", str(symbol_error.exception).lower())
        self.assertIn("requires contract multiplier 50", str(multiplier_error.exception))
        self.assertIn("explicit multiplier override conflicts", str(multiplier_error.exception))
        self.assertNotIn("987654321", str(multiplier_error.exception))

    def test_invalid_catalog_multiplier_is_rejected_strictly(self):
        for invalid in (True, 20.5, "20"):
            with self.subTest(invalid=invalid):
                session = ReplaySession(
                    name="invalid",
                    path="invalid.jsonl",
                    label="Invalid",
                    description="Invalid multiplier.",
                    contract_multiplier=invalid,  # type: ignore[arg-type]
                )
                with self.assertRaisesRegex(ValueError, "invalid catalog multiplier"):
                    config_for_replay_session(_config(), session)

    def test_environment_defaults_do_not_mislabel_selected_bundled_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "snapshot.json"
            completed = _run_cli(
                "--replay-session",
                "trend-day",
                "--export",
                str(export_path),
                environment_updates={
                    "GEX_SYMBOL": "NQ",
                    "GEX_CONTRACT_MULTIPLIER": "20",
                },
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            snapshot = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["symbol"], "ES")
            self.assertEqual(snapshot["contract_multiplier"], 50)

    def test_explicit_cli_conflicts_fail_before_export(self):
        cases = (
            ("--symbol", "NQ", "explicit symbol override conflicts"),
            ("--multiplier", "20", "explicit multiplier override conflicts"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for index, (*override, expected) in enumerate(cases):
                with self.subTest(override=override):
                    export_path = Path(tmp) / f"conflict-{index}.json"
                    completed = _run_cli(
                        "--replay-session",
                        "trend-day",
                        *override,
                        "--export",
                        str(export_path),
                    )

                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn(expected, completed.stderr)
                    self.assertFalse(export_path.exists())

    def test_session_store_uses_selected_replay_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = _run_cli(
                "session-store",
                "save",
                "--replay-session",
                "trend-day",
                "--session-store-dir",
                tmp,
                environment_updates={
                    "GEX_SYMBOL": "NQ",
                    "GEX_CONTRACT_MULTIPLIER": "20",
                },
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            records = load_session_records(tmp)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["inputs"]["symbol"], "ES")
            self.assertEqual(records[0]["inputs"]["contract_multiplier"], 50)

    def test_non_es_seeded_demo_fails_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "demo.json"
            completed = _run_cli(
                "--demo",
                "--symbol",
                "NQ",
                "--export",
                str(export_path),
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Seeded demo data is available only for ES", completed.stderr)
            self.assertFalse(export_path.exists())


if __name__ == "__main__":
    unittest.main()

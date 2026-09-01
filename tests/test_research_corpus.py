import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.package_data import provider_fixture_path
from gex_terminal.capture_governance import capture_policy_identity
from gex_terminal.research_corpus import (
    initialize_corpus,
    register_corpus_item,
    verify_corpus,
)
from gex_terminal.session_capture import CapturedSessionWriter


def _capture_policy(*, research_use: str = "approved") -> dict:
    return {
        "schema": "gex-terminal.capture-policy.v1",
        "policy_id": f"test-capture-{research_use}",
        "rights": {
            "status": "licensed",
            "basis": "Test-only operator declaration",
            "redistributable": False,
        },
        "retention": {
            "mode": "time_limited",
            "days": 30,
            "storage": "temporary test directory",
            "owner": "test operator",
        },
        "redaction": {
            "status": "required",
            "profile": "normalized-test-v1",
            "review_before_sharing": True,
        },
        "research_use": {
            "status": research_use,
            "scope": "test-only corpus validation",
        },
    }


async def _write_captured_session(path: Path, policy: dict) -> None:
    writer = CapturedSessionWriter(
        path,
        source={
            "mode": "live",
            "provider": "databento",
            "symbol": "ES",
            "capture_policy": capture_policy_identity(policy),
        },
    )
    await writer.start()
    await writer.append({
        "schema_version": 2,
        "type": "underlying_tick",
        "provider": "databento",
        "symbol": "ES",
        "price": 6000.0,
        "event_time": "2026-08-06T16:00:00Z",
    })
    await writer.finalize()


class ResearchCorpusTests(unittest.TestCase):
    def test_rejects_timezone_naive_as_of(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "corpus"
            source = root / "source.json"
            source.write_text('{"value":1}\n', encoding="utf-8")
            metadata = json.loads(
                provider_fixture_path("corpus_item_metadata_example.json").read_text()
            )
            metadata["as_of"] = "2026-08-06T16:00:00"
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            initialize_corpus(corpus)
            with self.assertRaisesRegex(ValueError, "include a timezone"):
                register_corpus_item(corpus, source, metadata_path)

    def test_append_only_registration_and_verification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "corpus"
            source = root / "source.json"
            source.write_text('{"value":1}\n', encoding="utf-8")
            initialize_corpus(corpus, corpus_id="test-corpus")
            event = register_corpus_item(
                corpus,
                source,
                provider_fixture_path("corpus_item_metadata_example.json"),
            )
            report = verify_corpus(corpus)
            self.assertEqual(event["sequence"], 1)
            self.assertTrue(report["result"]["passed"])
            self.assertEqual(report["corpus"]["split_counts"]["test"], 1)
            self.assertEqual(report["result"]["predictive_validity"], "unmeasured")

    def test_duplicate_and_source_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "corpus"
            source = root / "source.json"
            source.write_text('{"value":1}\n', encoding="utf-8")
            metadata = root / "metadata.json"
            metadata.write_text(
                provider_fixture_path("corpus_item_metadata_example.json").read_text(),
                encoding="utf-8",
            )
            initialize_corpus(corpus)
            register_corpus_item(corpus, source, metadata)
            with self.assertRaisesRegex(ValueError, "already registered"):
                register_corpus_item(corpus, source, metadata)
            source.write_text('{"value":2}\n', encoding="utf-8")
            report = verify_corpus(corpus)
            self.assertFalse(report["result"]["passed"])
            self.assertIn("source_digest_changed", " ".join(report["errors"]))

    def test_event_chain_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus = Path(temp_dir) / "corpus"
            event_path = initialize_corpus(corpus)
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["payload"]["corpus_id"] = "tampered"
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = verify_corpus(corpus)
            self.assertFalse(report["chain"]["chain_valid"])

    def test_captured_session_requires_matching_approved_policy_and_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "corpus"
            source = root / "capture.gex-session.jsonl"
            policy = _capture_policy()
            asyncio.run(_write_captured_session(source, policy))
            policy_path = root / "capture-policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            metadata = json.loads(
                provider_fixture_path("corpus_item_metadata_example.json").read_text()
            )
            metadata.update({
                "dataset_id": "approved-live-capture",
                "source_kind": "captured_session",
                "rights": {
                    "status": "licensed",
                    "redistributable": False,
                    "notes": "Matches the capture policy",
                },
                "redaction_status": "verified",
            })
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            initialize_corpus(corpus)

            event = register_corpus_item(
                corpus,
                source,
                metadata_path,
                capture_policy_path=policy_path,
            )

            self.assertEqual(
                event["payload"]["capture_policy"],
                capture_policy_identity(policy),
            )
            self.assertEqual(
                event["payload"]["research_use"]["status"],
                "approved",
            )
            self.assertTrue(verify_corpus(corpus)["result"]["passed"])

    def test_prohibited_capture_policy_blocks_corpus_registration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "corpus"
            source = root / "capture.gex-session.jsonl"
            policy = _capture_policy(research_use="prohibited")
            asyncio.run(_write_captured_session(source, policy))
            policy_path = root / "capture-policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            metadata = json.loads(
                provider_fixture_path("corpus_item_metadata_example.json").read_text()
            )
            metadata.update({
                "dataset_id": "prohibited-live-capture",
                "source_kind": "captured_session",
                "rights": {
                    "status": "licensed",
                    "redistributable": False,
                    "notes": "Matches the capture policy",
                },
                "redaction_status": "verified",
            })
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            initialize_corpus(corpus)

            with self.assertRaisesRegex(ValueError, "prohibits research corpus"):
                register_corpus_item(
                    corpus,
                    source,
                    metadata_path,
                    capture_policy_path=policy_path,
                )

    def test_captured_session_cannot_register_without_full_policy_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "corpus"
            source = root / "capture.gex-session.jsonl"
            policy = _capture_policy()
            asyncio.run(_write_captured_session(source, policy))
            metadata = json.loads(
                provider_fixture_path("corpus_item_metadata_example.json").read_text()
            )
            metadata.update({
                "dataset_id": "unreviewed-live-capture",
                "source_kind": "captured_session",
                "rights": {
                    "status": "licensed",
                    "redistributable": False,
                    "notes": "Matches the capture policy",
                },
                "redaction_status": "verified",
            })
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            initialize_corpus(corpus)

            with self.assertRaisesRegex(ValueError, "requires --capture-policy"):
                register_corpus_item(corpus, source, metadata_path)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.package_data import provider_fixture_path
from gex_terminal.research_corpus import (
    initialize_corpus,
    register_corpus_item,
    verify_corpus,
)


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


if __name__ == "__main__":
    unittest.main()

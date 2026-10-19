import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import build_participant_delivery as delivery
from scripts import build_study_kit as study
from scripts import build_study_consent as consent
from unittest.mock import patch


class ParticipantDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.frozen = self.root / "frozen"
        self.frozen.mkdir()
        self.templates = self.root / "templates"
        self.templates.mkdir()
        self.pdf = self.root / "reviewed-blank.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nsynthetic test attachment; no PDF rendering dependency\n")
        self.output = self.root / "delivery"
        self.delivery_id = delivery.DELIVERY
        self.wheel = "gex_terminal-0.6.0-py3-none-any.whl"
        with zipfile.ZipFile(self.frozen / self.wheel, "w") as archive:
            archive.writestr("gex_terminal/__init__.py", "__version__ = '0.6.0'\n")
            archive.writestr("gex_terminal-0.6.0.dist-info/METADATA", "Name: gex-terminal\nVersion: 0.6.0\n")
        for name, text in {
            "requirements-lock.txt": "numpy==2.4.6\n",
            "participant-guide.md": "# Six tasks\nTask goals only.\n",
            "materials/LICENSE": "MIT test license\n",
            "moderator-guide.md": "PRIVATE ANSWERS MUST NOT BE INCLUDED\n",
            "fixture-answer-key.json": '{"private_answer": 42}\n',
            "protocol.json": '{"protocol_id":"guided-intake-v1"}\n',
        }.items():
            path = self.frozen / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for name in delivery.HELP:
            (self.frozen / f"materials/docs/{name}").parent.mkdir(parents=True, exist_ok=True)
            (self.frozen / f"materials/docs/{name}").write_text(
                "# User help\n[Kept](wind-tunnel.md#user-help) [Excluded](study-build.md)\n"
                "[Reference](https://example.invalid/docs)\n")
        for name in delivery.RECRUITER:
            (self.templates / name).write_text("Blank template: contact and dates must be filled privately.\n")
        (self.templates / "participant-start.txt").write_text(
            "Study: old-study\nDelivery: old-study-participant-v0\n"
            "Wait for the moderator. gex_terminal-0.6.0-py3-none-any.whl\n")
        fixtures = []
        for name, symbol, multiplier in (("zero-gamma-flip", "ES", 50), ("nq-research-loop", "NQ", 20)):
            relative = f"fixtures/{name}.gex-session.jsonl"
            path = self.frozen / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"synthetic_test_capture": true}\n')
            fixtures.append({"name": name, "symbol": symbol, "contract_multiplier": multiplier,
                             "capture_path": relative, "capture_sha256": delivery.sha(path),
                             "content_sha256": "d" * 64, "source_kind": "synthetic_fixture",
                             "source_ref": f"bundled:{name}", "redistributable": True,
                             "rights_status": "owned", "selected_checkpoint": 27,
                             "private_metadata": "moderator only"})
        self.parent = {
            "schema": "gex-terminal.study-kit.v1", "protocol_id": "guided-intake-v1",
            "study_id": delivery.COHORT, "source_commit": "a" * 40, "source_tree": "b" * 40,
            "application_version": "0.6.0",
            "build_environment": {"architecture": "arm64", "os": "Darwin", "os_version": "25.6.0",
                                  "python": "3.12.13", "private_path": "/Users/private",
                                  "tools": {"build": "1.5.0", "setuptools": "83.0.0", "wheel": "0.47.0", "secret": "private"}},
            "wheel": {"path": self.wheel, "sha256": delivery.sha(self.frozen / self.wheel), "secret": "internal"},
            "dependency_lock": {"path": "requirements-lock.txt", "sha256": delivery.sha(self.frozen / "requirements-lock.txt")},
            "fixtures": fixtures, "rehearsal": {"private": "/Users/moderator"},
        }
        self.freeze()

    def freeze(self):
        (self.frozen / "build-manifest.json").write_text(json.dumps(self.parent))
        study.write_inventory(self.frozen)

    def build(self):
        return delivery.build(self.frozen, self.output, self.pdf, self.delivery_id, templates=self.templates)

    def test_build_keeps_frozen_inputs_and_excludes_moderator_material(self):
        frozen_before = study.verify_inventory(self.frozen)
        report = self.build()
        self.assertEqual(report["participant_files"], 20)
        self.assertEqual(report["participant_sessions"], 0)
        self.assertEqual(study.verify_inventory(self.frozen), frozen_before)
        participant = self.output / "participant"
        self.assertEqual(delivery.verify_delivery(self.frozen, self.output)["status"], "passed")
        self.assertEqual(len(delivery.tree_files(self.output / "recruiter")), 9)
        source_csv = (self.templates / "session-plan.csv").read_bytes()
        self.assertNotIn(b"\r", source_csv)
        self.assertEqual((self.output / "recruiter/session-plan.csv").read_bytes(),
                         source_csv.replace(b"\n", b"\r\n"))
        self.assertEqual(study.verify_inventory(self.output), study.inventory(self.output))
        amendment = json.loads((self.output / "delivery-amendment.json").read_text())
        self.assertEqual(amendment["observations_at_amendment"], 0)
        for relative, digest in amendment["unchanged_files"].items():
            self.assertEqual((participant / relative).read_bytes(), (self.frozen / relative).read_bytes())
            self.assertEqual(delivery.sha(participant / relative), digest)
        self.assertFalse((participant / "moderator-guide.md").exists())
        self.assertFalse((participant / "fixture-answer-key.json").exists())
        for archive_name, folder in (("gex-participant-package.zip", participant), ("gex-organizer-pack.zip", self.output / "recruiter")):
            with zipfile.ZipFile(self.output / archive_name) as archive:
                self.assertEqual(set(archive.namelist()), delivery.tree_files(folder))
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), (folder / name).read_bytes())
            self.assertEqual(report["archives"][archive_name], delivery.sha(self.output / archive_name))

    def test_public_manifest_drops_answers_private_paths_and_unknown_metadata(self):
        self.build()
        public = json.loads((self.output / "participant/build-manifest.json").read_text())
        rendered = json.dumps(public)
        for value in ("private", "rehearsal", "selected_checkpoint", "secret", "/Users/"):
            self.assertNotIn(value, rendered)
        self.assertEqual(public["source_commit"], self.parent["source_commit"])
        self.assertEqual(public["wheel"]["sha256"], self.parent["wheel"]["sha256"])
        self.assertEqual({fixture["symbol"]: fixture["contract_multiplier"] for fixture in public["fixtures"]}, {"ES": 50, "NQ": 20})

    def test_help_amendment_preserves_allowed_links_and_task_guide_exactly(self):
        self.build()
        help_text = (self.output / "participant/materials/docs/first-run.md").read_text()
        self.assertIn("[Kept](wind-tunnel.md#user-help)", help_text)
        self.assertIn("[Reference](https://example.invalid/docs)", help_text)
        self.assertIn(" Excluded\n", help_text)
        self.assertNotIn("study-build.md", help_text)
        self.assertEqual((self.output / "participant/participant-guide.md").read_bytes(),
                         (self.frozen / "participant-guide.md").read_bytes())
        start = (self.output / "participant/START-HERE.txt").read_text()
        self.assertIn("Study: " + delivery.COHORT, start)
        self.assertIn("Delivery: " + delivery.DELIVERY, start)

    def test_no_overwrite_even_empty_or_failed_output(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(list(self.output.iterdir()), [])
        self.output.rmdir()
        self.build()
        before = study.verify_inventory(self.output)
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(study.verify_inventory(self.output), before)

    def test_parent_inventory_detects_changed_and_unrecorded_files(self):
        for mode in ("changed", "added"):
            with self.subTest(mode=mode):
                target = self.frozen / ("participant-guide.md" if mode == "changed" else "not-frozen.txt")
                previous = target.read_bytes() if target.exists() else None
                target.write_text("unexpected")
                with self.assertRaisesRegex(ValueError, "exact kit"):
                    self.build()
                self.assertFalse(self.output.exists())
                if previous is None:
                    target.unlink()
                else:
                    target.write_bytes(previous)

    def test_traversal_absolute_and_linked_sources_fail_closed(self):
        original = copy.deepcopy(self.parent)
        for path in ("../outside.whl", "/outside.whl", "C:\\outside.whl", "a/../outside.whl", "a//wheel.whl"):
            with self.subTest(path=path):
                self.parent["wheel"]["path"] = path
                self.freeze()
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())
        self.parent = original
        self.freeze()
        (self.frozen / "linked").symlink_to(self.frozen / "participant-guide.md")
        with self.assertRaisesRegex(ValueError, "links"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_rejects_unknown_protocol_unqualified_inputs_and_unsafe_wheel(self):
        original = copy.deepcopy(self.parent)
        for update in ("protocol", "rights", "hash", "wheel"):
            with self.subTest(update=update):
                self.parent = copy.deepcopy(original)
                if update == "protocol":
                    self.parent["protocol_id"] = "future-protocol"
                elif update == "rights":
                    self.parent["fixtures"][0]["redistributable"] = False
                elif update == "hash":
                    self.parent["wheel"]["sha256"] = "0" * 64
                else:
                    with zipfile.ZipFile(self.frozen / self.wheel, "a") as archive:
                        archive.writestr("gex_terminal/moderator-guide.md", "answers")
                    self.parent["wheel"]["sha256"] = delivery.sha(self.frozen / self.wheel)
                self.freeze()
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())

    def test_verifier_rejects_extra_changed_and_linked_participant_files(self):
        self.build()
        participant = self.output / "participant"
        extra = participant / "moderator-guide.md"
        extra.write_text("must never ship")
        study.write_inventory(participant)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            delivery.verify_delivery(self.frozen, self.output)
        extra.unlink()
        guide = participant / "participant-guide.md"
        original = guide.read_bytes()
        guide.write_text("changed tasks")
        study.write_inventory(participant)
        with self.assertRaisesRegex(ValueError, "exact frozen copy"):
            delivery.verify_delivery(self.frozen, self.output)
        guide.write_bytes(original)
        guide.unlink()
        guide.symlink_to(self.frozen / "participant-guide.md")
        with self.assertRaisesRegex(ValueError, "links"):
            delivery.verify_delivery(self.frozen, self.output)

    def test_escape_links_invalid_identifiers_and_unreviewable_pdf_are_rejected(self):
        for target in ("../../../../outside", "/outside", "file:///Users/private", "..%2f..%2f..%2foutside"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                delivery.render_help(f"[bad]({target})", "materials/docs/first-run.md")
        for value in ("../delivery", "OTHER", "wrong-parent-participant-v1", delivery.COHORT + "-participant-v2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                delivery.build(self.frozen, self.output, self.pdf, value, templates=self.templates)
        self.pdf.write_bytes(b"not a PDF")
        with self.assertRaisesRegex(ValueError, "blank consent PDF"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_output_inside_frozen_kit_or_templates_never_mutates_inputs(self):
        original = study.verify_inventory(self.frozen)
        for source in (self.frozen, self.templates):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "outside frozen inputs"):
                delivery.build(self.frozen, source / "new-delivery", self.pdf, self.delivery_id,
                               templates=self.templates)
            self.assertFalse((source / "new-delivery").exists())
        self.assertEqual(study.verify_inventory(self.frozen), original)

    def test_remaining_links_and_anchors_fail_closed(self):
        for link in ("wind-tunnel.md#missing-heading", "missing-file.md"):
            with self.subTest(link=link):
                path = self.frozen / "participant-guide.md"
                path.write_text(f"# Task goals\n[Help](materials/docs/{link})\n")
                self.freeze()
                with self.assertRaisesRegex(ValueError, "broken participant local"):
                    self.build()
                self.assertTrue(self.output.exists())  # Failed identity remains reserved.
                import shutil
                shutil.rmtree(self.output)

    def test_verifier_rejects_added_public_metadata_and_amendment_copy_omission(self):
        self.build()
        manifest_path = self.output / "participant/build-manifest.json"
        public = json.loads(manifest_path.read_text())
        public["private_answer"] = "must not leak"
        manifest_path.write_text(json.dumps(public))
        study.write_inventory(self.output / "participant")
        with self.assertRaisesRegex(ValueError, "public identity"):
            delivery.verify_delivery(self.frozen, self.output)
        public.pop("private_answer")
        manifest_path.write_text(json.dumps(public))
        study.write_inventory(self.output / "participant")
        amendment_path = self.output / "delivery-amendment.json"
        amendment = json.loads(amendment_path.read_text())
        amendment["unchanged_files"].pop("participant-guide.md")
        amendment_path.write_text(json.dumps(amendment))
        with self.assertRaisesRegex(ValueError, "declared exact materials"):
            delivery.verify_delivery(self.frozen, self.output)

    def test_consent_renderer_imports_no_pdf_dependencies_and_refuses_overwrite(self):
        existing = self.root / "existing.pdf"
        existing.write_bytes(b"already reviewed")
        with patch.object(consent, "_render") as render, self.assertRaises(FileExistsError):
            consent.build(existing)
        render.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"already reviewed")
        failed = self.root / "failed.pdf"
        with patch.object(consent, "_render", side_effect=RuntimeError("render failed")):
            with self.assertRaises(RuntimeError):
                consent.build(failed)
        self.assertTrue(failed.exists())


if __name__ == "__main__":
    unittest.main()

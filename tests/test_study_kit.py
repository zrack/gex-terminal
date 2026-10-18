import csv
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import build_study_kit as kit


ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOL_VERSIONS = {"build": "1.0.0", "setuptools": "80.0.0", "wheel": "0.45.0"}


class StudyKitTests(unittest.TestCase):
    def test_lock_requires_exact_unique_portable_versions(self):
        self.assertEqual(kit.pinned_requirements("NumPy==2.4.6\n# recorded runtime\naiohttp==3.14.3\n"),
                         "aiohttp==3.14.3\nnumpy==2.4.6\n")
        for value in ("", "numpy>=2", "-e /private/source", "numpy @ file:///private/a.whl",
                      "numpy==2.4.6\nNumPy==2.4.6", "numpy==not-a-version"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                kit.pinned_requirements(value)

    def test_inventory_detects_tampering_extras_and_nested_inventory_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "SHA256SUMS").write_text("also a kit file")
            (root / "wheel.whl").write_bytes(b"frozen")
            files = kit.write_inventory(root)
            self.assertIn("nested/SHA256SUMS", files)
            self.assertEqual(kit.verify_inventory(root), files)
            (root / "wheel.whl").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "exact kit"):
                kit.verify_inventory(root)
            (root / "wheel.whl").write_bytes(b"frozen")
            (root / "unrecorded").write_text("not frozen")
            with self.assertRaisesRegex(ValueError, "exact kit"):
                kit.verify_inventory(root)

    def test_inventory_rejects_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file").write_bytes(b"a")
            (root / "linked").symlink_to(root / "file")
            with self.assertRaisesRegex(ValueError, "links"):
                kit.write_inventory(root)

    def test_source_export_rejects_traversal_and_links(self):
        for name, kind in (("../outside", tarfile.REGTYPE), ("/outside", tarfile.REGTYPE),
                           ("linked", tarfile.SYMTYPE), ("fifo", tarfile.FIFOTYPE)):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w") as archive:
                info = tarfile.TarInfo(name)
                info.type = kind
                archive.addfile(info)
            with tempfile.TemporaryDirectory() as directory, self.subTest(name=name, kind=kind):
                with self.assertRaises(ValueError):
                    kit.safe_export(raw.getvalue(), Path(directory))

    def test_rehearsal_requires_exact_identity_and_zero_participants(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "execution.json"
            report = {"schema": "gex-terminal.study-rehearsal.v1", "source_commit": "a" * 40,
                      "wheel_sha256": "b" * 64, "participant_sessions": 0,
                      "checks": [{"name": "fresh server", "status": "passed"}]}
            path.write_text(json.dumps(report))
            self.assertEqual(kit.rehearsal_record(path, "a" * 40, "b" * 64), report)
            for update in ({"source_commit": "c" * 40}, {"wheel_sha256": "d" * 64},
                           {"participant_sessions": 1}, {"participant_sessions": False},
                           {"checks": []}, {"checks": [{"name": "fresh server", "status": "probably"}]}):
                with self.subTest(update=update), self.assertRaises(ValueError):
                    path.write_text(json.dumps({**report, **update}))
                    kit.rehearsal_record(path, "a" * 40, "b" * 64)

    def test_frozen_protocol_and_blank_scorecard_have_matching_task_ids(self):
        protocol = json.loads((ROOT / "docs/study-kit/protocol.json").read_text())
        rows = list(csv.DictReader((ROOT / "docs/study-kit/scorecard.csv").read_text().splitlines()))
        self.assertEqual(tuple(task["id"] for task in protocol["tasks"]), kit.TASK_IDS)
        self.assertEqual(tuple(row["task_id"] for row in rows), kit.TASK_IDS)
        self.assertEqual(protocol["participant_sessions"], 0)
        for row in rows:
            self.assertNotIn(None, row)
            self.assertTrue(all(not value for key, value in row.items() if key != "task_id"))

    def _repo(self, root):
        root.mkdir()
        for command in (["git", "init", "-q"], ["git", "config", "user.name", "Study test"],
                        ["git", "config", "user.email", "study-test@example.invalid"]):
            subprocess.run(command, cwd=root, check=True, capture_output=True)
        (root / "pyproject.toml").write_text('[project]\nname="gex-terminal"\nversion="0.6.0"\n')
        for name in ("README.md", "LICENSE", "CONTRIBUTING.md", "ROADMAP.md"):
            (root / name).write_text("frozen test source\n")
        templates = root / "docs/study-kit"
        templates.mkdir(parents=True)
        for name in ("participant-guide.md", "moderator-guide.md", "protocol.json", "scorecard.csv"):
            (templates / name).write_bytes((ROOT / "docs/study-kit" / name).read_bytes())
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "freeze study test"], cwd=root, check=True, capture_output=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def _wheel(self, export, destination, epoch, log):
        self.assertFalse((export / ".git").exists())
        self.assertIn("frozen test source", (export / "README.md").read_text())
        self.assertTrue(epoch.isdigit())
        destination.mkdir()
        wheel = destination / "gex_terminal-0.6.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            info = zipfile.ZipInfo("gex_terminal-0.6.0.dist-info/METADATA", (2026, 1, 1, 0, 0, 0))
            archive.writestr(info, "Metadata-Version: 2.1\nName: gex-terminal\nVersion: 0.6.0\nRequires-Dist: numpy==2.4.6\n")
        log.write_text("synthetic test build output\n")
        return wheel

    def _fixtures(self, export, destination):
        destination.mkdir()
        (destination / "test.gex-session.jsonl").write_bytes(b"synthetic test capture\n")
        return [{"name": "synthetic-test", "capture_path": "fixtures/test.gex-session.jsonl"}]

    def test_prepare_freezes_committed_source_exact_inventory_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            commit = self._repo(repo)
            (repo / "README.md").write_text("uncommitted private text must not enter kit")
            lock = root / "requirements.txt"
            lock.write_text("numpy==2.4.6\n")
            # These tests exercise packaging/inventory with a fake wheel build;
            # the corresponding build-tool metadata belongs to that fixture as
            # well, even when CI installs build backends only in isolation.
            with patch.object(kit, "_build_wheel", side_effect=self._wheel) as build, \
                    patch.object(kit, "_prepare_fixtures", side_effect=self._fixtures), \
                    patch.object(kit.importlib.metadata, "version", side_effect=BUILD_TOOL_VERSIONS.__getitem__) as versions:
                target = kit.prepare(repo, commit, "test-guided-cohort", lock, root / "study")
            self.assertEqual(build.call_count, 2)
            self.assertEqual(versions.call_args_list, [unittest.mock.call(name) for name in BUILD_TOOL_VERSIONS])
            manifest = json.loads((target / "build-manifest.json").read_text())
            self.assertEqual(manifest["source_commit"], commit)
            self.assertEqual(manifest["build_environment"]["tools"], BUILD_TOOL_VERSIONS)
            self.assertEqual(manifest["rehearsal"]["installation"], "not_run")
            self.assertEqual(manifest["rehearsal"]["participant_sessions"], 0)
            self.assertEqual((target / "materials/README.md").read_text(), "frozen test source\n")
            guide = (target / "participant-guide.md").read_text()
            self.assertNotIn("@WHEEL_FILENAME@", guide)
            self.assertIn("gex_terminal-0.6.0-py3-none-any.whl", guide)
            files = kit.verify_inventory(target)
            self.assertIn("build-manifest.json", files)
            with zipfile.ZipFile(target.with_suffix(".zip")) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {f"{target.name}/{name}" for name in [*files, "SHA256SUMS"]})
            self.assertIn(kit.sha256(target.with_suffix(".zip")),
                          target.with_suffix(".zip.sha256").read_text())
            with patch.object(kit, "_build_wheel") as second:
                with self.assertRaises(FileExistsError):
                    kit.prepare(repo, commit, "test-guided-cohort", lock, root / "study")
                second.assert_not_called()

    def test_prepare_rejects_nonreproducible_wheel_and_retains_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            commit = self._repo(repo)
            lock = root / "requirements.txt"
            lock.write_text("numpy==2.4.6\n")
            calls = []

            def differing(export, destination, epoch, log):
                wheel = self._wheel(export, destination, epoch, log)
                calls.append(wheel)
                if len(calls) == 2:
                    with wheel.open("ab") as stream:
                        stream.write(b"different build bytes")
                return wheel

            with patch.object(kit, "_build_wheel", side_effect=differing):
                with self.assertRaisesRegex(ValueError, "different wheel bytes"):
                    kit.prepare(repo, commit, "test-failed-cohort", lock, root / "study")
            self.assertTrue((root / "study/test-failed-cohort/PREPARATION_FAILED.txt").exists())
            self.assertFalse((root / "study/test-failed-cohort.zip").exists())

    def test_prepare_freezes_identity_bound_execution_record_without_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            commit = self._repo(repo)
            lock = root / "requirements.txt"
            lock.write_text("numpy==2.4.6\n")
            source = root / "preview-source"
            source.mkdir()
            (source / "README.md").write_text("frozen test source")
            wheel = self._wheel(source, root / "preview-wheel", "1", root / "preview.log")
            report = {"schema": "gex-terminal.study-rehearsal.v1", "source_commit": commit,
                      "wheel_sha256": kit.sha256(wheel), "participant_sessions": 0,
                      "checks": [{"name": "browser replay", "status": "failed",
                                  "evidence": "synthetic failure intentionally retained"}]}
            record = root / "execution.json"
            record.write_text(json.dumps(report))
            with patch.object(kit, "_build_wheel", side_effect=self._wheel), \
                    patch.object(kit, "_prepare_fixtures", side_effect=self._fixtures), \
                    patch.object(kit.importlib.metadata, "version", side_effect=BUILD_TOOL_VERSIONS.__getitem__):
                target = kit.prepare(repo, commit, "test-recorded-cohort", lock, root / "study", record)
            manifest = json.loads((target / "build-manifest.json").read_text())
            self.assertEqual(manifest["build_environment"]["tools"], BUILD_TOOL_VERSIONS)
            self.assertEqual(json.loads((target / "rehearsal/execution.json").read_text()), report)
            self.assertEqual(manifest["rehearsal"]["checks"][0]["status"], "failed")
            self.assertEqual(manifest["rehearsal"]["sha256"], kit.sha256(record))
            kit.verify_inventory(target)

    def test_lock_must_cover_and_satisfy_wheel_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export = root / "source"
            export.mkdir()
            (export / "README.md").write_text("frozen test source")
            wheel = self._wheel(export, root / "wheels", "1", root / "build.log")
            metadata = kit._wheel_metadata(wheel)
            kit._check_lock(metadata, "numpy==2.4.6\n")
            for lock in ("aiohttp==3.14.3\n", "numpy==1.0.0\n", "numpy==2.4.6\ngex-terminal==0.5.0\n"):
                with self.subTest(lock=lock), self.assertRaises(ValueError):
                    kit._check_lock(metadata, lock)

    def test_generated_capture_fixtures_are_deterministic_and_source_timed(self):
        from gex_terminal.session_capture import inspect_captured_session

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = kit._prepare_fixtures(ROOT, root / "first")
            second = kit._prepare_fixtures(ROOT, root / "second")
            self.assertEqual(first, second)
            self.assertEqual(tuple(row["name"] for row in first), kit.FIXTURES)
            self.assertEqual([(row["symbol"], row["contract_multiplier"]) for row in first], [("ES", 50), ("NQ", 20)])
            for row in first:
                path = root / "first" / Path(row["capture_path"]).name
                verified = inspect_captured_session(path)
                self.assertTrue(verified["integrity_verified"])
                self.assertEqual(verified["event_time_fallback_count"], 0)
                self.assertEqual(verified["source"]["source_kind"], "synthetic_fixture")
                self.assertEqual(verified["source"]["mode"], "replay")
                self.assertEqual(verified["source"]["rights_status"], "owned")
                self.assertTrue(verified["source"]["redistributable"])
                self.assertEqual(row["selected_checkpoint"], verified["event_count"] - 1)
                self.assertEqual(kit.sha256(path), row["capture_sha256"])


if __name__ == "__main__":
    unittest.main()

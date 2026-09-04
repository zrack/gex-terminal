import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.artifact_lifecycle import (
    PRIVATE_BACKUP_SCHEMA,
    RETENTION_PLAN_SCHEMA,
    apply_retention_plan,
    create_private_backup,
    create_retention_plan,
    restore_private_backup,
    verify_private_backup,
)
from gex_terminal.experiment_manifest import run_experiment
from gex_terminal.local_support import inspect_research_artifact
from gex_terminal.package_data import provider_fixture_path
from gex_terminal.research_corpus import initialize_corpus, register_corpus_item
from gex_terminal.research_journal import ENTRY_SCHEMA


class ArtifactLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def _experiment(self, root: Path, name: str = "experiment") -> Path:
        spec = json.loads(
            provider_fixture_path("experiment_spec_example.json").read_text()
        )
        spec["experiment_id"] = name
        spec["input"] = str(
            provider_fixture_path("price_action_validation_example.json")
        )
        spec_path = root / f"{name}-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        target = root / name
        await run_experiment(spec_path, target)
        return target

    @staticmethod
    def _corpus(root: Path, name: str = "corpus") -> Path:
        target = root / name
        initialize_corpus(target, corpus_id=f"{name}-id")
        source = target / "input.json"
        source.write_text('{"value":1}\n', encoding="utf-8")
        metadata = json.loads(
            provider_fixture_path("corpus_item_metadata_example.json").read_text()
        )
        metadata["dataset_id"] = f"{name}-dataset"
        metadata_path = root / f"{name}-metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        register_corpus_item(target, source, metadata_path)
        return target

    @staticmethod
    def _journal(root: Path, name: str = "journal", *, entries: int = 1) -> Path:
        target = root / name
        entries_dir = target / "entries"
        entries_dir.mkdir(parents=True)
        for index in range(entries):
            entry = {
                "schema": ENTRY_SCHEMA,
                "id": f"{name}-entry-{index}",
                "generated_at": f"2026-09-04T12:00:0{index}Z",
                "summary": {"label": "synthetic lifecycle test"},
            }
            (entries_dir / f"entry-{index}.json").write_text(
                json.dumps(entry), encoding="utf-8"
            )
        return target

    @staticmethod
    def _demo_lab(root: Path, name: str = "demo-lab") -> Path:
        target = root / name
        target.mkdir()
        receipt = {
            "schema": "gex-terminal.demo-lab-review-receipt.v1",
            "receipt_sha256": "1" * 64,
            "pack": {
                "schema": "gex-terminal.demo-lab.v2",
                "content_sha256": "2" * 64,
            },
            "source": {"sha256": "3" * 64},
            "model": {"profile_sha256": "4" * 64},
            "content": {"snapshot.json": "5" * 64},
            "artifacts": [
                {
                    "path": "manifest.json",
                    "kind": "manifest",
                    "bytes": 38,
                    "sha256": "6" * 64,
                }
            ],
        }
        (target / "review-receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        (target / "manifest.json").write_text(
            '{"schema":"gex-terminal.demo-lab.v2"}\n', encoding="utf-8"
        )
        return target

    @staticmethod
    def _verify_demo_lab(root: Path) -> dict:
        receipt = json.loads((Path(root) / "review-receipt.json").read_text())
        return {
            "schema": "gex-terminal.demo-lab-verification.v1",
            "content_sha256": receipt["pack"]["content_sha256"],
            "receipt": receipt,
        }

    async def test_private_backup_verify_restore_preserves_supported_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = (
                await self._experiment(root, "experiment-source"),
                self._corpus(root, "corpus-source"),
                self._journal(root, "journal-source", entries=2),
            )
            for source in sources:
                with self.subTest(kind=source.name):
                    original = inspect_research_artifact(source)
                    backup = root / f"{source.name}-backup"
                    verification = create_private_backup(source, backup)
                    self.assertEqual(
                        json.loads((backup / "backup-manifest.json").read_text())[
                            "schema"
                        ],
                        PRIVATE_BACKUP_SCHEMA,
                    )
                    self.assertEqual(verification["status"], "verified")
                    self.assertFalse(verification["artifact"].get("shareable", False))
                    self.assertEqual(
                        verify_private_backup(backup)["manifest_sha256"],
                        verification["manifest_sha256"],
                    )

                    restored_dir = root / f"{source.name}-restored"
                    receipt = restore_private_backup(backup, restored_dir)
                    restored = inspect_research_artifact(restored_dir)
                    self.assertEqual(receipt["status"], "restored_and_verified")
                    self.assertEqual(restored["content_sha256"], original["content_sha256"])
                    self.assertEqual(restored["primary_sha256"], original["primary_sha256"])
                    self.assertEqual(
                        restored["recorded_identities"], original["recorded_identities"]
                    )

    async def test_backup_and_restore_refuse_overwrite_traversal_and_environment_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._journal(root, "safe-journal")
            existing = root / "existing-backup"
            existing.mkdir()
            sentinel = existing / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                create_private_backup(source, existing)
            self.assertEqual(sentinel.read_text(), "keep")

            with self.assertRaisesRegex(ValueError, "traversal"):
                create_private_backup(source / ".." / source.name, root / "unused")

            (source / ".env").write_text("DATABENTO_API_KEY=secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "environment and credential"):
                create_private_backup(source, root / "env-backup")
            (source / ".env").unlink()

            backup = root / "valid-backup"
            create_private_backup(source, backup)
            restore_target = root / "existing-restore"
            restore_target.mkdir()
            restore_sentinel = restore_target / "keep.txt"
            restore_sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                restore_private_backup(backup, restore_target)
            self.assertEqual(restore_sentinel.read_text(), "keep")

    async def test_backup_and_restore_reject_containment_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._journal(root, "source")
            original_files = sorted(path.relative_to(source) for path in source.rglob("*"))
            nested_backup = source / "backup"
            with self.assertRaisesRegex(ValueError, "must not overlap"):
                create_private_backup(source, nested_backup)
            self.assertFalse(nested_backup.exists())
            self.assertEqual(
                sorted(path.relative_to(source) for path in source.rglob("*")),
                original_files,
            )

            backup = root / "backup"
            create_private_backup(source, backup)
            nested_restore = backup / "payload" / "restored"
            with self.assertRaisesRegex(ValueError, "must not overlap"):
                restore_private_backup(backup, nested_restore)
            self.assertFalse(nested_restore.exists())

    async def test_destination_ancestor_symlinks_cannot_bypass_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._journal(root, "source")
            actual_parent = root / "actual-parent"
            actual_parent.mkdir()
            alias = root / "alias"
            alias.symlink_to(actual_parent, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "ancestors must not be symlinks"):
                create_private_backup(source, alias / "backup")
            self.assertFalse((actual_parent / "backup").exists())

            actual_source_parent = root / "actual-source-parent"
            actual_source_parent.mkdir()
            nested_source = self._journal(actual_source_parent, "nested-source")
            source_alias = root / "source-alias"
            source_alias.symlink_to(actual_source_parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ancestors must not be symlinks"):
                create_private_backup(
                    source_alias / nested_source.name,
                    root / "unused-backup",
                )
            self.assertFalse((root / "unused-backup").exists())

    async def test_backup_verification_rejects_tamper_partial_and_missing_components(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._journal(root, "journal", entries=2)

            partial = root / "partial-backup"
            create_private_backup(source, partial)
            (partial / "payload" / "entries" / "entry-0.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing, changed, or contains extras"):
                verify_private_backup(partial)

            tampered = root / "tampered-backup"
            create_private_backup(source, tampered)
            manifest_path = tampered / "backup-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["created_at"] = "2030-01-01T00:00:00Z"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity is inconsistent"):
                verify_private_backup(tampered)

            missing = root / "missing-backup"
            create_private_backup(source, missing)
            (missing / "backup-manifest.json").unlink()
            with self.assertRaisesRegex(ValueError, "manifest is missing"):
                verify_private_backup(missing)

            exposed = root / "exposed-backup"
            create_private_backup(source, exposed)
            os.chmod(exposed / "backup-manifest.json", 0o644)
            with self.assertRaisesRegex(ValueError, "owner-only permissions"):
                verify_private_backup(exposed)

    async def test_private_outputs_are_owner_only_under_normal_umask(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._journal(root, "private-source")
            previous_umask = os.umask(0o022)
            try:
                backup = root / "private-backup"
                create_private_backup(source, backup)
                restored = root / "private-restored"
                restore_private_backup(backup, restored)
                plan_path = root / "private-plan.json"
                create_retention_plan(
                    [source],
                    "2030-01-01T00:00:00Z",
                    plan_path,
                    backup_dirs=[backup],
                )
            finally:
                os.umask(previous_umask)

            for directory in (
                backup,
                *(path for path in backup.rglob("*") if path.is_dir()),
                restored,
                *(path for path in restored.rglob("*") if path.is_dir()),
            ):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            for path in (
                *(path for path in backup.rglob("*") if path.is_file()),
                *(path for path in restored.rglob("*") if path.is_file()),
                plan_path,
            ):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    async def test_demo_lab_receipt_identity_is_preserved_across_full_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._demo_lab(root)
            with patch(
                "gex_terminal.local_support._verify_demo_lab_pack",
                side_effect=self._verify_demo_lab,
            ):
                original = inspect_research_artifact(source)
                self.assertEqual(original["kind"], "demo_lab")
                self.assertEqual(original["primary_sha256"], "1" * 64)

                backup = root / "demo-backup"
                verification = create_private_backup(source, backup)
                restored = root / "demo-restored"
                restore_private_backup(backup, restored)
                self.assertEqual(
                    verification["artifact"]["recorded_identities"],
                    inspect_research_artifact(restored)["recorded_identities"],
                )

                self._set_tree_mtime(restored, 1_600_000_000_000_000_000)
                plan_path = root / "demo-retention.json"
                plan = create_retention_plan(
                    [restored],
                    "2026-01-01T00:00:00Z",
                    plan_path,
                    backup_dirs=[backup],
                )
                receipt = apply_retention_plan(
                    plan_path, confirmation=plan["plan_sha256"]
                )
                self.assertEqual(receipt["deleted_count"], 1)
                self.assertFalse(restored.exists())

    async def test_corpus_backup_rejects_external_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "external-corpus"
            initialize_corpus(corpus, corpus_id="external-corpus")
            source = root / "outside.json"
            source.write_text('{"value":1}\n', encoding="utf-8")
            register_corpus_item(
                corpus,
                source,
                provider_fixture_path("corpus_item_metadata_example.json"),
            )
            with self.assertRaisesRegex(ValueError, "in-directory regular sources"):
                create_private_backup(corpus, root / "external-backup")

    async def test_marker_files_do_not_turn_broad_directories_into_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal = self._journal(root, "journal")
            required_backup = root / "required-backup"
            create_private_backup(journal, required_backup)
            sentinel = journal / "unrelated-private-file.txt"
            sentinel.write_text(
                "must not be swept into lifecycle", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsupported or missing files"):
                create_private_backup(journal, root / "backup")
            with self.assertRaisesRegex(ValueError, "unsupported or missing files"):
                create_retention_plan(
                    [journal],
                    "2030-01-01T00:00:00Z",
                    root / "unsafe-plan.json",
                    backup_dirs=[required_backup],
                )
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "must not be swept into lifecycle",
            )

            sentinel.unlink()
            empty_sentinel = journal / "unrelated-empty-project"
            empty_sentinel.mkdir()
            with self.assertRaisesRegex(ValueError, "unsupported or missing files"):
                create_retention_plan(
                    [journal],
                    "2030-01-01T00:00:00Z",
                    root / "empty-unsafe-plan.json",
                    backup_dirs=[required_backup],
                )
            self.assertTrue(empty_sentinel.is_dir())

    async def test_retention_requires_plan_confirmation_and_deletes_only_expired_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expired = self._journal(root, "expired")
            retained = self._journal(root, "retained")
            expired_backup = root / "expired-backup"
            retained_backup = root / "retained-backup"
            create_private_backup(expired, expired_backup)
            create_private_backup(retained, retained_backup)
            self._set_tree_mtime(expired, 1_600_000_000_000_000_000)
            self._set_tree_mtime(retained, 1_900_000_000_000_000_000)
            plan_path = root / "retention-plan.json"

            plan = create_retention_plan(
                [expired, retained],
                "2026-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[expired_backup, retained_backup],
                created_at="2026-09-04T12:00:00Z",
            )
            self.assertEqual(plan["schema"], RETENTION_PLAN_SCHEMA)
            self.assertTrue(expired.exists())
            self.assertTrue(retained.exists())
            self.assertEqual(
                {target["action"] for target in plan["targets"]},
                {"delete_whole_group", "retain"},
            )

            with self.assertRaisesRegex(ValueError, "exact plan SHA-256"):
                apply_retention_plan(plan_path, confirmation="0" * 64)
            self.assertTrue(expired.exists())
            self.assertTrue(retained.exists())

            receipt = apply_retention_plan(
                plan_path, confirmation=plan["plan_sha256"]
            )
            self.assertEqual(receipt["deleted_count"], 1)
            self.assertEqual(receipt["retained_count"], 1)
            self.assertFalse(expired.exists())
            self.assertTrue(retained.exists())

    async def test_retention_requires_matching_backup_and_reverifies_it_on_apply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = self._journal(root, "target")
            other = self._journal(root, "other")
            target_backup = root / "target-backup"
            other_backup = root / "other-backup"
            create_private_backup(target, target_backup)
            create_private_backup(other, other_backup)

            with self.assertRaisesRegex(ValueError, "one explicit verified backup"):
                create_retention_plan(
                    [target],
                    "2030-01-01T00:00:00Z",
                    root / "missing-backup-plan.json",
                    backup_dirs=[],
                )
            with self.assertRaisesRegex(ValueError, "content or recorded identity"):
                create_retention_plan(
                    [target],
                    "2030-01-01T00:00:00Z",
                    root / "mismatched-backup-plan.json",
                    backup_dirs=[other_backup],
                )

            plan_path = root / "verified-plan.json"
            plan = create_retention_plan(
                [target],
                "2030-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[target_backup],
            )
            backup_entry = target_backup / "payload" / "entries" / "entry-0.json"
            backup_entry.write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "backup changed or no longer verifies"):
                apply_retention_plan(
                    plan_path, confirmation=plan["plan_sha256"]
                )
            self.assertTrue(target.is_dir())

    async def test_retention_revalidates_all_targets_before_deleting_any(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = self._journal(root, "a-expired")
            second = self._journal(root, "b-expired")
            first_backup = root / "a-backup"
            second_backup = root / "b-backup"
            create_private_backup(first, first_backup)
            create_private_backup(second, second_backup)
            old = 1_600_000_000_000_000_000
            self._set_tree_mtime(first, old)
            self._set_tree_mtime(second, old)
            plan_path = root / "plan.json"
            plan = create_retention_plan(
                [first, second],
                "2026-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[first_backup, second_backup],
            )
            changed_entry = second / "entries" / "entry-0.json"
            changed_entry.write_text('{"changed":true}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "changed after planning"):
                apply_retention_plan(plan_path, confirmation=plan["plan_sha256"])
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    async def test_retention_quarantine_never_deletes_replacement_at_original_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = self._journal(root, "expired")
            backup = root / "backup"
            create_private_backup(target, backup)
            self._set_tree_mtime(target, 1_600_000_000_000_000_000)
            plan_path = root / "plan.json"
            plan = create_retention_plan(
                [target],
                "2026-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[backup],
            )
            real_rmtree = shutil.rmtree

            def replace_original_then_delete_quarantine(quarantine):
                target.mkdir()
                sentinel = target / "unrelated-replacement.txt"
                sentinel.write_text("replacement must survive", encoding="utf-8")
                real_rmtree(quarantine)

            with patch(
                "gex_terminal.artifact_lifecycle.shutil.rmtree",
                side_effect=replace_original_then_delete_quarantine,
            ):
                receipt = apply_retention_plan(
                    plan_path, confirmation=plan["plan_sha256"]
                )

            self.assertEqual(receipt["deleted_count"], 1)
            self.assertEqual(
                (target / "unrelated-replacement.txt").read_text(encoding="utf-8"),
                "replacement must survive",
            )

    async def test_retention_rolls_back_every_staged_target_before_any_delete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = self._journal(root, "first")
            second = self._journal(root, "second")
            first_backup = root / "first-backup"
            second_backup = root / "second-backup"
            create_private_backup(first, first_backup)
            create_private_backup(second, second_backup)
            old = 1_600_000_000_000_000_000
            self._set_tree_mtime(first, old)
            self._set_tree_mtime(second, old)
            plan_path = root / "plan.json"
            plan = create_retention_plan(
                [first, second],
                "2026-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[first_backup, second_backup],
            )
            from gex_terminal import artifact_lifecycle

            real_stage = artifact_lifecycle._stage_retention_target

            def tamper_second_after_stage(target):
                quarantine = real_stage(target)
                if target.name == "second":
                    (quarantine / "entries" / "entry-0.json").write_text(
                        '{"changed":true}\n', encoding="utf-8"
                    )
                return quarantine

            with patch(
                "gex_terminal.artifact_lifecycle._stage_retention_target",
                side_effect=tamper_second_after_stage,
            ), self.assertRaisesRegex(ValueError, "all staged targets were restored"):
                apply_retention_plan(
                    plan_path, confirmation=plan["plan_sha256"]
                )

            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertFalse(tuple(root.glob(".gex-terminal-retention-*")))

    async def test_interrupted_retention_leaves_quarantine_and_verified_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = self._journal(root, "target")
            backup = root / "backup"
            create_private_backup(target, backup)
            self._set_tree_mtime(target, 1_600_000_000_000_000_000)
            plan_path = root / "plan.json"
            plan = create_retention_plan(
                [target],
                "2026-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[backup],
            )

            with patch(
                "gex_terminal.artifact_lifecycle.shutil.rmtree",
                side_effect=OSError("synthetic interruption"),
            ), self.assertRaisesRegex(ValueError, "remaining same-parent quarantine"):
                apply_retention_plan(
                    plan_path, confirmation=plan["plan_sha256"]
                )

            self.assertFalse(target.exists())
            self.assertEqual(len(tuple(root.glob(".gex-terminal-retention-*"))), 1)
            self.assertEqual(verify_private_backup(backup)["status"], "verified")

    async def test_retention_rejects_tampered_plan_missing_target_and_broad_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = self._journal(root, "artifact")
            artifact_backup = root / "artifact-backup"
            create_private_backup(artifact, artifact_backup)
            self._set_tree_mtime(artifact, 1_600_000_000_000_000_000)
            plan_path = root / "plan.json"
            plan = create_retention_plan(
                [artifact],
                "2026-01-01T00:00:00Z",
                plan_path,
                backup_dirs=[artifact_backup],
            )
            tampered = json.loads(plan_path.read_text())
            tampered["cutoff"] = "2030-01-01T00:00:00Z"
            plan_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "plan identity is inconsistent"):
                apply_retention_plan(plan_path, confirmation=plan["plan_sha256"])
            self.assertTrue(artifact.exists())

            missing_artifact = self._journal(root, "missing-artifact")
            missing_backup = root / "missing-backup"
            create_private_backup(missing_artifact, missing_backup)
            self._set_tree_mtime(missing_artifact, 1_600_000_000_000_000_000)
            missing_plan_path = root / "missing-plan.json"
            missing_plan = create_retention_plan(
                [missing_artifact],
                "2026-01-01T00:00:00Z",
                missing_plan_path,
                backup_dirs=[missing_backup],
            )
            shutil.rmtree(missing_artifact)
            with self.assertRaisesRegex(ValueError, "changed after planning"):
                apply_retention_plan(
                    missing_plan_path,
                    confirmation=missing_plan["plan_sha256"],
                )

            with self.assertRaisesRegex(ValueError, "root, home, and repository"):
                create_retention_plan(
                    [Path.home()],
                    "2026-01-01T00:00:00Z",
                    root / "broad-plan.json",
                    backup_dirs=[artifact_backup],
                )

    @staticmethod
    def _set_tree_mtime(root: Path, modified_ns: int) -> None:
        for path in root.rglob("*"):
            if path.is_file():
                os.utime(path, ns=(modified_ns, modified_ns))


if __name__ == "__main__":
    unittest.main()

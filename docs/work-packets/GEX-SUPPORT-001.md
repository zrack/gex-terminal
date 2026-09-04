# GEX-SUPPORT-001 — Local Support And Artifact Lifecycle

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: ready_for_integration
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: pull-request reviewer and hosted CI
baseline: f4d1220
branch: codex/gex-support-001
created: 2026-09-04
```

## Authority and scope

The maintainer authorized the repository-owned, offline work through the live
data boundary, including Roadmap Slice 1D. This packet adds a safe support
artifact and an explicit local lifecycle for currently recognized research
directories. It does not authorize provider access, credential-store changes,
licensed-data distribution, package uninstall, deletion of real user data,
database/catalog work, or live/predictive claims.

This is L3 because it defines private backup and destructive-retention
contracts. All mutation tests use synthetic temporary directories. Roadmap,
documentation indexes, changelog, release version, live certification, and
credential-platform selection remain with the coordinating workstream.

## Adopted invariants

Adopt `INV-01` through `INV-08` of the project profile and add these lifecycle
constraints:

- `SUP-01` — A shareable support bundle contains only application version,
  configuration field names/types, canonical readiness labels, bounded offline
  doctor results, and content identities/counts. It contains no configuration
  values, raw paths, credentials, account IDs, payloads, exception text, or log
  files.
- `SUP-02` — A private backup is never described as shareable. It may copy only
  an explicitly selected, recognized Demo Lab pack, experiment, research-
  corpus, or research-journal directory whose complete tree contains no
  symlink or traversal escape. The destination must be new and no file is
  overwritten. Every file and directory must belong to the artifact's exact
  declared or canonical topology; a marker file alone is insufficient. Private
  directories and files are created with owner-only `0700`/`0600` modes.
- `SUP-03` — Backup verification and restore compare every relative file path,
  byte count, and SHA-256 digest. Restore writes only to a new destination and
  revalidates the restored tree before success.
- `SUP-04` — Retention first writes a dry-run plan. Application requires the
  exact plan SHA-256 as a separate confirmation and revalidates every selected
  directory, artifact identity, file, byte count, and digest before deletion.
  Every target is paired explicitly with a verified, identity-matching private
  backup. Eligible targets move atomically to randomized same-parent quarantine
  names; every moved tree and backup is revalidated before any deletion.
- `SUP-05` — Retention deletes only whole recognized artifact groups. It never
  prunes or rewrites corpus event chains, journal entries, experiment files, or
  other ledger rows.
- `SUP-06` — Root, home, repository, environment/credential, symlinked, broad,
  missing, unrecognized, changed, or path-escaping targets fail closed.

## Supported contract

The initial lifecycle is deliberately directory-scoped:

| Kind | Recognition and preserved identity | Lifecycle unit |
| --- | --- | --- |
| Demo Lab | verified review-receipt v1, receipt and pack hashes, source and model-profile hashes, and bound semantic-content hashes | Whole portable Demo Lab pack |
| Experiment | v1/v2 `manifest.json`, its experiment ID and recorded identity/result digest, plus complete directory tree | Whole experiment directory |
| Research corpus | valid `events.jsonl`, corpus ID, event count, chain head, and only in-directory source references | Whole corpus directory |
| Research journal | `entries/*.json` using the journal-entry schema, entry IDs and complete directory tree | Whole journal directory |

Captured-session stores, arbitrary folders, external corpus sources, partial
captures, raw licensed inputs outside a recognized corpus, databases, and
credential files are not silently generalized into this contract. Their
rights, retention, and recovery decisions remain separate.

## Acceptance

- The public support command produces deterministic bounded sections and
  embeds the synchronous `gex-terminal.doctor.v1` report through its documented
  API without network, live adapter, optional SDK import, or log collection.
- Adversarial values in environment, configuration, doctor input, filenames,
  JSON payloads, and artifact contents cannot appear in the support output.
- Backup, verify, and restore round-trip synthetic Demo Lab, experiment,
  corpus, and journal groups byte-for-byte while preserving their content
  identities.
- Backup and restore reject existing destinations, symlinks, traversal, missing
  files, digest drift, partial copies, and unsupported artifact layouts.
- Retention planning is non-destructive. Apply requires exact confirmation,
  rejects a changed plan, target, or backup, stages and revalidates all eligible
  groups before deleting any, and removes only complete eligible synthetic
  groups. Ineligible groups, replacement paths, and sibling data remain
  untouched.
- CLI help and the canonical local-support guide state the privacy split,
  credential/uninstall boundary, recovery procedure, and unsupported cases.
- Focused tests, the full unit suite, source compilation, public CLI smokes,
  and diff hygiene pass before handoff.

## Recovery and stop conditions

Code rollback is a normal commit revert. A private backup is verified before a
source is eligible for any independent deletion decision; restore never writes
over a destination. Retention has no implicit apply, wildcard, recursive-root,
or force mode. Stop on any identity mismatch, symlink, unsupported layout,
secret-bearing support output, partial restore, unclear rights, or request to
operate on non-synthetic user data during implementation.

## Evidence

- `tests.test_artifact_lifecycle`, `tests.test_local_support`, and
  `tests.test_local_support_cli`: 22 tests passed, including private
  backup/restore round trips, owner-only modes, exact topology, explicit backup
  binding, tamper and partial-copy rejection, all-target preflight, quarantine
  rollback, replacement-path survival, redaction, bounds, and separate CLI
  confirmation.
- Full unit discovery on the isolated feature branch: 330 tests passed with no
  failures. Source compilation completed without errors and `git diff --check`
  passed.
- All filesystem mutations used synthetic temporary research directories.
  The doctor report was injected through its stable offline schema and Demo Lab
  identity was exercised through the stable verifier boundary pending the
  coordinating branch merge that supplies those independently owned modules.
- No provider credentials, live data, user research, licensed capture store,
  package uninstall, authenticity claim, or deletion outside disposable
  temporary directories was exercised.

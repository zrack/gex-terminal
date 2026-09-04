# Local Support And Research Lifecycle

This guide covers two intentionally separate local workflows:

| Workflow | Classification | Contains research payloads? | Safe to attach to a support request? |
| --- | --- | --- | --- |
| Support bundle | Shareable, redacted support evidence | No | Yes, after the operator reviews the JSON |
| Backup, restore, and retention | Private local research | Yes | No |

Neither workflow contacts a provider, validates credentials, certifies live
data, or makes a predictive or profitability claim.

## Create a redacted support bundle

Run the offline doctor and collect bounded configuration shape, canonical
provider-readiness labels, and optional artifact identities:

```bash
gex-terminal support-bundle support.json [ARTIFACT_DIR ...]
```

The output includes application version, configuration field names and types,
the offline doctor report, and, for each supported artifact, its kind, file
count, byte count, content digest, and a one-way fingerprint of its local
identifier. It does not include configuration values, raw paths, credentials,
account identifiers, raw payloads, exceptions, or log-file contents. Output is
bounded and the command refuses to overwrite an existing file.

Supported artifact directories are verified Demo Lab review-receipt v1 packs,
experiment manifest v1/v2 directories, verified research corpora with only
in-directory sources, and research journals containing journal-entry v1 files.
The bundle does not copy those directories; it reports only redacted identities
and counts. Review `support.json` before sharing it.

The bundle remains diagnostic evidence, not an authenticity proof. All hashes
used by these workflows are unkeyed integrity identifiers; someone able to
replace an artifact and its manifest can recompute them. A successful doctor
report does not prove a provider connection or live-data readiness.

## Back up private research

Back up one explicitly selected, supported artifact directory:

```bash
gex-terminal research-backup ARTIFACT_DIR NEW_BACKUP_DIR
gex-terminal research-backup-verify BACKUP_DIR
```

The backup directory is classified `private-local-research` and may contain the
complete authorized research payload. Do not attach it to a support request or
redistribute it without a separate rights review. The backup is not encrypted;
choose a destination whose operating-system permissions and storage controls
match the sensitivity of the research.

The command copies the whole recognized directory, records every relative
path, byte count, and SHA-256 digest, preserves the artifact's recorded
identities, and verifies the completed payload. The source and destination
must be distinct, the destination must be new and outside the repository, and
the tree may not contain symlinks, special files, path traversal, or `.env`
files. Every file and directory must belong to the artifact's exact declared
or canonical topology, so an unrelated file or empty directory makes the
selection ineligible. The destination parent must already exist. Private
directories and files are created owner-only (`0700` and `0600`); the command
fails if the platform cannot enforce those modes. No file is overwritten.

For a Demo Lab pack, verification preserves the distinct receipt, pack, source,
model-profile, and semantic-content hashes. For an experiment it preserves the
manifest identities. For a corpus it preserves its append-only chain head and
requires every registered source to be inside the corpus directory. For a
journal it preserves the entry IDs and complete entry bytes.

External experiment inputs referenced by a manifest are not silently copied.
The backup preserves the artifact directory; it does not promise that an
external input needed for a later experiment reproduction remains available.

## Restore and recover

Restore only from a verified backup and only into a new directory:

```bash
gex-terminal research-backup-verify BACKUP_DIR
gex-terminal research-restore BACKUP_DIR NEW_ARTIFACT_DIR
```

Restore verifies the manifest and every payload file before creating the
destination, copies without overwrite, and verifies the restored artifact and
identities before reporting success. A missing manifest, partial payload,
unexpected file, digest mismatch, incompatible artifact contract, or changed
identity fails closed.

If backup or restore is interrupted, the new destination may be incomplete and
will not be reported as verified. Keep the original source, inspect the partial
directory separately, and choose another new destination for the next attempt.
Never delete a source merely because a backup directory exists; first run the
verification command and retain its manifest digest.

## Plan retention before deletion

Retention operates on whole supported artifact directories. Planning is a
non-destructive dry run:

```bash
gex-terminal research-retention-plan /private/operator/retention-plan.json \
  2026-01-01T00:00:00Z ARTIFACT_DIR [ARTIFACT_DIR ...] \
  --retention-backup BACKUP_DIR [--retention-backup BACKUP_DIR ...]
```

The cutoff must include a timezone. Eligibility uses the newest file
modification time in each selected directory. Inspect the private plan: it
contains exact local paths, artifact identities, every file digest and byte
count, the matching verified-backup identity, and either `delete_whole_group`
or `retain` for each directory. Repeat `--retention-backup` once per artifact,
in the same order. A missing, invalid, or identity-mismatched backup makes the
target ineligible. The private plan is created with mode `0600` and must remain
outside the repository, selected artifacts, and their backups.

Applying is a separate command and requires the exact plan hash printed by the
planning command:

```bash
gex-terminal research-retention-apply /private/operator/retention-plan.json \
  --confirm-plan-sha256 EXACT_PLAN_SHA256
```

Before deleting anything, apply validates the plan hash and rechecks every
target and paired backup. A missing, added, edited, or moved file or directory,
or a changed file timestamp, invalidates the plan. Private backup and plan
permissions are checked separately. Eligible groups are atomically moved to
randomized, same-parent quarantine names, and every staged tree and backup is
checked again before any quarantine is deleted. A replacement later placed at
the original path is not the staged artifact and is not deleted. Only complete
groups marked `delete_whole_group` are removed; retained groups and sibling
directories are untouched.
There is no default deletion, wildcard target, force mode, or partial-entry
pruning. Corpus event rows, journal entries, experiment files, and receipt
members are never selectively rewritten.

Root, home, repository, overlapping, broad, unrecognized, symlinked, and
credential-file targets are refused. Create a new plan after any intentional
artifact change.

If staging or revalidation fails, every staged name is moved back before the
command exits. If filesystem deletion itself is interrupted, a hidden
`.gex-terminal-retention-*` quarantine may remain beside the original target;
do not treat the operation as complete. Inspect and recover that private tree
before creating another plan.

## Credentials and uninstall

Credentials remain in the existing operator-controlled environment or `.env`
workflow. These lifecycle commands never read, copy, report, rotate, or delete
credential files. Remove an exported value from the current shell using the
shell's environment-removal command, and edit or delete an operator-owned
`.env` file explicitly if that is where the value was stored. Confirm removal
using the offline doctor; the doctor checks shape/readiness only and does not
validate a secret against a provider.

The current provider credential variables are `DATABENTO_API_KEY` and
`TRADOVATE_NAME`, `TRADOVATE_PASSWORD`, `TRADOVATE_APP_ID`, `TRADOVATE_CID`,
and `TRADOVATE_SEC`. The repository's `.env.example` is a shape-only template;
real values belong only in the operator's environment or untracked local
`.env` file.

No keychain or secrets-manager integration is introduced here. Choosing and
implementing a credential platform is a separate governed provider decision.

Uninstalling the Python package does not delete research directories, private
backups, retention plans, support bundles, or `.env` files. Remove those only
through an explicit, separately reviewed local decision. The retention command
supports only recognized research artifact groups; it is not a general
uninstaller or secure-erasure tool.

## Deliberate limits

Captured-session stores, partial captures, arbitrary directories, databases,
external corpus sources, and raw licensed capture stores are outside this
lifecycle. Licensed-data rights, retention, redistribution, and deletion need
their own policy and evidence. This slice also does not provide encryption,
cloud backup, scheduling, filesystem snapshots, secure erase, or generalized
migration tooling.

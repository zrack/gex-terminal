# GEX-HEALTH-004 — Experiment Identity

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: ready_for_integration
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@4c79f1f
branch: codex/gex-health-004-experiment-identity
created: 2026-09-04
```

## Authority and scope

The maintainer authorized the offline roadmap through the live-data boundary,
including independently mergeable correctness repairs and contributor review.
This slice closes H4 from the application review by making experiment metadata
part of a validated, versioned identity. It does not add live access, sign or
anchor artifacts, package a portable input, promote predictive validity, or
claim protection from deliberate tampering.

Own the experiment manifest implementation and tests, the minimum CLI status
needed to expose legacy identity limits, and the research-governance contract.
Roadmap, documentation indexes, changelog, release version, and portable pack
integration remain with the coordinating workstream.

## Contract and compatibility

Adopt INV-01 through INV-08 of the adoption profile and preserve model math,
workflow behavior, semantic-result hashing, and local artifact ownership.

- New runs emit `gex-terminal.experiment-manifest.v2`. The normalized complete
  experiment spec, inline profile, input identity, producer implementation, and
  semantic result are bound by canonical SHA-256 identities.
- Manifest-local `source_root`/`spec_reference` locations, generation time, and
  reproduction-operation status are excluded from the stable experiment
  identity. The declared spec input reference remains bound; a later portable
  pack must give it a stable logical reference rather than silently rewriting
  an existing experiment.
- The v2 producer/reader contract is
  `gex-terminal.experiment-runtime.v1`. Package version `0.4.0` is explicitly
  supported; future releases must deliberately update compatibility rather
  than infer it from semantic version numbers.
- Existing v1 manifests produced by package versions `0.3.0` and `0.4.0`
  remain readable when every identity they actually recorded is consistent.
  Successful reproduction still requires the current workflow to match the
  recorded semantic result; additive report fields or corrected chronology may
  therefore make an older result fail rather than be silently reinterpreted.
  V1 reports `legacy_partial`, because it cannot independently prove that
  split, outcome, or cost metadata was never relabeled.
- Unknown manifest, spec, model, runtime-contract, or producer versions fail
  before experiment execution. A legacy record is never silently promoted to
  complete historical identity assurance.

## Acceptance

- An unchanged v2 experiment reproduces with complete identity validation and
  the same semantic result.
- Profile, split, outcome, cost, input reference/digest/size, mirrored workflow
  or experiment ID, implementation, result, or stored identity changes fail at
  their owning validation gate.
- Metadata and implementation failures occur before a workflow is invoked or
  output is created. Result drift still fails after deterministic execution.
- A nonempty output directory fails before execution, including an attempt to
  reproduce into the source artifact directory; existing report and manifest
  bytes remain untouched.
- Known, internally consistent v1 manifests reproduce with an explicit
  `legacy_partial` status and v2 lineage to the exact source-manifest bytes.
  A stale v1 profile hash or unknown producer version fails closed.
- Canonical identity rejects malformed digests and non-finite values. Hashes
  establish internal consistency only; authenticity remains a separate future
  signing or anchoring decision.
- Focused tests, the full unit suite, source compilation, and diff hygiene pass
  before the branch is handed back for independent merge.

## Recovery

No stored artifact is migrated or overwritten in place. Run and reproduction
targets must be absent or empty, and artifact files use exclusive creation. The
source manifest remains operator-owned. Reverting the eventual merge restores
the v1 writer/reader. A v1 record from an undeclared producer must be reproduced
with its originating release or rerun from its original spec and input as a new
v2 experiment.

## Evidence

- `tests.test_experiment_manifest`: 15 tests passed, including complete v2
  identity, legacy partial identity, predictive-validity and unknown-field
  rejection, result/input drift, CLI status, and no-overwrite coverage.
- Full unit discovery: 308 tests passed with no failures.
- Source compilation for `main.py`, `gex_terminal`, and `tests` completed with
  no errors; `git diff --check` passed.
- An out-of-worktree public CLI run/reproduce smoke completed with
  `matched=True` and `identity_validation=complete` when the isolated source
  was selected explicitly.
- Verification used packaged offline fixtures only. No provider credentials,
  live market connection, signing authority, or empirical-validity claim was
  exercised.

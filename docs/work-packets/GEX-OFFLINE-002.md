# GEX-OFFLINE-002 — Offline Reliability And Release Verification

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L2
status: in_review
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent reviewer and hosted CI
baseline: main@ddd03e48be13f41cf4314fc49d2628fcdfa40c21
branch: codex/offline-reliability-release
created: 2026-09-26
```

## Authority and scope

The maintainer requested a clean pull and all four proposed offline improvements:
semantic replay expectations, retained synthetic build evidence, macOS release
verification, and repeatable documentation previews. The clean fast-forward pull
confirmed the baseline above. This packet routes bounded testing and maintainer
automation through the existing package/build and offline command contracts.
It introduces no release publication mechanism, new supported customer platform,
runtime calculation change, or enforced performance budget.

Visual review reproduced two existing defects in the generated demo SVG:
the first row covers its table headings and long regime text exceeds its panel.
The bounded scope also corrects those presentation coordinates and captures
onboarding at a height that exposes its replay list. Model calculations, fixture
inputs and interactive terminal behavior remain unchanged. Rebuild and recheck
the package after this exporter-only correction.

Implementation, local verification, a feature branch and reviewable pull request
are in scope. Protected-main merge and publication remain separately authorized
actions. The exact September 20 study bundle, its source and frozen materials
remain unchanged. No participant sessions or market-data connections are used.

## Acceptance

1. Bundled replay scenarios have independently reasoned expectations for useful
   alert types, event times, levels or regime transitions, including relevant
   absence cases. Checks must detect wrong behavior rather than snapshot the
   current implementation as its own oracle.
2. Linux and macOS CI run the existing Python 3.11/3.12 source, package and
   disposable installation/recovery checks. Matrix failures remain inspectable.
3. Each CI job retains a bounded allowlist of generated synthetic reports and
   previews, with source/run/runtime identity and available-file hashes, even
   when a preceding check fails. Missing/failed outputs remain explicit;
   arbitrary workspace, environment, secrets and private artifacts are excluded.
4. A maintainer command regenerates the demo and optional onboarding previews
   from explicit bundled synthetic inputs, records source/runtime/input/command
   identity, and avoids existing research folders and live configuration.
   Inspect refreshed visuals before accepting them; table headings, panel text
   and onboarding replay choices must be visible without overlap or clipping.
5. Focused regressions, full source suite, compilation, documentation links,
   distribution validation and independent review pass. Hosted checks establish
   their own observed result; local success cannot stand in for a hosted run.

## Evidence ceiling and recovery

These are software and release-verification improvements. They do not establish
unaided installation, customer demand, live reliability, provider readiness or
predictive value. Package version and existing tags remain unchanged. CI is a
verification environment, not a promise to support every tested platform.
Recovery is a reviewed revert of the bounded automation/tests/docs changes;
generated previews and reports can be rebuilt. No user data is migrated.

## Verification and closeout

- The final source passed all 461 tests on macOS ARM64 / CPython 3.12.13,
  compilation (including maintainer scripts), local documentation links and
  patch hygiene. Nine new replay tests cover semantic checkpoints; five
  deliberate in-memory alert/time/level/cross/regime mutations were detected.
- Numerical, offline Databento, model-property, provider-fault and default
  generated-chain performance gates passed. These retain their original
  software-only evidence ceilings and budgets.
- Final source/wheel distributions passed build and Twine checks. The actual
  workflow's installed-wheel and lifecycle steps passed in fresh temporary
  environments, including ES/NQ packs, reproduction, synthetic provider and
  research reports, private backup/restore, and install/upgrade/corrupt-update/
  rollback/uninstall with all 14 prior research artifact identities preserved.
- Complete local collection retained all 32 expected synthetic artifacts,
  with zero missing/rejected files and every saved byte hash verified. Local
  outcomes identify only the checks actually exercised; absent GitHub run and
  action identities remain unavailable. Earlier partial collection correctly
  retained two reports, recorded 30 missing files and exited unsuccessfully.
- Preview generation was exercised with hostile ambient configuration and a
  caller `.env`; both remained excluded. Existing destinations are preserved,
  timeout/failure states remain explicit, and source/input changes fail closed.
  Independent review corrected timeout status and timestamp wording before
  final verification. An earlier full-suite run rejected an over-broad receipt
  equality assertion; final checks compare stable numerical outputs while
  preserving and documenting variable generation/as-of and SVG timing fields.
- The final preview manifest and PNG render checks are retained locally under
  ignored `dist/offline-002-preview-layout/`. Both repository assets match their
  recorded hashes. Table headings and regime values are visible; onboarding at
  180×64 exposes the existing scrolling picker viewport. No interactive layout,
  numerical calculation, fixture, receipt schema or compatibility rule changed.
- Independent review found no unresolved issues in the packet/docs, collector,
  CI contract, preview isolation or final renderer diff. YAML parsing, all 13
  shell step bodies and Python 3.11 syntax checks passed. Hosted matrix results
  and protected-main merge remain separate completion evidence, pending review.

The initial clean pull was already current. Local integration reports remain in
the maintainer's temporary `gex-offline-002.SzyxBD` directory; generated logs and
full packages are not committed or uploaded by the bounded collector.

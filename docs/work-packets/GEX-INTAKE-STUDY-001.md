# GEX-INTAKE-STUDY-001 — Guided Session Intake And Current-Build Study

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent contributor review
baseline: main@cd81cc71075c64a31899c59cc9222f5f0be9ccb7
branch: codex/guided-session-intake
created: 2026-10-18
```

## Authority And Scope

The maintainer requested guided session intake, a current-build study kit,
regression tests, documentation, commit and merge. Keep issue #4 open for actual
Tradovate payloads. This slice acquires no live/provider data, changes no tags
or package version, and sends no participant invitations.

Provide an explicit local-file workflow in Wind Tunnel: verify a complete
captured session, review bounded source/time/assumption information, select a
capture sequence, freeze that prefix through the production consumer, then
calculate and save a portable receipt. Reuse the capture verifier and existing
strict checkpoint contract. Do not add a generic provider/CSV importer.

Prepare a separately named exact-build study cohort covering this workflow and
the Terminal checkpoint handoff. Preserve the September 20 kit and observations
unchanged. Freeze task/scoring definitions, synthetic inputs, source commit and
tree, wheel hash, dependency lock and materials. Automated rehearsal is software
evidence; real participant outcomes and consent remain uncollected.

## Contract And Invariants

[ADR-003](../decisions/ADR-003-guided-session-intake.md) owns memory, input and
privacy boundaries. The browser uploads selected bytes, never a server path.
Bound capture bytes, event count, retained sessions and offered choices. Verify
the complete capture before retaining an allowlisted representation. Reject
incomplete, tampered, unknown-contract or untimed inputs. Reviewed metadata
must not expose arbitrary header labels, extension fields, account identifiers
or paths. Preserve exact capture digest and sequence in portable provenance.

Replay only the selected prefix through the production consumer. Never include
later events. The preview reports the prefix's maximum genuine event time; the
frozen state uses the production consumer's latest accepted event time. Existing versioned checkpoint validation remains authoritative. Invalid
or canceled work cannot replace the browser's last validated research source.
Raw uploaded bytes are neither persisted nor logged by this workflow. Original
capture rights/retention obligations remain with its owner; integrity checks do
not establish authenticity, data truth or redistribution rights.

Preserve INV-01 through INV-08, model separation, existing loopback/capability/
origin protections, source-quality visibility and unchanged provider readiness.

## Acceptance And Integration

1. Integrity and parameter regressions cover bounds, malformed input, missing
   clocks, unexpected fields, independent ES/NQ multipliers, model defaults,
   cutoff isolation, immutability and portable receipt reproduction.
2. HTTP regressions cover authorization, content type/size, invalid selections,
   no-path authority, cleanup and the real inspect → checkpoint → save → export
   → fresh-server reproduce loop.
3. Browser regressions cover successful review/open and stale/failed/canceled
   requests; actual local browser rehearsal uses bundled synthetic captures.
4. Study tooling refuses overwrite, binds exact committed artifacts, freezes
   separate materials and blank scorecards, and verifies the saved kit directly.
   Build twice with the same source epoch; compare wheel bytes. Install the
   locked wheel outside the checkout and run offline checks.
5. Compilation, full unittest suite, documentation links, whitespace, numerical
   evidence, distribution checks, independent diff review and final-head hosted
   jobs pass before the authorized merge. Verify merged main and remote equality.

Feature branch → reviewed PR → final-head checks → merge → merged-tree checks.
Recover by reverting the merge and retaining original captures, study bundles
and matching research builds. No migration or provider-readiness promotion.

## Evidence

Local acceptance passes 673 methods, including 36 new intake, browser, real
HTTP and study-kit regressions. Compilation, documentation/heading links,
whitespace and numerical evidence pass. Independent review repaired overflow
JSON numbers, cancellation retention, opaque contract linkage/log privacy and
raw-preview versus accepted-state time labeling. Initial hosted checks exposed
two test fixtures depending on ambient build-tool metadata; explicit fixture
versions repair them, and all eight corrected-source jobs pass.

[The dated study record](../studies/guided-intake-2026-10-18.md) binds source
`0ddfbc4c0d94dd09935590ccb00db5d980863151`, the exact wheel, separate cohort
`guided-intake-2026-10-18-r1`, frozen materials and dependency versions. Two
clean exports produce identical wheels; the final kit's 86-file inventory and
all ZIP entry bytes verify directly. The September kit's 219 files also verify.
The installed final wheel passes 16 independent functional/keyboard checks;
actual browser intake/save/export and a fresh final-wheel browser receipt
reproduction pass. The frozen execution record contains 23 explicit preparation
checks and zero participants. A rejected rehearsal envelope remains preserved
under its failed identity; the corrected final kit uses a new one.

[PR #41](https://github.com/zrack/gex-terminal/pull/41) owns the final reviewed
head and merge. This packet closes the bounded implementation with its
explicitly authorized merge, conditional on every final-head Ubuntu/macOS and
Python 3.11/3.12 hosted job passing. Final merged-tree checks and remote equality
are retained afterward in `dist/guided-intake/2026-10-18/summary.json`.
Six actual observed sessions and issue #4's actual payload gate remain open.

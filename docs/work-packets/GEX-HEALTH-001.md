# GEX-HEALTH-001 — Instrument Identity

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: ready for contributor review
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@4c79f1f
branch: codex/gex-health-001-instrument-identity
created: 2026-09-04
```

## Authority and scope

The maintainer authorized correctness repairs, all repository-owned offline
roadmap work, documentation, and contributor commit/PR/merge/push cycles. This
first independently mergeable slice closes H1 from the application review. It
does not authorize live connections, licensed capture, readiness promotion,
customer-evidence claims, or package-registry publication.

## Contract and acceptance

Adopt INV-01 through INV-08 of the adoption profile. Preserve model math,
consumer state ownership, and separated position sources.

- Seeded legacy demonstration data is ES-only; another symbol fails before
  state mutation or artifact creation.
- Bundled replay identity owns its symbol and fallback multiplier, reused by
  CLI, terminal, journal, store, and Demo Lab. Explicit conflicting overrides
  fail; catalog selection can replace an unrelated environment default.
- Snapshot v2 receives additive multiplier provenance: configured fallback,
  effective distinct multipliers, homogeneous effective value (null for mixed),
  selected row identities and their explicit/fallback source. The existing
  top-level `contract_multiplier` remains a compatibility fallback field and is
  explicitly labeled as such; it must not be presented as actual row input.
- Legacy/mixed legacy calculation reports the fallback actually used. Missing
  provenance on externally supplied old engine dictionaries is unreported,
  not invented contract provenance.
- Known contract multipliers cannot change across updates or position sources;
  missing metadata may be enriched, but later omissions retain known values.
  Snapshot construction rejects a fallback argument inconsistent with the
  engine's recorded calculation fallback.
- Public ES/NQ demo and replay workflows, SPY fixture exports, and heterogeneous
  multiplier regressions prove identity without claiming live NQ support.

## Verification and recovery

Run focused identity/consumer/export tests, the full suite, source compilation,
model evidence, and diff hygiene before the contributor PR. Await hosted
Python 3.11/3.12 checks, merge preserving history, pull clean main and repeat
the suite. Record results below. A revert of this merge restores the prior
implementation; no stored artifacts are migrated or overwritten.

## Evidence

- September 4 branch verification: all 314 tests, compileall, diff hygiene,
  numerical model evidence, and offline Databento certification passed.
- Independent review found mutable contract multipliers, inconsistent caller
  fallback arguments, and incomplete Markdown provenance. All three were
  repaired with regressions before the full gate.
- Public SPY fixture export records effective multiplier 100 and configured
  fallback 50. ES/NQ demo, selected replay, screenshot, and saved-store identity
  cases are covered by public-workflow tests.
- Hosted checks and merged-main verification remain pending at this commit.

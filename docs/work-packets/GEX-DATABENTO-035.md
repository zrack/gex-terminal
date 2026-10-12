# GEX-DATABENTO-035 — Databento Contract And Statistics Correctness

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: "Open — offline verified; protected-branch integration pending"
baseline: main@c7f0c0b
branch: codex/databento-issue-35
created: 2026-10-11
packet_owner: project maintainer
spec_steward: implementation agent
architecture_authority: project maintainer
evidence_reviewer: independent review and hosted CI
external_outcome: "Open — credentialed provider observation"
```

## Authorization And Routing

The maintainer requested fixes for all three problems in
[issue #35](https://github.com/zrack/gex-terminal/issues/35), regression tests,
documentation updates, a commit, and closure of
[issue #5](https://github.com/zrack/gex-terminal/issues/5) with links to completed
fixture work. This is L3 because reference-session and deletion semantics add
optional metadata to the normalized contract and affect canonical OI state.
The change does not authorize paid/live access, a protected-branch merge, a
version promotion, a tag, or a release.

## Problem And Intended Outcome

Databento's deliverable multiplier is currently interpreted as a dollar
multiplier, including its undefined sentinel. A single quarterly option parent
misses the other ES/NQ products, and product codes are mistaken for futures
underlying identity. OI statistics discard deletion and reference-session
metadata, accept undefined quantities, and can overwrite newer-reference OI
with a later publication for an older date.

The repaired path uses dollar contract metadata or an explicit configured
fallback, selects a declared option-product universe, preserves futures
underlying identity, and orders OI by reference session and publication time.
Deleted OI becomes an invalidated zero tombstone, separate from a valid zero OI
observation and from independent trade volume.

## Invariants And Compatibility

Adopt INV-01 through INV-08 from the
[adoption profile](../SAED_ADOPTION_PROFILE.md). Mutable market state remains
owned by `StatefulGexConsumer`. Model equations, application version `0.6.0`,
legacy normalized messages, release tags, and provider readiness remain at
their existing boundaries. Optional reference/action metadata extends schema
v2 compatibly; Databento's provider-shaped statistics require valid reference
metadata. Fixtures are synthetic and public SDK records are constructed
locally without provider I/O.

## Acceptance And Evidence

| Requirement | Acceptance evidence | Status |
| --- | --- | --- |
| Dollar multiplier excludes provider deliverable fields and undefined values | Real SDK definition and ES/NQ consumer/GEX regression tests | Offline verified |
| Subscriptions cover declared quarterly, daily, weekly and month-end products | Subscription sets, product identity, unrelated-product and futures-month tests | Offline verified |
| OI honors add/delete, reference date, zero and undefined quantity | Mapper, SDK object, consumer ordering and deletion regression tests | Offline verified |
| Existing contracts and offline workflows continue to pass | Full source suite, compile, model evidence, provider certification and documentation checks | Offline verified |
| Documentation matches behavior and proof ceiling | Canonical adapter, mapping and architecture docs | Verified |
| Changes are reviewable and issue #5 links completed work | Feature branch history, its pull request and issue #5 discussion own delivery identities/state | Tracked in GitHub |

## Local Verification — October 11, 2026

- 568 source tests passed, including 39 new regression tests. The two real SDK
  record tests ran with Databento 0.83.0 / databento-dbn 0.65.0. CI installs the
  optional SDK so these tests also run in every source matrix job.
- The initial 15 end-to-end tests were run in an isolated archive of baseline
  `c7f0c0b` and failed with 31 failed subcases and 4 errors, reproducing the
  multiplier, parent-family and OI defects before repair.
- Independent review found an OI futures-month guard bypass. OI additions now
  require a matching observed futures quote; bootstrap and mismatch inputs are
  dropped without buffering. Deletions can invalidate retained OI without a
  current quote. Both arrival orders and deletion without quote are covered.
- Source compile and patch hygiene passed. Five local Markdown destination
  tests passed. Numerical model evidence passed with predictive validity still
  `unmeasured`; 12 offline Databento cases and all 7 provider fault cases passed.
- The first sandboxed suite encountered local socket restrictions in existing
  launcher/server tests. The final full suite passed with loopback access.
- Local evidence: `/tmp/gex35-tests-final.log`,
  `/tmp/gex35-model-evidence.json`, `/tmp/gex35-offline-certify.json`, and
  `/tmp/gex35-provider-faults.json`. These are disposable local outputs.

Hosted checks and protected-branch merge remain integration evidence, separate
from the completed offline implementation. GitHub records the exact delivered
commit, review discussion, check results and issue closure.

## Recovery And Evidence Ceiling

Revert the feature commit to recover the previous implementation. No user data
migration is performed. Offline tests prove parser/state/calculation behavior;
they do not establish live credentials, current option-family availability,
entitlements, latency, predictive validity, or financial outcomes. Hosted CI and
maintainer merge remain separate integration gates.

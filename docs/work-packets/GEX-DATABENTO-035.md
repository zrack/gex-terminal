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

The maintainer subsequently authorized the proposed offline functional,
parameter, generated-sequence, rollover/reconnect, binary-format and provider
load test package. This amendment includes repair of the reproduced rollover
gap: retained positions must never be priced against another futures contract.
Fresh-wheel public CLI and terminal checks must verify the installed application
outside the source checkout. Live reconciliation remains a separate external
observation requiring provider/data-owner authority.

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
| Retained exposure stays bound to its futures contract across rollover/reconnect | Rollover regression and session test | Offline verified |
| Parameter combinations and generated sequences agree with independent expectations | Deterministic matrix and seeded state-machine tests | Offline verified |
| Installed CLI, terminal/export and SDK binary records reproduce controlled results | Fresh-wheel functional report outside checkout | Offline verified |
| Changed provider path handles sustained family/revision/deletion traffic within declared budgets | Provider ingestion report with correctness and environment evidence | Offline verified |

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

## Expanded Offline Verification — October 11, 2026

- The final full source suite passed all 602 tests. Compile, patch hygiene,
  five Markdown destination tests, numerical evidence, twelve offline provider
  cases, seven fault cases and candidate-wheel Twine checks also passed.

- Fifteen new rollover/identity tests exercise retained trade/OI isolation,
  provider namespaces, missing IDs, reset behavior and nanosecond ordering.
  The original scenario now retains raw OI for provenance while quarantining
  its exposure when the quote moves to another futures contract.
- 1,774 parameter cases passed, including 24 real SDK cases and independent
  scalar Black-76 calculations. Four seeds checked 6,000 operations against a
  dictionary state oracle; 256 bootstrap arrivals were checked separately.
- The parameter suite found and now covers an undefined raw publication
  timestamp incorrectly interpreted as a date in 2554. Timestamp decoding now
  rejects undefined values and retains exact nanosecond ordering.
- Eighteen installed-wheel functional cases passed: ES/NQ initial, revised,
  deleted and rolled sessions through the public CLI in JSONL/DBN form,
  independent GEX, selected quantities, units/provenance and identity parity,
  plus terminal replay, visible values, keyboard export and rollover empty state.
  All 117 installed package members matched the tested candidate wheel.
  Connections were blocked in the worker and child CLI processes.
- Visible-card checks found stale terminal GEX after the active chain emptied.
  The repair clears derived metrics, quantities, expiry totals and flow while
  showing the latest quote and blocking stale exports. A dedicated UI
  regression covers the display transition.
- A larger load run passed all ten correctness/budget gates with 18,954 raw
  records across 52 families and 416 contracts: 4,741.8 records/second,
  maximum sampled snapshot 5.54 ms, peak process memory 47.53 MiB, and 624
  position states within the 832 bound. These observations apply to the
  recorded macOS ARM64/Python 3.12 environment and synthetic workload.
- Rerunnable functional and provider-load harnesses are added to the existing
  Linux/macOS/Python 3.11/3.12 CI path. Its bounded collector retains their
  report JSON without uploading the full generated input/export inventory.
- Retained local evidence is under ignored
  `dist/databento-issue-35-verification/2026-10-11/`: `summary.json`,
  `functional.json`, `provider-load.json`, candidate wheel, source-suite log,
  offline evidence and generated synthetic functional artifacts. Candidate
  bytes and source hashes identify this test build; the existing release tag
  and application version are unchanged.

The tested pricing flow has one selected provider/root per consumer. Legacy
unlinked sessions remain compatible; the new identity evidence does not certify
mixed-vendor forward equivalence. Retired mappings deliberately require a
consumer reset before reuse. Live reconciliation remains external observation.

## Hosted Compatibility Repair — October 11, 2026

The first expanded hosted matrix passed source, numerical and installed-wheel
checks but failed reproduction of a real `0.5.0` Demo Lab pack. An empty
`underlying_identity` feed-quality field changed the saved snapshot/replay
decision hashes for identity-free historical inputs. Reports now emit this
field only when identity evidence exists; receipt canonicalization and integrity
checks remain unchanged. Regression coverage verifies legacy omission, tracked
contract reporting, quarantine without a quote, and reset behavior.

The repaired installed wheel passed the real `0.5.0` producer compatibility
gate: Demo Lab verification/reproduction, experiment reproduction and byte
preservation of all 22 original files. All eighteen Databento functional cases
and ten default provider-load gates also passed. Independent review confirmed
the complete historical replay decision content matches. The final source suite
passed all 603 tests; compile, documentation links and patch hygiene passed.
Repair evidence is retained in the same ignored verification directory under
`ci-repair/`. The revised hosted matrix remains the final integration check
before maintainer merge.

## Recovery And Evidence Ceiling

Revert the feature commit to recover the previous implementation. No user data
migration is performed. Offline tests prove parser/state/calculation behavior;
they do not establish live credentials, current option-family availability,
entitlements, latency, predictive validity, or financial outcomes. Hosted CI and
maintainer merge remain separate integration gates.

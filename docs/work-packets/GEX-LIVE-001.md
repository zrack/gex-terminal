# GEX-LIVE-001 — Pre-Live Certification Hardening

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
adoption_context: team
change_rigor: L3
status: "Closed — repository release shipped; external observation open"
packet_owner: project maintainer
spec_steward: implementation agent
architecture_authority: project maintainer
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@360abdc
branch: codex/gex-live-001-prelive-v0.4.0
feature_pull_request: 14
feature_merge: main@e58511cf652a5dcfe3326869987b6b9a8d34f890
closeout_branch: codex/gex-live-001-prelive-v0.4.0-closeout
closeout_pull_request: 15
target_release: "0.4.0 Pre-Live Certification Hardening"
release_tag: v0.4.0
created: 2026-08-31
external_outcome: "Open — credentialed provider observation"
```

## Authorization And Routing

The maintainer authorized every repository-owned pre-live hardening item named
in the roadmap review: a versioned certification policy, deterministic
adapter-lifecycle evidence, explicit OI and IV reporting, production logging
and redaction controls, separate ES/NQ certification profiles, and a retention,
licensing, and redaction decision before capture. The maintainer also authorized
a clean pull, an isolated contributor branch/worktree, branch verification,
merge to `main`, merged-tree verification, version promotion, an annotated Git
tag, and publication of the branch, merged `main`, and tag to `origin`.

This is `L3` because it changes enforced certification thresholds, credential
and licensed-data safeguards, provider diagnostics, and the release identity.
It does not authorize provider credentials, paid entitlements, live network
testing, retention of licensed observations, readiness promotion, PyPI
publication, or a hosted GitHub Release.

## Problem And Intended Outcome

The existing Databento probe can pass chain ingestion after observing only one
definition, one underlying quote, one option trade, and one normalized option
state. It does not predeclare meaningful chain breadth, report distinct
expiry/strike coverage, expose OI availability as a state, measure IV-source
coverage, or exercise the adapter lifecycle through a scripted provider client.
Its exception redaction is limited to exact API-key replacement.

Version `0.4.0` lets contributors test a versioned, fail-closed certification
contract entirely offline. A report carries its policy, target identity,
coverage measurements, OI status, IV provenance, lifecycle diagnostics, and
evidence ceiling. Scripted clients prove deterministic behavior for
success, entitlement rejection, disconnect, malformed input, cancellation, and
shutdown paths. None of this changes Databento from `live-uncertified`.

## Scope

- Versioned ES and NQ certification profiles with canonical multipliers and
  explicit minimum chain, freshness, sequence, and IV thresholds.
- A certification report that evaluates the selected profile and records all
  thresholds beside observed values.
- Explicit OI status and statistics-subscription diagnostics without combining
  OI and trade volume or inferring provider availability.
- Separate native-provider, Black-76-inverted, configured-fallback, inversion-
  failure, and underlying-age measurements.
- Scripted Databento lifecycle tests covering subscription, entitlement,
  disconnect, reconnect/resubscription signals where exposed, cancellation,
  provider errors, malformed records, and clean stop behavior.
- Configurable logging with safe defaults and adversarial credential,
  identifier, and payload redaction checks.
- A pre-capture policy for rights, retention, redaction, and research use.
- Architecture, provider, offline-validation, contributor, roadmap, changelog,
  and release-contract reconciliation.
- Contributor branch review boundary, merge to `main`, merged-tree release
  verification, version `0.4.0`, and annotated tag `v0.4.0`.

## Non-Goals

- A credentialed Databento connection or claim about current authentication,
  entitlements, active ES/NQ chains, payload drift, latency, or reconnects.
- Proof that Databento supplies licensed live OI for the requested symbols.
- Retaining or committing licensed market data, account data, or credentials.
- Dealer/customer inventory inference, predictive promotion, execution claims,
  or profitability claims.
- Multi-symbol scanning, hosted alerts, higher Greeks, REST/MCP publication,
  PyPI publication, or a GitHub Release.

## Invariants

This packet adopts `INV-01` through `INV-08` from
`docs/SAED_ADOPTION_PROFILE.md` and adds:

- `INV-12` — Offline success never changes the Databento registry status from
  `live-uncertified` and never sets live transport certification true.
- `INV-13` — Certification thresholds are versioned, selected before a run,
  emitted in the report, and evaluated fail closed.
- `INV-14` — OI availability is explicit; unavailable or unobserved OI is never
  replaced by, summed with, or relabeled as trade volume.
- `INV-15` — Provider IV, Black-76 inversion, and configured fallback remain
  separately counted; fallback use cannot satisfy the quantitative-input gate.
- `INV-16` — Credentials, account identifiers, subscription identifiers, and
  licensed payload fragments are redacted before report or log emission.
- `INV-17` — ES and NQ use separate certification profiles and canonical
  multipliers; a result for one symbol cannot certify the other.

## Requirements And Acceptance

| ID | Requirement / Acceptance Criterion | Evidence | Status |
| --- | --- | --- | --- |
| `REQ-01` | A versioned policy defines supported ES/NQ targets, canonical multipliers, and quantitative thresholds. | Policy tests | Verified |
| `AC-01` | Unknown policies, symbols, multiplier mismatches, invalid thresholds, and insufficient coverage fail closed. | Positive/negative report tests | Verified |
| `REQ-02` | Reports include distinct expiry/strike counts, freshness/sequence measurements, and observed-versus-required coverage. | Report schema tests | Verified |
| `REQ-03` | OI status distinguishes observed, unavailable, unsupported, entitlement-denied, and not-requested states. | Adapter/report tests | Verified |
| `AC-02` | OI and trade volume remain separate throughout adapter, consumer, and report paths. | Contract/regression tests | Verified |
| `REQ-04` | IV provenance reports native, inverted, fallback, failure, age, and coverage measurements separately. | Adapter/report tests | Verified |
| `REQ-05` | Scripted clients exercise connection, subscription, entitlement, provider-error, malformed-record, reconnect callback, post-reconnect observation, cancellation, and bounded stop/close behavior. | Lifecycle test matrix | Verified |
| `AC-03` | Diagnostics remain bounded to observed callbacks and do not claim real provider behavior or reinterpret request IDs as acknowledgements. | Evidence-ceiling assertions | Verified |
| `REQ-06` | Logging level is configurable and report/log redaction covers secrets and sensitive identifiers recursively. | Redaction and CLI tests | Verified |
| `REQ-07` | Capture governance rejects ambiguous rights/retention/redaction/research-use declarations and captured-session corpus mismatches. | Policy/corpus tests and guide | Verified |
| `AC-04` | Full source, behavioral, offline-provider, research, performance, distribution, and documentation gates pass on branch and merged `main`. | Release evidence | Verified |
| `AC-05` | Version, changelog, package metadata, merged commit, and annotated `v0.4.0` tag agree. | Release identity checks | Verified at release closeout |

## Architecture Delta

Canonical market state remains owned by `StatefulGexConsumer`, and model math
remains unchanged. The certification boundary gains an explicit policy and
sanitization layer:

```text
target symbol -> versioned certification profile -> Databento adapter
                                                     |
scripted/live records -> normalized messages -> consumer diagnostics
                                                     |
observations + policy -> redacted certification report -> fail-closed result
```

Scripted clients are deterministic test doubles, not captured live evidence.
The report is derived; policy definitions and normalized contracts remain the
authorities for their respective fields.

## Bounded Slices

| Slice | Deliverable | Evidence | Fallback / Stop Point |
| --- | --- | --- | --- |
| `S1` Route | Packet, baseline, branch, release authority | Structural review | Stop before runtime edits if authority is unclear |
| `S2` Contract | Versioned profiles, thresholds, report schema | Policy/report tests | Retain existing probe and do not promote it |
| `S3` Provider diagnostics | OI/IV metrics and scripted lifecycle coverage | Adapter/lifecycle tests | Report unavailable/unobserved states explicitly |
| `S4` Safety | Logging controls, recursive redaction, capture policy | Adversarial safety tests | Block report emission or capture on ambiguity |
| `S5` Truth | Architecture/operator/contributor/release reconciliation | Link and release tests | Keep roadmap/live status open |
| `S6` Release | Branch commit/review, merge, merged gates, `v0.4.0` tag | Git and package evidence | Do not tag or push on a failed critical gate |

## Risks And Controls

| ID | Risk | Control / Recovery |
| --- | --- | --- |
| `RISK-01` | Richer synthetic evidence is mistaken for live readiness. | Hard-code registry/evidence ceilings and preserve `live-uncertified`. |
| `RISK-02` | Threshold defaults appear empirically validated. | Label them bounded certification-policy choices; retain them in every report. |
| `RISK-03` | SDK behavior differs from scripted clients. | Limit claims to tested callbacks and require a later credentialed run. |
| `RISK-04` | Sensitive data leaks through nested errors or identifiers. | Central recursive sanitizer plus adversarial nested-string tests. |
| `RISK-05` | ES results are generalized to NQ. | Separate profiles, multiplier validation, and per-symbol reports. |
| `RISK-06` | Release mechanics outrun review evidence. | Branch review, merged-tree gates, tag only the verified merged commit. |

## Verification And Release Plan

1. Run focused policy, certification, adapter, lifecycle, logging, redaction,
   and capture-policy tests after each slice.
2. Run compileall, the full unit suite, `git diff --check`, model evidence,
   Databento offline certification, property/fault/performance reports, and
   documentation-link checks on the branch.
3. Build source and wheel distributions, run Twine metadata validation, and
   exercise the installed wheel from outside the checkout.
4. Push the contributor branch and establish a pull-request/review boundary.
5. Merge the reviewed branch into `main` while preserving branch history.
6. Re-run the complete gate from clean merged `main`.
7. Confirm version/changelog/runtime/package identity, create annotated
   `v0.4.0` on the verified merge commit, then push `main`, branch, and tag.

Rollback is a Git revert of the merge commit; the tag identifies the verified
release tree. No user data or licensed market data is migrated.

## Amendments

- 2026-08-31 — The evidence-only closeout records the reviewed feature merge,
  clean merged-tree gates, narrow closeout pull request, and authorized release
  tag. It changes no implementation scope, invariant, or evidence ceiling.

## Evidence

Repository evidence:

- `gex_terminal/databento_certification_policy.py` owns versioned ES/NQ target
  identity, canonical multipliers, and repository-chosen thresholds;
  `tests/test_databento_certification_policy.py` and
  `tests/test_databento_certification.py` exercise fail-closed selection and
  report evaluation.
- `gex_terminal/adapters/databento.py` exposes required/optional request
  outcomes, explicit OI states, IV/age metrics, provider-flag sequence evidence,
  reconnect callback boundaries, post-reconnect frames, and bounded
  `wait_for_close`; `tests/test_databento_live.py` uses scripted clients to cover
  those paths. Returned request IDs are submission evidence, not
  acknowledgements.
- `gex_terminal/logging_config.py` and `gex_terminal/redaction.py` provide safe
  defaults and recursive sanitization; `tests/test_safety_controls.py` covers
  nested secrets, identifiers, payload labels, and CLI configuration.
- `gex_terminal/capture_governance.py` binds live captures to explicit policy
  identity. `gex_terminal/research_corpus.py` requires an exact embedded-policy
  match, approved research use, matching rights/redistribution metadata, and
  verified redaction; focused governance and corpus tests exercise rejection.
- The complete branch gate passed on 2026-08-31: source compilation, patch
  hygiene, all 297 unit tests, model evidence, Databento offline certification,
  all 7 model-property checks, all 7 provider-fault scenarios, the generated
  500-contract performance budget, documentation links, and screenshot export.
  Offline reports retained `live_transport=false`, `live_capacity=false`, and
  `predictive_validity=unmeasured` where applicable.
- The `0.4.0` wheel and source distribution both passed Twine validation. A
  fresh Python 3.12 environment installed the wheel outside the checkout and
  passed every installed-wheel smoke command in CI, including packaged-resource
  discovery, capture-policy validation, offline Databento certification,
  property/fault/performance gates, experiment reproduction, batch comparison,
  and corpus registration/verification. Persisted outputs contained no checkout
  or site-packages paths.
- Contributor pull request
  [#14](https://github.com/zrack/gex-terminal/pull/14) passed its Python 3.11 and
  3.12 hosted checks and merged with commit
  `e58511cf652a5dcfe3326869987b6b9a8d34f890`, preserving the three contributor
  commits. The original `main` checkout then fast-forwarded cleanly from
  `origin/main` without modifying its pre-existing untracked image files.
- The merged tree passed source compilation, patch hygiene, all 297 unit tests,
  model evidence, offline Databento certification, 7/7 model properties, 7/7
  provider faults, the 500-contract performance budget, documentation links,
  screenshot export, isolated wheel/source build, and Twine validation. The
  [hosted merged-main run](https://github.com/zrack/gex-terminal/actions/runs/33474249035)
  also passed both supported Python versions.
- Documentation-only closeout pull request
  [#15](https://github.com/zrack/gex-terminal/pull/15) records actual release
  evidence. Its merge commit is the annotated `v0.4.0` target; the tag is pushed
  only after that merge is re-read from clean `main` and its identity checks
  pass.

External evidence remains deliberately absent. No credentialed Databento run,
licensed OI observation, provider-side resubscription result, recurring service
window, readiness promotion, retained market-data corpus, or predictive result
is claimed. Those outcomes are the remaining roadmap work and require separate
authority.

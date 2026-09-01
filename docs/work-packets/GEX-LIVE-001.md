# GEX-LIVE-001 — Pre-Live Certification Hardening

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
adoption_context: team
change_rigor: L3
status: Build / Validate
packet_owner: project maintainer
spec_steward: implementation agent
architecture_authority: project maintainer
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@360abdc
branch: codex/gex-live-001-prelive-v0.4.0
target_release: "0.4.0 Pre-Live Certification Hardening"
created: 2026-08-31
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

After this change, contributors can test a versioned, fail-closed certification
contract entirely offline. A report will carry its policy, target identity,
coverage measurements, OI status, IV provenance, lifecycle diagnostics, and
evidence ceiling. Scripted clients will prove deterministic behavior for
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
| `REQ-01` | A versioned policy defines supported ES/NQ targets, canonical multipliers, and quantitative thresholds. | Policy tests | Planned |
| `AC-01` | Unknown policies, symbols, multiplier mismatches, invalid thresholds, and insufficient coverage fail closed. | Positive/negative report tests | Planned |
| `REQ-02` | Reports include distinct expiry/strike counts, freshness/sequence measurements, and observed-versus-required coverage. | Report schema tests | Planned |
| `REQ-03` | OI status distinguishes observed, unavailable, unsupported, entitlement-denied, and not-requested states. | Adapter/report tests | Planned |
| `AC-02` | OI and trade volume remain separate throughout adapter, consumer, and report paths. | Contract/regression tests | Planned |
| `REQ-04` | IV provenance reports native, inverted, fallback, failure, age, and coverage measurements separately. | Adapter/report tests | Planned |
| `REQ-05` | Scripted clients exercise connection, subscription, entitlement, provider-error, malformed-record, cancellation, and stop behavior. | Lifecycle test matrix | Planned |
| `AC-03` | Diagnostics remain bounded to observed callbacks and do not claim real provider behavior. | Evidence-ceiling assertions | Planned |
| `REQ-06` | Logging level is configurable and report/log redaction covers secrets and sensitive identifiers recursively. | Redaction and CLI tests | Planned |
| `REQ-07` | Capture governance rejects ambiguous rights/retention/redaction/research-use declarations before corpus eligibility. | Policy schema tests and guide | Planned |
| `AC-04` | Full source, behavioral, offline-provider, research, performance, distribution, and documentation gates pass on branch and merged `main`. | Release evidence | Planned |
| `AC-05` | Version, changelog, package metadata, merged commit, and annotated `v0.4.0` tag agree. | Release identity checks | Planned |

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

None at baseline. Material scope, invariant, authority, proof-ceiling, version,
or recovery changes must be appended before implementation continues.

## Evidence

Pending implementation and branch verification.

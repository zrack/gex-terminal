# GEX-HEALTH-002 — Configuration And Offline Health Truth

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
adoption_context: team
change_rigor: L3
status: closed
packet_owner: project maintainer
spec_steward: implementation agent
architecture_authority: project maintainer
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@4c79f1f
branch: codex/gex-health-002-config-truth
created: 2026-09-04
external_outcome: "Not applicable — offline correctness only"
```

## Authorization And Routing

The maintainer authorized the repository-owned H2 repair identified in the
September 4 application review: validate configuration before runtime or
export, produce actionable errors without echoing supplied values, and make
offline provider injection visibly simulated. Work is isolated on the named
contributor branch and will be integrated through a later reviewed pull
request. No credentialed provider call, live observation, readiness promotion,
release tag, or publication is authorized by this packet.

This is routed as `L3` because it changes the enforced configuration boundary
and the meaning of durable provider-health evidence. The implementation keeps
mutable market state in `StatefulGexConsumer`, preserves provider mapping
paths, and leaves the deliberately scripted live lifecycle harness unchanged.

## Problem And Intended Outcome

Malformed numeric environment values currently fall back to plausible
defaults, while nonfinite values can reach stale detection. A nonfinite stale
threshold can cause old data to appear healthy. Direct `GexConfig`
construction and command-line overrides do not share one complete invariant
check.

Separately, local provider-shaped fixtures are injected through a consumer
labeled `LIVE` and `CONNECTED`, so a no-network artifact can report healthy
live state. After this change, every runtime/export configuration fails closed
on invalid numeric assumptions, public errors identify the field and expected
constraint without repeating its raw value, and provider fixture artifacts
state their offline origin and simulated runtime unambiguously.

## Scope

- One `GexConfig` validation boundary for environment loading, direct
  construction, and `dataclasses.replace` command/UI overrides.
- Strict required and optional numeric parsing with finite/domain checks.
- Secret-safe, actionable command-line configuration failures.
- Defensive stale-threshold validation at consumer and feed-quality ingress.
- Explicit offline origin, no-network evidence, and replay/simulated runtime
  semantics for provider fixture injection and its workbench exports.
- Focused unit, CLI, fixture, release-contract, and scripted-fault regression
  evidence plus canonical provider-injection/configuration documentation.

## Non-Goals

- Symbol/multiplier identity redesign, instrument-profile policy, or changes to
  model calculations.
- Replay task ownership, experiment identity, replay chronology, or terminal
  layout repairs from other health findings.
- Credentialed provider testing, provider readiness changes, retained market
  data, predictive claims, or profitability claims.
- Requiring a replay path to exist during intermediate configuration assembly;
  adapters continue to validate paths at execution time.
- Inventing an empirical bound for a finite risk-free rate.

## Invariants

This packet adopts `INV-01` through `INV-08` from
`docs/SAED_ADOPTION_PROFILE.md` and adds:

- `INV-21` — Invalid required numeric configuration never becomes a default;
  only absence selects a default, and only an absent or blank optional value
  becomes `None`.
- `INV-22` — Runtime timing and expiry values are finite and inside their
  declared positive or non-negative domains before work begins.
- `INV-23` — Public configuration errors identify only the field and safe
  constraint, never the supplied environment or command-line value.
- `INV-24` — Offline provider fixtures never emit `LIVE`, claim a network
  connection, or count simulated execution as observed provider health.
- `INV-25` — Scripted live lifecycle cases remain explicitly synthetic and
  cannot set `live_transport_certified=true`.

## Requirements And Acceptance

| ID | Requirement / Acceptance Criterion | Evidence | Status |
| --- | --- | --- | --- |
| `REQ-01` | `GexConfig` rejects nonfinite and out-of-domain multiplier, rate, expiry, refresh, stale, replay-delay, replay-speed, and replay-gap values on direct construction. | Table-driven configuration tests | Verified |
| `AC-01` | Multiplier is a positive integer; rate is finite; expiry, refresh, stale, and replay speed are finite and positive; replay delay and optional max gap are finite and non-negative. | Boundary tests | Verified |
| `REQ-02` | Environment parsing distinguishes absent defaults and optional blanks from malformed values. | Environment tests | Verified |
| `REQ-03` | CLI overrides use the same invariant boundary and fail with a concise nonzero result, no traceback, and no raw supplied sentinel. | Adversarial subprocess tests | Verified |
| `AC-02` | An invalid stale threshold cannot yield a healthy feed-quality result through supported config, consumer, or direct feed-quality entry points. | Consumer/feed-quality tests | Verified |
| `REQ-04` | Provider injection records an offline fixture source, `network_used=false`, and replay/simulated or degraded health rather than live/connected health. | Public injection export and summary tests | Verified |
| `AC-03` | Fixture-lab summaries and scorecards distinguish mapping pass, simulated runtime, and degraded parser/model evidence. | Workbench JSON/CSV/Markdown tests | Verified |
| `AC-04` | Provider fault certification still passes every scripted case and retains `live_transport_certified=false`. | Offline fault gate | Verified |
| `AC-05` | Focused tests, full discovery, source compilation, patch hygiene, and installed-wheel offline smoke pass. | Branch evidence | Verified |

## Architecture Delta

Configuration validation becomes an ingress contract rather than a downstream
side effect:

```text
environment / CLI / direct constructor
              |
              v
       validated GexConfig
              |
              +--> consumer/feed-quality guards
              |
local provider fixture --> adapter mapping --> consumer/engine --> artifact
       source=offline fixture                 status=REPLAY, network=false
```

The provider identifier continues to describe the parser/mapping under test;
it does not describe an observed connection or provider readiness. Scripted
fault certification retains its intentionally live-shaped state transitions
under an explicit no-network evidence ceiling.

## Bounded Slices

| Slice | Deliverable | Evidence | Fallback / Stop Point |
| --- | --- | --- | --- |
| `S1` Route | Accepted packet, baseline, branch, invariants | Structural review | Stop before runtime edits if scope changes |
| `S2` Config | Strict parsers and direct-construction validation | Config and CLI tests | Keep prior defaults only for absent values |
| `S3` Health | Consumer/feed-quality ingress guards | Stale/nonfinite tests | Fail closed rather than guess health |
| `S4` Fixture truth | Offline metadata, runtime semantics, summaries | Injection/workbench/fault tests | Preserve parser counters and fault harness |
| `S5` Reconcile | Canonical guide and generated example | Link/content review | Do not duplicate roadmap or architecture |
| `S6` Verify | Focused/full/package checks and contributor commit | Exact branch evidence | Do not integrate on failed critical gate |

## Risks And Controls

| ID | Risk | Control / Recovery |
| --- | --- | --- |
| `RISK-01` | New checks reject an intentional boundary such as zero replay delay. | Encode positive versus non-negative fields explicitly and test boundaries. |
| `RISK-02` | A validation message leaks an accidental secret used as an invalid value. | Construct messages from fixed field names and constraints; adversarially assert the sentinel is absent. |
| `RISK-03` | Offline parser evidence is mistaken for a provider connection. | Emit source kind, network use, replay status, connection state, and simulated health together. |
| `RISK-04` | Relabeling fixture execution weakens scripted lifecycle coverage. | Do not change the provider fault lifecycle case; run its complete gate. |
| `RISK-05` | Validation overlaps the instrument-identity slice. | Do not infer multiplier from symbol or change H1 identity behavior; integrate branches serially. |

## Verification And Integration Plan

1. Run focused configuration, CLI, consumer, feed-quality, injection, fixture-
   lab, release-contract, safety, and provider-fault tests.
2. Run full unit discovery, source compilation, `git diff --check`, and local
   documentation-link inspection.
3. Build source and wheel distributions, install the wheel into a temporary
   environment outside the checkout, and run only offline injection and invalid-
   configuration smoke commands.
4. Commit explicit packet, implementation, test, and canonical documentation
   paths on the contributor branch. Do not push, merge, tag, or make a live call
   in this slice.

Rollback is a Git revert of the contributor commit. No user state, licensed
market data, credentials, or external system is mutated.

## Amendments

None.

## Evidence

Integration at `main@813bb24` preserved H1 multiplier identity, H3 writer
ownership, and H5 chronology. An additional regression validates UI assumption
changes before publishing engine mutations. All 333 integrated tests,
compilation, diff hygiene, and the 7/7 provider-fault gate passed. PR #23 merged
as `51ad3a2` after all four hosted Python 3.11/3.12 checks passed. Clean merged
main passed all 333 tests and compilation. No live-readiness status changed.

Repository evidence on the isolated contributor branch:

- Focused configuration, CLI, feed-quality, injection, fixture-lab,
  release-contract, and safety coverage passed all 50 tests, including
  secret-shaped invalid environment and command-line values that were absent
  from stderr and produced no traceback.
- Full unit discovery passed all 309 tests. Source compilation and
  `git diff --check` also passed.
- The regenerated fixture-lab example passed 5/5 mappings while reporting zero
  healthy-live cases, three simulated cases, and two degraded cases. Every row
  reports replay mode and no network use; exported injection evidence reports
  an offline fixture source and a disconnected consumer.
- The unchanged scripted provider-fault suite retained its deliberately
  synthetic lifecycle coverage and `live_transport_certified=false` ceiling.
- Source and wheel distributions built successfully and both passed Twine
  validation. The wheel was installed outside the checkout; its offline
  provider-injection command emitted replay/disconnected/simulated truth, and
  its adversarial invalid-environment command failed concisely without the raw
  sentinel or a traceback.

No credentialed provider call or network-backed market-data observation was
performed. This evidence establishes repository behavior only; it cannot
certify live transport, provider capacity, or predictive validity.

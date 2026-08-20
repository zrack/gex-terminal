# GEX-ORC-001 — Offline Research Certification Workbench

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
adoption_context: team
change_rigor: L3
status: Shipped / Validate
packet_owner: project maintainer
spec_steward: implementation agent
architecture_authority: project maintainer
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@2aec3f1
branch: codex/offline-research-certification-v0.3.0
target_release: "0.3.0 Offline Research Certification Workbench"
created: 2026-08-19
```

## Authorization And Routing

The maintainer authorized the complete offline-hardening set, documentation and
image convergence, a named branch, pull request, branch testing, merge to
`main`, merged-tree testing, versioning, and final mainline publication. The two
pre-existing working-tree edits to `ROADMAP.md` and `docs/market-analysis.md`
are preserved as in-scope product-direction input.

This is `L3` because it introduces durable experiment/corpus contracts,
append-only evidence state, declared performance budgets, a public research
workflow, and a release identity. It does not authorize credentials, paid data,
live network testing, destructive user-data migration, a Git tag, or a hosted
GitHub Release.

## Problem And Intended Outcome

The existing workbench proves deterministic calculations, normalized fixture
handling, temporal guards, and bounded offline comparisons. It does not yet
provide a reproducible experiment identity, governed corpus registration,
multi-session model comparison, broad property evidence, transport-state fault
simulation, or a declared generated-chain performance envelope.

After this change, multiple contributors can run the same versioned research
contracts, reproduce results, detect input drift or split leakage, challenge
model invariants, compare sessions without blending position sources, and
review one coherent evidence package. Claims remain bounded to software and
research-process verification.

## Scope

- Versioned model profiles and reproducible experiment manifests.
- Batch session/day/expiry/DTE position-model comparisons.
- Append-only governed corpus registration and verification.
- Deterministic property, metamorphic, and numerical differential evidence.
- Provider fault/state simulation without network access.
- Deterministic generated-chain performance budgets.
- Canonical provider-readiness vocabulary and proxy-first UI semantics.
- Installed-wheel CI coverage for every offline certification workflow.
- SAED adoption, current architecture, contributor, operator, roadmap,
  changelog, release, and generated-image convergence.

## Non-Goals

- Live authentication, entitlements, active-chain discovery, or latency proof.
- Dealer/customer or opening/closing inference without licensed evidence.
- Predictive promotion, strategy tuning, execution simulation, or P&L claims.
- New higher-Greek surfaces, scanner, hosted alerts, REST, or MCP service.
- Copying licensed market data into the repository.
- Git tag, GitHub Release, PyPI publication, or production deployment.

## Invariants

This packet adopts `INV-01` through `INV-08` from
`docs/SAED_ADOPTION_PROFILE.md` and adds:

- `INV-09` — Corpus membership is append-only and hash chained; changing a
  registered source invalidates verification rather than rewriting history.
- `INV-10` — Reproduction compares semantic output, excluding volatile report
  timestamps while preserving every decision-relevant field.
- `INV-11` — Performance certification uses generated data and reports the
  observed environment; it makes no live-feed capacity claim.

## Requirements And Acceptance

| ID | Requirement / Acceptance Criterion | Evidence | Status |
| --- | --- | --- | --- |
| `REQ-01` | A versioned profile controls model and evaluation assumptions. | Profile validation tests | Verified locally |
| `AC-01` | An experiment can run, emit input/profile/version/result digests, and reproduce to the same semantic result. | Experiment CLI and tests | Verified locally |
| `REQ-02` | Batch comparison groups sessions by declared day, expiry, and DTE layer without summing model sources. | Batch module and contract tests | Verified locally |
| `AC-02` | Missing/future timestamps and insufficient directional coverage remain visible and unscored. | Batch tests | Verified locally |
| `REQ-03` | Corpus registration records source digest, rights metadata, split, outcome definition, costs, and append-only chain identity. | Corpus tests | Verified locally |
| `AC-03` | Duplicate IDs/digests, split reassignment, source drift, broken chains, and missing files fail verification. | Adversarial corpus tests | Verified locally |
| `REQ-04` | Numerical properties cover round trips, order/scaling, state semantics, time boundaries, and nonfinite failures. | Property evidence report and tests | Verified locally |
| `REQ-05` | Provider fault simulation covers gaps, duplicates, reorder, malformed/unknown frames, disconnect/reconnect, and partial prerequisites. | Fault report and tests | Verified locally |
| `REQ-06` | Generated-chain benchmarks report throughput, snapshot latency, peak memory, environment, and declared budgets. | Performance report and tests | Verified locally |
| `AC-04` | Default CI budgets are deterministic and generous enough to detect severe regression without claiming live capacity. | Hosted/local release gate | Verified locally and hosted |
| `REQ-07` | Provider readiness and UI wording distinguish connection state, provider readiness, proxy model, and evidence ceiling. | Registry/UI/docs tests | Verified locally |
| `REQ-08` | Clean-wheel CI exercises all offline commands and package resources outside the checkout. | CI definition and branch checks | Verified locally and hosted |
| `AC-05` | README, architecture, operator docs, roadmap, changelog, contribution guide, and important generated images match shipped behavior. | Structural readback and image generation | Verified locally |
| `AC-06` | Branch tests pass; one PR is reviewed and merged; merged `main` passes the release gate at version `0.3.0`. | Git/CI/release evidence | Verified at `e7d1808` |

## Architecture Delta

Canonical market state and model math remain unchanged. New modules sit beside
the existing offline labs:

```text
versioned profile + source input
          |
          v
experiment runner ----> semantic digest + reproducible manifest
          |
          +----> existing Databento / position / price-action workflows

corpus event chain ----> verified source registry ----> batch comparison

generated contracts --> consumer + engine --> property/performance evidence

scripted faults ------> adapter + consumer --> fail-closed state evidence
```

The corpus event log is canonical for corpus membership. Corpus verification,
batch reports, experiment reports, screenshots, and architecture images are
derived and rebuildable. No server, database, credential store, or background
worker is introduced.

## Bounded Slices

| Slice | Deliverable | Evidence | Fallback / Stop Point |
| --- | --- | --- | --- |
| `S1` Governance baseline | Adoption profile and this packet | Structural review | Stop before executable changes if authority/invariants are unclear |
| `S2` Reproducible research | Profiles, experiment runner, corpus chain | Focused unit/CLI tests | Remove new modules; existing labs remain unchanged |
| `S3` Comparative research | Batch comparison and grouped summaries | Source-separation and cutoff tests | Retain single-session comparison |
| `S4` Fitness evidence | Property, fault, and performance certification | Deterministic reports/tests | Keep reports advisory if stable budgets cannot be established |
| `S5` Product truth | Readiness vocabulary, proxy semantics, docs/images | UI/registry tests and generated readback | Preserve runtime connection states |
| `S6` Release convergence | Wheel CI, full tests, PR, merge, `0.3.0` | Hosted/local release gate | Do not merge/version on failed critical evidence |

## Risks And Controls

| ID | Risk | Control / Recovery |
| --- | --- | --- |
| `RISK-01` | Synthetic evidence is mistaken for market validity. | Hard-coded evidence ceilings and no promotion fields. |
| `RISK-02` | New manifests duplicate canonical state. | Inputs/corpus events are canonical; reports declare derived status and repair path. |
| `RISK-03` | Performance thresholds become environment-flaky. | Record environment, use deterministic inputs, generous default budgets, and separate observed values from claims. |
| `RISK-04` | Licensed or private paths leak into artifacts. | Store operator-supplied references only in local corpus state; tests use packaged fixtures; committed examples are sanitized. |
| `RISK-05` | Readiness renaming breaks connection-state behavior. | Keep runtime `LIVE/SIM/STALE/DISCONNECTED` separate and regression tested. |
| `RISK-06` | Cross-cutting work obscures contributor review. | One packet, bounded commits/slices, traceability, architecture diagram, and coherent PR review. |

## Verification And Release Plan

1. Focused tests after each slice.
2. Full unit suite, compileall, `git diff --check`, model evidence, offline
   Databento certification, property/fault/performance reports, and screenshot
   generation on the branch.
3. Source and wheel build, Twine metadata, and clean-wheel command smoke outside
   the checkout.
4. Push one branch and open one ready pull request against `main`.
5. Inspect PR diff and hosted checks; repair within this packet if necessary.
6. Merge, switch to updated `main`, and repeat the complete release gate.
7. Confirm `pyproject.toml`, runtime `--version`, changelog, package metadata,
   branch/merge identity, and `origin/main` agree on `0.3.0`.

Rollback is a Git revert of the merge/release commit. Local corpus or experiment
outputs are outside the repository by default and remain operator-owned.

## Amendments

None at baseline. Material scope, invariant, authority, proof-ceiling, or
recovery changes must be appended here before closeout.

## Branch Evidence

- `python -m compileall main.py gex_terminal tests`: passed.
- `python -m unittest discover -s tests`: 242 tests passed.
- Model property certification: 7/7 checks passed.
- Provider fault certification: 7/7 cases passed; live transport false.
- Default 500-contract generated performance gate: passed; live capacity false.
- Model evidence and 12-case Databento offline certification: passed;
  predictive validity unmeasured and live transport false.
- Source distribution and wheel built as `0.3.0`; both passed Twine validation.
- Fresh Python 3.14 wheel installation outside the checkout ran the packaged
  experiment/reproduction, batch, corpus, property, fault, performance,
  Databento replay/certification, position comparison, and price-action paths.
- Product and onboarding screenshots, demo preview, social PNG/SVG, GEX proxy
  mockup, and research architecture diagram were regenerated and inspected.
- Pull request [#12](https://github.com/zrack/gex-terminal/pull/12) was reviewed
  with no blocking findings and merged through GitHub as `e7d1808` after both
  hosted Python 3.11 and 3.12 jobs passed every required step.
- The exact merged `main` tree passed compileall, patch hygiene, all 242 tests,
  model evidence, the twelve-case offline Databento matrix, 7/7 property
  checks, 7/7 fault cases, the default 500-contract performance budget,
  experiment reproduction, batch comparison, corpus verification, screenshot
  export, source/wheel build, Twine checks, and fresh installed-wheel smoke.

## Closeout

Status is `Shipped / Validate`.

- **Specified versus shipped:** No material product, architecture, invariant,
  or evidence-ceiling difference. The GitHub integration could read the PR and
  CI but could not merge it, so the explicitly approved merge used the signed-in
  GitHub interface. This changed the execution surface, not the reviewed commit
  or acceptance evidence.
- **Release identity:** `0.3.0 Offline Research Certification Workbench` at
  merge commit `e7d1808493a4e16302119ba95721746c1284a0b5`, delivered by PR #12.
  No Git tag, GitHub Release, PyPI publication, or deployment is claimed.
- **External validation deferred:** Authentication, entitlements, active ES/NQ
  chain coverage, real reconnect and latency behavior, licensed participant
  state, predictive validity, execution quality, and profitability remain
  unverified. `predictive_validity` remains `unmeasured` and provider readiness
  is not promoted by this release.
- **Continuation condition:** Open a new routed packet before any credentialed
  live certification, real-history outcome study, prediction claim, tag,
  hosted release, package publication, or deployment. Preserve this packet as
  the immutable closeout record for the offline release slice.

# SAED Adoption Profile

**Project:** gex-terminal

**Stable project identity:** `gex-terminal`

**Method version:** `1.3`

**Base profile:** `saed-standalone`

**Local profile:** `gex-terminal-team-v1`

**Local profile version:** `1`

**Adoption context:** `team`

**Adoption owner:** Project maintainer

**Adopted:** 2026-08-19

**Status owner:** Each routed contributor packet owns its bounded slice;
active `GEX-OFFLINE-001` owns the `0.5.0` integration and release record. `GEX-HEALTH-001`
through `005` record merged repairs. Closed `GEX-LIVE-001` records `0.4.0`;
prepared `GEX-LIVE-002` does not authorize or certify live operation.
Closed `GEX-LIVE-PREP-001` owns only offline population preparation for that
future observation. `GEX-HEALTH-006` and reopened `GEX-INSTALL-001` cover the
release-blocking terminal shutdown regression found by the final hosted gate.

## Purpose And Entry Boundary

`gex-terminal` is an open, local-first market-structure research workbench. It
must let researchers inspect and compare explicit GEX proxy models without
presenting software verification as live-provider certification, dealer
inventory, predictive validity, or financial advice.

| Field | Value |
| --- | --- |
| Project authorization | Maintainer-directed development in the canonical repository |
| Authorized outcome | Evidence-bounded, reproducible GEX research and provider-normalization workflows |
| Decision owner | Project maintainer |
| Repository boundary | `https://github.com/zrack/gex-terminal` |
| External-action gates | Credentials, paid data, live certification, deployment, protected-branch merge, tags, releases, and publication require explicit authority |

## Canonical Truths

| Truth | Authority | Writers | Drift Detection And Repair |
| --- | --- | --- | --- |
| Release version | `pyproject.toml` | Release maintainer | Version consistency tests and build metadata check |
| Normalized market contract | `gex_terminal/market_data_adapter.py` and `gex_terminal/contracts.py` | Maintainers through reviewed changes | Contract tests and fixture validation |
| Model behavior | `gex_terminal/engine.py` and model modules | Maintainers through reviewed changes | Numerical, property, sensitivity, and replay evidence |
| Current architecture | `docs/architecture.md` | Architecture authority | Closeout reconciliation against shipped source |
| Active change intent/status | Any open packet in `docs/work-packets/`; no active status when all packets are closed | Spec steward | PR review and closeout check |
| Release history | `CHANGELOG.md` and Git history | Release maintainer | Version/release consistency inspection |
| Research corpus membership | Corpus event chain created by `corpus-init` and `corpus-register` | Explicit corpus operator | Hash-chain, source-digest, duplicate, and split verification |
| Experiment result | Immutable input digest, model profile, implementation version, and semantic result digest | Experiment runner | `experiment-reproduce` |

Generated reports, screenshots, graph indexes, and dashboards are derived
views. They never override their listed source authorities.

## Non-Negotiable Invariants

- `INV-01` — OI, raw trade volume, directionalized volume, and any future
  participant-attributed model remain separate quantities and are never summed.
- `INV-02` — `predictive_validity` remains `unmeasured` without governed,
  point-in-time, out-of-sample real-market evidence.
- `INV-03` — Offline fixtures and simulations never promote a provider to
  `live-certified`.
- `INV-04` — Dealer/customer and opening/closing state remain `unobserved`
  without licensed evidence that supplies those fields.
- `INV-05` — Mutable market state remains owned by `StatefulGexConsumer`.
- `INV-06` — Credentials, account identifiers, and non-redistributable market
  data never enter committed fixtures, reports, logs, or screenshots.
- `INV-07` — Research inputs are cut off at their declared `as_of`; future or
  missing event time fails closed.
- `INV-08` — Public/read-only research contracts are versioned and unknown
  incompatible versions fail closed.

## Change-Rigor Routing

### L1

- Documentation corrections that do not change model meaning.
- New malformed fixtures inside an existing schema.
- Reproducible screenshot refreshes with unchanged behavior.

### L2

- New offline report or bounded CLI research workflow.
- New model metric inside the existing state and evidence boundaries.
- New provider-shaped fixture mapping that does not claim live readiness.

### L3 Hard Triggers

- Normalized schema or canonical state ownership changes.
- Credential, entitlement, privacy, rights, or licensed-data handling.
- Live-provider certification or readiness promotion.
- Durable corpus/experiment authority, release mechanism, destructive migration,
  or enforced performance/reliability budgets.

## Artifact Ownership

| Role | Canonical Path | Owner |
| --- | --- | --- |
| Roadmap | `ROADMAP.md` | Outcome owner |
| Active packet/status | `docs/work-packets/` | Spec steward |
| Decisions | `docs/decisions/` | Architecture authority |
| Evidence | Packet traceability plus CI and GitHub checks | Evidence reviewer |
| Current architecture | `docs/architecture.md` | Architecture authority |
| Release record | `CHANGELOG.md`, `pyproject.toml`, Git history | Release maintainer |
| Historical packets | Accepted/archived files under `docs/work-packets/` | Spec steward |

## Required Fitness Functions

| Invariant Or Quality | Command Or Inspection | Frequency | Failure Action |
| --- | --- | --- | --- |
| Source integrity | `python -m compileall main.py gex_terminal tests` | Every PR | Block merge |
| Behavioral regression | `python -m unittest discover -s tests -p 'test*.py'` | Every PR | Block merge |
| Numerical ceiling | `gex-terminal model-evidence OUTPUT.json` | Model/release change | Block merge |
| Offline provider behavior | `gex-terminal databento-offline-certify OUTPUT.json` | Adapter/release change | Block merge |
| Research reproducibility | Experiment/corpus/property tests | Research-contract change | Block merge |
| Performance budget | Deterministic generated-chain certification | Release change | Block merge when declared budget fails |
| Distribution parity | Build, Twine, and clean-wheel command smoke | Every release | Block release |
| Documentation hygiene | `git diff --check` and local-link inspection | Every PR | Repair before merge |
| Release identity | Package/changelog/version checks | Every release | Block release |

## Evidence Ladder And Proof Ceiling

Local unit, contract, property, replay, fault-simulation, performance, package,
and screenshot checks support implementation verification only. Hosted CI adds
proof for the reviewed commit in its environment. Live-provider operation
requires an acknowledged, credentialed, redacted certification run. Predictive
or financial outcome validation requires governed point-in-time real history,
predeclared outcomes, untouched test data, costs, and an observation window.

## Release, Recovery, And Observation

- Release identity: exact merged commit plus the version in `pyproject.toml`.
- Rollout: feature branch → pull request → hosted checks/review → merge → clean
  main checkout → full merged-tree verification → push confirmation.
- Recovery: revert the merge or release commit; generated corpus/report outputs
  are rebuildable and no committed migration mutates user data.
- Stop conditions: invariant failure, secret/right-sensitive content, contract
  drift, nonreproducible output, failed declared budget, or claim beyond evidence.
- Runtime observation: separately required for any live-readiness promotion.

## Decision Rights

| Decision | Authority | Required Evidence |
| --- | --- | --- |
| Packet baseline and amendments | Outcome owner/spec steward | Bounded packet and visible rationale |
| Implementation slice | Authorized work package | Focused acceptance evidence |
| Architecture contract | Architecture authority | Delta, alternatives, compatibility, and fitness functions |
| Pull-request merge | Project maintainer | Reviewed diff and required checks |
| Version promotion | Project maintainer | Merged-tree release gate |
| Live certification | Credential/data owner and project maintainer | Redacted exact-run evidence |
| Credentials, spending, destructive action, tag, or hosted release | Explicit owner authority | Action-specific evidence and recovery path |

## Profile Upgrade Log

| Date | From | To | Changed Rules | Active Packets | Decision |
| --- | --- | --- | --- | --- | --- |
| 2026-08-19 | none | `gex-terminal-team-v1` | Initial SAED 1.3 adoption | `GEX-ORC-001` | Adopted for multi-participant release workflow |
| 2026-08-31 | `GEX-ORC-001` closed | `GEX-LIVE-001` closed | Shipped repository-owned pre-live certification hardening for `0.4.0`; credentialed outcome remains external | none | Contributor and closeout pull requests, merged-tree gate, and annotated tag completed |
| 2026-09-04 | Correctness and offline product slices | `GEX-OFFLINE-001` closed | Accepted correctness, doctor, portable loop, compact installation, support/recovery and offline live-population preparation for `0.5.0` | none; `GEX-LIVE-002` prepared only | Independent contributor review, hosted checks and verified main; user/live evidence remains external |

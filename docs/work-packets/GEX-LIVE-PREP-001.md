# GEX-LIVE-PREP-001 — Offline Live-Observation Population Contract

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
adoption_context: team
change_rigor: L3
status: active
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: pull-request reviewer and hosted CI
baseline: codex/gex-research-loop-001@fd4e966
branch: codex/gex-live-prep-001
created: 2026-09-04
execution_authorized: false
```

## Authority And Scope

The maintainer authorized a bounded, offline preparation contract for the later
`GEX-LIVE-002` recurring ES observation. This packet may add a versioned
population-plan template, strict plan and observed-result-manifest validators,
validation-only public CLI commands, focused tests, and an operator guide. It
does not authorize credentials, provider access, network I/O, observation
scheduling, capture, licensed-data retention, readiness promotion, or an
automatic result writer.

This is L3 because a frozen population identity, certification-policy identity,
and prior-population lineage constrain a future live-readiness decision. It
adopts `INV-01` through `INV-08` from the SAED profile.

## Intended Outcome

Before any provider connection, an owner can fill and freeze an exact 12-slot ES
population plan. Offline validation proves only that the plan is complete,
internally consistent, bound to the repository's canonical ES certification
policy, and linked by digest to any prior observed population. After separately
authorized observations, a reviewer can validate a hand-authored redacted
result manifest against that exact frozen plan without the validator contacting
a provider or creating evidence.

## Invariants

- `INV-27` — Validation performs local file reads and deterministic
  canonicalization only; it never opens a provider connection or records a live
  result.
- `INV-28` — A plan binds the complete canonical `databento-es-prelive-v1`
  policy by schema, ID, version, and canonical SHA-256. A copied or weakened
  threshold set cannot validate.
- `INV-29` — The planned population contains exactly 12 unique, non-overlapping
  20-minute UTC slots: three each for regular open, midday, regular close, and
  Globex, across at least four trading dates. Two restart observations occur on
  distinct dates.
- `INV-30` — Application, Python, provider SDK, operating-system, architecture,
  dataset, symbol, multiplier, operator/reviewer aliases, clock source,
  entitlement scope, rights/retention references, and every run time are explicit
  before a plan validates. Placeholder values fail closed.
- `INV-31` — A successor plan includes the immediately prior population ID and
  the canonical SHA-256 of its observed-result manifest. First-population status
  is an explicit declaration, not an omitted field.
- `INV-32` — A result manifest binds the exact plan digest and includes every
  planned run exactly once, including missed and failed attempts. It cannot
  silently replace, omit, or add a run.
- `INV-33` — Plan and result identities hash their complete normalized JSON
  representations with versioned canonical JSON. No generic `generated_at`
  exclusion or partial-field identity is permitted.

## Requirements And Acceptance

| ID | Requirement / Acceptance Criterion | Evidence | Status |
| --- | --- | --- | --- |
| `REQ-01` | A packaged, deliberately incomplete ES template exposes every required owner decision and all 12 exact slot records without credentials or account identifiers. | Package-resource and redaction tests | Planned |
| `REQ-02` | A strict versioned validator rejects duplicate JSON keys, unknown/missing fields, placeholders, non-UTC or non-20-minute slots, duplicate/overlapping slots, wrong window/date counts, and invalid restart selection. | Positive/negative plan tests | Planned |
| `REQ-03` | Plan identity binds exact app/Python/SDK/environment values and the registered ES policy's canonical content hash; NQ or altered policy identity fails closed. | Policy/identity tests | Planned |
| `REQ-04` | Explicit first/successor lineage is required; a successor needs a prior population ID and 64-character result-manifest SHA-256, while a first population prohibits both. | Lineage tests | Planned |
| `REQ-05` | A result manifest validator takes both frozen plan and result paths, requires the plan SHA-256, versions, and all 12 run IDs to match, and retains every pass/failure/missed outcome with appropriate actual times and report-digest state. | Result-manifest tests | Planned |
| `REQ-06` | Public CLI validation commands print stable identities on success, return nonzero on rejection, avoid echoing document values, and perform no provider setup or network I/O. | CLI/subprocess tests | Planned |
| `REQ-07` | The operator guide distinguishes structural validation from owner authority, real observation, rights review, provider reliability, and promotion. | Documentation review | Planned |

## Architecture Delta

```text
packaged incomplete template
          |
owner-filled JSON --local validator--> normalized frozen plan + plan SHA-256
          |                                      |
          |                          separate external authority/live work
          |                                      |
          +-- frozen plan + hand-authored redacted result manifest
                                  |
                           local cross-validator
                                  |
                     result-manifest SHA-256 / lineage input
```

The existing Databento certification policy remains the sole authority for
symbol, multiplier, dataset, and thresholds. The new contract imports and hashes
that registered policy; it does not copy thresholds into another authority.
Neither validator imports an adapter, resolves credentials, schedules tasks, or
writes a provider record.

## Risks And Controls

| ID | Risk | Control / Recovery |
| --- | --- | --- |
| `RISK-01` | A valid template is mistaken for execution authority. | Template placeholders intentionally fail; CLI and guide state that validation grants no authority. |
| `RISK-02` | Later success hides an earlier failed population. | Successor lineage requires prior result-manifest identity; promotion review still owns completeness across the chain. |
| `RISK-03` | Manual result entry invents evidence. | Validator checks structure and plan consistency only and says so; it does not attest that observations happened or that a digest names a legitimate report. |
| `RISK-04` | Policy changes after a plan is frozen. | Plan embeds the canonical registered-policy digest and validation rejects a stale or altered identity. |
| `RISK-05` | A manifest includes private/licensed detail. | Schema permits bounded categories, aliases, times, versions, digests, and redacted notes only; guide keeps plans/results outside the public repository when restricted. |

## Verification And Recovery

Run focused plan, result, CLI, package-resource, duplicate-key, and no-network
tests; then source compilation, the full unit suite, diff hygiene, numerical
model evidence, and offline Databento certification. Build a wheel and validate
the packaged template from outside the checkout. Hosted review remains a merge
gate.

Recovery is a Git revert of this isolated feature commit. The validators do not
modify plan/result files, migrate user data, or contact an external system.

## Evidence

Implementation has not started. The packet is routed first as required. No live
observation, customer evidence, predictive result, or provider-readiness change
is claimed.

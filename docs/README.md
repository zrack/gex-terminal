# Documentation Map

This index routes each topic to one canonical document. Keep summaries and links
outside the owning document; do not copy full command references, contracts, or
status checklists into multiple files.

## Canonical Ownership

| Topic | Canonical document | What belongs there |
| --- | --- | --- |
| Project front door | [README](../README.md) | Positioning, evidence boundary, install, quick start, and links to detailed guides |
| Current system | [Architecture](architecture.md) | Repository map, component responsibilities, runtime flows, state ownership, and verification map |
| Application health | [Application Review](application-review.md) | Latest dated state assessment, open review findings, reproductions, and verification limits |
| Planned work | [Roadmap](../ROADMAP.md) | Now/next/later sequencing, dependencies, and exit criteria for work not yet shipped |
| Shipped history | [Changelog](../CHANGELOG.md) | Released or merged capabilities and version history |
| Durable direction | [Product Vision](product-vision.md) | Target users, product outcomes, and non-goals without implementation status |
| Market evidence | [Competitive Analysis](market-analysis.md) | Dated competitor/persona evidence and implications; not active delivery status |
| Normalized provider contract | [Market-Data Adapters](adapters.md) | Message shapes, quantity semantics, provider readiness, and adapter extension rules |
| Model meaning | [Model Assumptions](model-assumptions.md) | Equations, pricing models, units, position proxies, levels, and limitations |
| Model evidence | [Model Validation](model-validation.md) | Numerical oracles, deterministic gates, provenance, and proof ceiling |
| Databento mapping | [Databento Fixture Mapping](databento-fixtures.md) | Provider-specific requests, record mapping, certification policy, and lifecycle evidence semantics |
| Offline provider evidence | [Offline Validation](offline-validation.md) | Replay, temporal, adversarial, and scripted-lifecycle checks plus their proof ceiling |
| Capture safety | [Capture Governance](capture-governance.md) | Pre-capture rights, retention, redaction, research-use decisions, and logging safeguards |
| Live observation preparation | [Live Population Preparation](live-population-prep.md) | Offline population preregistration, canonical identities, full-result accounting, and external authority gates |
| Research authority | [Research Governance](research-governance.md) | Model profiles, manifests, corpus gates, split identity, and evidence ladder |
| Contribution workflow | [Contributing](../CONTRIBUTING.md) | Setup, verification commands, development rules, and pull-request checklist |
| Change governance | [SAED Adoption Profile](SAED_ADOPTION_PROFILE.md) | Change rigor, authority, invariants, active-packet rules, and release evidence |
| Security | [Security](../SECURITY.md) | Credential handling and vulnerability reporting |

An active work packet under `work-packets/` owns the status of its authorized
change. Closed packets are historical evidence and do not make a roadmap item
active. [GEX-LIVE-PREP-001](work-packets/GEX-LIVE-PREP-001.md) owns the bounded
offline live-population contract. [GEX-HEALTH-004](work-packets/GEX-HEALTH-004.md)
owns experiment-identity integration; independent preflight, support,
installation and research-loop slices are isolated on their contributor
branches. `GEX-HEALTH-001`, `002`, `003`, and `005` record merged correctness
repairs.

## Start Here By Goal

### Understand The System

- [Architecture](architecture.md) — layers, data flow, state ownership, and
  verification.
- [Application Review](application-review.md) — current health evidence and
  open correctness/usability findings.
- [Market-Data Adapters](adapters.md) — normalized messages and provider paths.
- [Model Assumptions](model-assumptions.md) — GEX definitions and limitations.
- [Export Formats](exports.md) — snapshot, overlay, comparison, and certification
  artifact formats.

### Work Offline

- [Replay Research](replay-research.md) — choose the right replay or local
  research workflow.
- [Replay Lab](replay-lab.md) — multi-session reports and alert checks.
- [Demo Lab](demo-lab.md) — screenshot and shareable artifact packs.
- [Provider Injection](provider-injection.md) — provider-shaped fixture input.
- [Offline Validation](offline-validation.md) — temporal, adversarial,
  price-action, and position-model checks.
- [Provider Fixture Example](examples/provider_fixture_lab.md) — scorecard
  interpretation.

### Capture And Compare Research

- [Capture Governance](capture-governance.md) — required live-capture policy,
  retention decisions, and logging/redaction safeguards.
- [Captured Sessions](captured-sessions.md) — normalized event files and replay.
- [Historical Session Store](historical-sessions.md) — computed snapshot archive.
- [Research Journal](research-journal.md) — local study entries and comparisons.
- [Research Governance](research-governance.md) — model profiles, experiment
  manifests, corpus registration, batch comparison, and certification gates.
- [Directionalized-Volume Comparison](model-comparison.md) — model separation,
  directional coverage, and comparison semantics.

### Work With Providers

- [Market-Data Adapters](adapters.md) — shared contract and provider selection.
- [Databento Fixture Mapping](databento-fixtures.md) — Databento-specific mapping
  and live-certification boundary.
- [Live Population Preparation](live-population-prep.md) — freeze and validate a
  prospective ES population without contacting a provider.
- [Provider Injection](provider-injection.md) — offline provider-shaped samples.
- [Captured Sessions](captured-sessions.md) — sanitized normalized captures.

### Contribute Or Govern A Change

- [Contributing](../CONTRIBUTING.md) — setup, tests, and pull requests.
- [Code of Conduct](../CODE_OF_CONDUCT.md) — community participation rules.
- [Good First Issues](good-first-issues.md) — bounded starter work.
- [SAED Adoption Profile](SAED_ADOPTION_PROFILE.md) — routing and evidence rules.
- [ADR-001](decisions/ADR-001-offline-research-authority.md) — append-only,
  contract-driven research identity decision.
- [GEX-ORC-001](work-packets/GEX-ORC-001.md) — closed `0.3.0` work-packet record;
  it is not an active packet.
- [GEX-LIVE-001](work-packets/GEX-LIVE-001.md) — closed `0.4.0` pre-live
  hardening and release record; credentialed validation remains external
  follow-on work.
- [GEX-LIVE-PREP-001](work-packets/GEX-LIVE-PREP-001.md) — active offline
  preregistration and result-manifest contract; no live execution is authorized.

## Editing Rules

- Keep the README short enough to install and start the app without becoming a
  command manual.
- Keep current implementation detail in architecture and topic guides; the
  README may summarize user-visible capabilities and readiness.
- Put future sequencing only in the roadmap and completed delivery only in the
  changelog or a closed packet.
- Keep detailed normalized payload examples in `adapters.md`; provider-specific
  guides should document mapping differences rather than copy the base schema.
- Keep equations and metric semantics in `model-assumptions.md`.
- Link to a workflow guide instead of repeating its complete command sequence.
- State whether evidence is offline, live, descriptive, predictive, or
  unmeasured whenever that boundary affects a claim.

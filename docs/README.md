# Documentation Map

This index routes each topic to one canonical document. Keep summaries and links
outside the owning document; do not copy full command references, contracts, or
status checklists into multiple files.

## Canonical Ownership

| Topic | Canonical document | What belongs there |
| --- | --- | --- |
| Project front door | [README](../README.md) | Positioning, evidence boundary, install, quick start, and links to detailed guides |
| Current system | [Architecture](architecture.md) | Repository map, component responsibilities, runtime flows, state ownership, and verification map |
| Planned work | [Roadmap](../ROADMAP.md) | Now/next/later sequencing, dependencies, and exit criteria for work not yet shipped |
| Shipped history | [Changelog](../CHANGELOG.md) | Released or merged capabilities and version history |
| Durable direction | [Product Vision](product-vision.md) | Target users, product outcomes, and non-goals without implementation status |
| Market evidence | [Competitive Analysis](market-analysis.md) | Dated competitor/persona evidence and implications; not active delivery status |
| Normalized provider contract | [Market-Data Adapters](adapters.md) | Message shapes, quantity semantics, provider readiness, and adapter extension rules |
| Model meaning | [Model Assumptions](model-assumptions.md) | Equations, pricing models, units, position proxies, levels, and limitations |
| Model evidence | [Model Validation](model-validation.md) | Numerical oracles, deterministic gates, provenance, and proof ceiling |
| Contribution workflow | [Contributing](../CONTRIBUTING.md) | Setup, verification commands, development rules, and pull-request checklist |
| Change governance | [SAED Adoption Profile](SAED_ADOPTION_PROFILE.md) | Change rigor, authority, invariants, active-packet rules, and release evidence |
| Security | [Security](../SECURITY.md) | Credential handling and vulnerability reporting |

An active work packet under `work-packets/` owns the status of its authorized
change. Closed packets are historical evidence and do not make a roadmap item
active.

## Start Here By Goal

### Understand The System

- [Architecture](architecture.md) — layers, data flow, state ownership, and
  verification.
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

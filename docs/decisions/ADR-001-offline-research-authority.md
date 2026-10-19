# ADR-001: Make Research Identity Append-Only And Contract-Driven

- Status: Accepted for `0.3.0`
- Date: 2026-08-19
- Work packet: `GEX-ORC-001`

## Context

Offline reports were deterministic but lacked one durable identity tying model
assumptions, input bytes, split/outcome metadata, implementation version, and
semantic output together. A mutable dataset catalog would make later changes
hard to distinguish from the evidence originally reviewed.

## Decision

Use versioned inline model profiles and experiment specs, content digests, and
an append-only hash-chained corpus event log. Keep generated reports derived and
replaceable; keep source registration history immutable. Treat provider
readiness as a separate controlled vocabulary from runtime connection state.

## Consequences

- Reproduction fails on source drift or decision-relevant result drift.
- Split changes require a new dataset identity/event rather than history edits.
- Corpus paths and licensed inputs remain local; only redistributable synthetic
  examples belong in the package.
- Offline success remains bounded to software and process evidence.
- A future schema change requires an explicit migration or a new versioned
  reader; silent reinterpretation is not allowed.

## Alternatives Considered

- A mutable JSON catalog was simpler but could not prove registration history.
- Hashing reports verbatim would fail on timestamps; semantic hashing excludes
  only volatile generation time and retains every decision-relevant field.
- Storing only a model-profile reference reduced duplication but weakened the
  self-contained experiment contract and reproducibility outside the checkout.

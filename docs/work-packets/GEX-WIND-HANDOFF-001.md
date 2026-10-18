# GEX-WIND-HANDOFF-001 — Terminal Checkpoint Handoff

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: active
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent contributor review
baseline: main@6b5af41502e26351a70180d3144aeeec2b6023d6
branch: codex/wind-tunnel-checkpoint
created: 2026-10-18
```

## Authority And Scope

The maintainer explicitly requested the roadmap recommendations, a checkpoint
handoff into Wind Tunnel, regression tests, documentation, commit and merge.
This authorizes the bounded implementation and its pull-request integration.
Keep issue #4 open until actual Tradovate payloads satisfy its independent gate.
There is no authority for paid/provider connections, live certification,
version/tag promotion or publication.

Update the roadmap's research/live dependencies and demand-led priorities.
Deliver an explicit Terminal action that freezes its current demo/replay state
and opens Wind Tunnel on that checkpoint. Support a local checkpoint file for
CLI handoff and self-contained scenario receipts. This is a single frozen
state, not continuous synchronization or a general data importer. Live-state
capture remains outside the slice and must fail closed.

## Contract And Invariants

[ADR-002](../decisions/ADR-002-terminal-checkpoint-handoff.md) owns the bounded
copy/transport decision. The consumer remains the sole mutable state owner.
Capture spot, market time, selected rows, separated alternate quantities,
expiry filter, effective rate/DTE/multiplier and source-quality provenance
under its lock. A detached, versioned, bounded and checksummed artifact binds
the state. No provider config, credentials or arbitrary filesystem path enters
the browser request. Missing event time, unsupported/mixed state, invalid input
and unapproved live capture fail closed.

The default `terminal_selected` model matches Terminal's existing per-contract
positive-trade-volume preference with OI fallback, without summing descriptions
of the same contract. Raw/OI/directional model choices retain their distinct
semantics. Retired-future state, invalidated OI and filtered/expired contracts
cannot reappear. Later ticks, replay replacement and changed settings cannot
mutate a frozen checkpoint. Preserve INV-01 through INV-08 and the historical
September study and release tags.

## Acceptance

1. Zero-shock parity with the production consumer for legacy and v2 inputs,
   ES/NQ multipliers, rate/DTE changes, expiry filters, mixed quantity
   availability and rollover. Explicit unavailable states stay unavailable.
2. Atomic immutable capture, later-event isolation, stable identities and
   rejection of malformed, nonfinite, oversized, unknown-version, future-time
   or checksum-invalid artifacts.
3. Real keyboard action and HTTP calculation/save/reopen/reproduction on the
   frozen source. Browser source/model/defaults distinguish captured state from
   bundled synthetic examples. Portable receipts reproduce in a fresh process
   without the original checkpoint file or server.
4. Loopback capability/origin protections remain intact; browser requests never
   select arbitrary input paths. Server ownership and terminal shutdown settle
   the handoff service; startup/browser failures are recoverable.
5. Full regression suite, compilation, documentation links, whitespace,
   numerical checks and installed-wheel CLI handoff smoke pass. Review the
   integrated diff independently and require hosted checks for the final head.

## Integration And Recovery

Feature branch → reviewed pull request → final-head hosted checks → authorized
merge → clean main → full merged-tree verification and remote equality.
Record final identities and measured verification here before closure.
Recover by reverting the merge; retain research files and matching builds.
No migration, tag, provider-readiness or predictive-validity promotion occurs.

## Evidence

Local source passes all 637 tests, including 23 additional checkpoint,
cross-language browser and keyboard/HTTP/lifecycle regressions. Compilation,
documentation links, patch hygiene and the numerical gate pass. Independent
review found and verified repairs for interrupted runner cleanup, publication
after Terminal teardown, contract selection before expiry filtering, and
Python/JavaScript numeric-token reserialization. Checkpoint JSON is transported
opaquely while validated metadata is decoded for display/calculation.

The actual local browser opened a frozen NQ checkpoint, preserved its zero-shock
baseline, recalculated an IV shift, saved and verified/reopened its receipt.
The wheel passes build/Twine and installs into an isolated environment outside
the checkout using the retained offline wheelhouse. Nine changed runtime/asset
files match installed bytes. Installed CLI export and receipt reproduction
pass after deleting the original checkpoint input. The wheel SHA-256 is
`ae90358b8b99f50b3d87ea5e2b4bbd850380e6ade2817facfd5ed90c50a22b58`.
Local evidence is retained under `dist/wind-tunnel-handoff/2026-10-18/`.

The first whole-suite run during concurrent edits retained one browser-fixture
failure; the final settled-tree run passes 637 tests in 99.178 seconds. The
browser's initial checksum failure was independently reproduced through Node
and fixed before acceptance. No provider credentials or connections were used.
Final-head hosted checks, merge and merged-tree verification remain pending.

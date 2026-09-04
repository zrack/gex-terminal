# GEX-RESEARCH-LOOP-001 — Portable Offline Research Loop

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: ready for contributor review
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: pull-request reviewer and hosted CI
baseline: main@4d58f89
branch: codex/gex-research-loop-001
integration_base: main@2029f29
created: 2026-09-04
```

## Authority And Scope

The maintainer authorized repository-owned offline product work through the
live-data boundary. This slice extends the existing Demo Lab into one portable,
reviewable research loop and adds a dedicated synthetic NQ schema-v2 replay. It
does not authorize live connections, licensed payload retention, provider
readiness promotion, predictive claims, package publication, or deployment.

This packet is L3 because the generated review receipt becomes a durable
integrity and reproduction contract, and because schema/runtime compatibility
must fail closed. It adopts `INV-01` through `INV-08` from the SAED profile.

## Outcome

A contributor can generate a self-contained Demo Lab pack, copy it outside the
checkout, verify every declared source and artifact, and reproduce the same
offline result with a clean environment. The pack explains today's snapshot,
compares open interest, raw trade volume, and directionalized trade volume as
separate proxies, preserves the replay input and its authorization, and records
an evidence-bounded review receipt.

## Invariants

- `INV-20` — Open interest, raw trade volume, and directionalized trade volume
  are computed and labeled separately and are never added together.
- `INV-21` — The portable source is committed synthetic schema-v2 data with
  explicit redistribution authority; no live or private provider payload is
  admitted into the pack.
- `INV-22` — Catalog symbol and multiplier, model profile, normalized schema,
  application version, and supported runtime must agree before verification or
  reproduction begins.
- `INV-23` — A review receipt binds source bytes, stable decision content, and
  every declared artifact. Missing, extra, renamed, or changed declared content
  fails closed.
- `INV-24` — Reproduction resolves inputs relative to the copied pack and emits
  no checkout-specific absolute path.
- `INV-25` — Replay Lab never reports cross-instrument deltas or a single
  instrument identity for a mixed-symbol selection.
- `INV-26` — Python entry points remain experimental; the documented contract
  is the public CLI and versioned artifact schemas.

## Requirements And Acceptance

| ID | Requirement / Acceptance Criterion | Evidence | Status |
| --- | --- | --- | --- |
| `REQ-01` | Catalog a synthetic NQ, multiplier-20 replay whose option messages are normalized schema v2 and include exact event/expiry times, OI, raw trades, and known/unknown direction. | Fixture/catalog tests | Verified |
| `REQ-02` | Demo Lab copies the authorized input into the existing pack and emits separate OI/raw/directional comparison artifacts plus limitations in JSON, Markdown, and README views. | Pack tests | Verified |
| `REQ-03` | The review receipt records portable source, model, app/runtime, quality, evidence ceiling, stable semantic hashes, and all non-receipt artifact byte hashes. | Receipt contract tests | Verified |
| `REQ-04` | `demo-lab verify PACK` rejects altered/missing/extra declared content, wrong symbol/multiplier/model, unsupported schemas, and incompatible app/runtime. | Negative CLI tests | Verified |
| `REQ-05` | `demo-lab reproduce PACK OUTPUT` uses only the copied input and receipt, regenerates the pack, verifies it, and matches recorded decision content without source-checkout paths. | Copied-pack clean-environment test | Verified |
| `REQ-06` | The generated README supports Today → Explain → Compare → Replay → Review and gives portable verify/reproduce commands. | README assertions | Verified |
| `REQ-07` | Mixed-symbol Replay Lab output groups identity and suppresses cross-symbol comparisons/leaderboards. | Replay Lab tests | Verified |

## Architecture Delta

```text
cataloged synthetic replay
        |
        +--> existing replay/snapshot path --------> Today + Explain
        |
        +--> existing position-model comparison ---> Compare (OI/raw/directional)
        |
        +--> copied inputs/replay.jsonl ------------> Replay
        |
        +--> manifest + receipt hashes -------------> Review / verify / reproduce
```

The existing Demo Lab remains the sole pack generator. `StatefulGexConsumer`
retains mutable market-state ownership, and the existing model-comparison
implementations retain calculation ownership. The portable layer only selects,
copies, describes, binds, verifies, and reproduces those artifacts.

## Evidence Ceiling And External Gates

This work can establish deterministic offline software behavior, portable
integrity, synthetic model disagreement, and contributor usability. It cannot
establish live transport, current market coverage, dealer inventory,
forecasting value, execution quality, or profitability. Credentialed data,
rights-approved real history, user observation, and commercial decisions remain
external gates.

## Verification And Recovery

Run focused fixture, Demo Lab, replay, comparison, CLI, package-resource, and
negative integrity tests; then source compilation, the full suite, diff hygiene,
model evidence, and offline Databento certification. Build and install the wheel
into a clean environment, generate a pack, copy it outside the checkout, and
verify/reproduce it there. Hosted checks and independent review remain required
before merge.

Recovery is a Git revert of this isolated feature commit. Generated packs are
rebuildable directories; the implementation performs no migration and does not
overwrite a reproduction target.

## Evidence

- Integrated the H1/H2/H3/H4/H5 correctness base through `main@2029f29` into
  the contributor branch before final verification.
- `python -m unittest discover -s tests`: 349 tests passed.
- Focused Demo Lab, catalog, replay, comparison, chronology, ownership,
  experiment-manifest, and provider-fixture set: 53 tests passed.
- `python -m compileall -q gex_terminal tests` and `git diff --check` passed.
- `gex-terminal model-evidence`: numerical gate passed with predictive validity
  `unmeasured`.
- `gex-terminal databento-offline-certify --symbol ES --multiplier 50`: all
  bounded cases passed with `live_transport=false`.
- Built the wheel from a clean archive of the committed tree and confirmed the
  packaged `nq_research_loop_v2.jsonl` resource.
- Installed that wheel and all declared dependencies into a fresh Python 3.12
  virtual environment. Under an empty environment outside the checkout, the
  installed CLI generated a 20-artifact NQ pack, verified a detached copy,
  reproduced it, and verified the reproduction. Source, model-profile, and all
  five decision-content hashes matched; a path scan found no checkout or source
  archive absolute path.
- Hosted checks and independent contributor review remain merge gates and are
  not claimed by this packet.

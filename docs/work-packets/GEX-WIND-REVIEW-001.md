# GEX-WIND-REVIEW-001 — Saved Flip Research

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L2
status: closed
packet_owner: project maintainer
spec_steward: implementation agent
baseline: main@9a34d352543bc68185a695af568b1cea18feac3b
branch: codex/wind-tunnel-saved-flip-research
created: 2026-11-14
```

The maintainer requested saved ES and NQ flip investigations, comparison and
blind review, followed by documentation, current visuals and integration into
`main`. This packet covers those local Wind Tunnel workflows.

## Acceptance

- Find modeled net-GEX sign flips on bundled and verified saved replays. Open
  an exact event boundary, reconcile the priced contract contributions and
  calculate the same-cutoff result with the driving update removed.
- Switch explicit saved sources and compare two flips from distinct captures.
  Keep selection, contributions, removal and receipt reproduction bound to
  each capture checksum and event sequence.
- In Blind Replay Review, keep each flip's horizon sign and observed futures
  price path behind its own server-owned read commitment. In a paired review,
  save and reopen one receipt with both commitments and outcomes. Same-market
  receipt reproduction resolves the original captures by checksum.
- Preserve ordinary Wind Tunnel workflows and compatible historical receipts.
  Keep input authority local and illustrate the workflows with synthetic
  browser captures and recorded provenance.

## Evidence And Integration

The [Wind Tunnel guide](../wind-tunnel.md) owns commands, model boundaries and
receipt behavior. The [visual asset guide](../../assets/README.md) owns public
preview inputs and provenance. Regression coverage exercises the commit gates,
correct-capture identity checks, same-cutoff removal, and exact receipt
reproduction. Browser verification covers saved source selection and paired
blind review. Private capture verification stays local.

Closure applies upon the authorized pull-request merge after hosted checks.
Git history records the integrated commits. Preserve existing release tags and
provider-readiness decisions. This is deterministic offline software evidence.
Predictive validity and observed participant acceptance remain unmeasured.

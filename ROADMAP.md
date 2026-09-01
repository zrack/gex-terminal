# Roadmap

This file contains planned and deferred work only. Shipped work belongs in
[CHANGELOG.md](CHANGELOG.md), the current system belongs in
[docs/architecture.md](docs/architecture.md), and durable product outcomes
belong in [docs/product-vision.md](docs/product-vision.md).

The project direction remains an evidence-bounded, local-first GEX model
laboratory: normalize provider inputs, preserve position-model provenance,
compare methods on identical point-in-time sessions, and state the proof ceiling
of every result.

## Priority Order

| Order | Outcome | Gate |
| --- | --- | --- |
| Now | Produce one bounded credentialed ES Databento report | Explicit credential/data-owner authority and the versioned ES policy |
| Next | Establish recurrence evidence and evaluate NQ separately | Predeclared observation windows, retained redacted reports, and per-symbol review |
| Blocked | Build a governed real-session evaluation corpus | Licensed retention/research authority plus a certified provider path |
| Later | Stabilize research interfaces and live delivery | Reproducible corpus/model evidence and demonstrated user need |

The `0.4.0` release candidate implements the repository-owned pre-live
hardening under the release-ready
[GEX-LIVE-001 packet](docs/work-packets/GEX-LIVE-001.md). The packet remains
active through merged-tree and tag closeout. Databento still has registry status
`live-uncertified`: no credentialed report or recurring service evidence is
claimed.

## Now: Credentialed Databento Evidence

The only immediate work is external observation. It requires authority to use a
credential and the relevant market-data entitlements; retaining a capture also
requires an approved [capture policy](docs/capture-governance.md) before the
connection opens.

1. Run `databento-certify` for ES with the canonical multiplier and the
   versioned ES policy in a declared read-only observation window.
2. Retain the redacted report, exact package/tag identity, credential and
   entitlement scope description, and observation-window metadata. Do not
   retain raw or normalized market data unless the separate capture policy
   permits it.
3. Review transport, chain breadth, freshness, sequence, multiplier, IV,
   shutdown, reconnect, and OI fields as separate evidence. A returned request
   ID is not a provider acknowledgement, unavailable OI is not trade volume, and
   an unobserved reconnect cannot be claimed as tested service behavior.
4. Classify any failure as authentication, entitlement, coverage, payload,
   temporal, lifecycle, or policy evidence. Repair code only when the evidence
   identifies a repository defect; otherwise keep the external limitation
   explicit.

Exit only when a redacted report clears the declared ES policy for its exact
dataset, symbol, credential, entitlements, configuration, and window. That is a
bounded observation, not global readiness, predictive validity, execution
quality, or profitability.

## Next: Recurrence And Separate NQ Review

Before changing provider readiness, route a new packet that defines the number,
timing, market conditions, and failure tolerance of recurring observations.
Repeat the same immutable report contract across those windows and preserve
failures as evidence rather than selecting only successful runs.

Evaluate NQ independently with its own canonical multiplier and policy. ES
evidence cannot certify NQ. A readiness decision must name the exact supported
scope and unresolved limitations, including OI availability and any reconnect
behavior that was not actually observed.

## Blocked Future Outcomes

After the live and recurrence gates have explicit authority and evidence:

- Capture licensed, point-in-time sessions with source, rights, retention,
  redaction, research-use, cost, symbol, expiry, and as-of metadata.
- Register immutable train, calibration, and untouched test splits before
  evaluating outcomes.
- Replay identical sessions through OI, raw-volume, and
  directionalized-volume models without summing or relabeling their quantities.
- Publish descriptive disagreement and stability evidence first. Keep
  `predictive_validity=unmeasured` until governed out-of-sample evidence
  supports a narrower claim.
- Define a supported read-only Python research interface before considering
  REST or MCP contracts.
- Build multi-symbol scans, alerts, integrations, or hosted views only on
  provider paths with comparable certified coverage and retained provenance.

## Deferred

Higher Greeks, scenario P/L, broad retail options flow, dark pools, mobile or
social features, trade execution, and proprietary commentary are not current
priorities. PyPI publication and a hosted GitHub Release remain separately
authorized distribution decisions.

Contributor-sized offline tasks live in
[docs/good-first-issues.md](docs/good-first-issues.md), not in this roadmap.

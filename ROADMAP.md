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
| Now | Certify one bounded Databento ES/NQ live path | Credentialed, entitlement-aware evidence with real chain coverage and production diagnostics |
| Next | Build a governed real-session corpus and evaluation baseline | Licensed point-in-time captures from the certified path |
| Then | Stabilize public research interfaces and add live delivery | Reproducible corpus/model evidence and a certified multi-symbol data path |
| Later | Broaden analytics and distribution | Demonstrated user need without weakening model or provider truth |

The sequence follows the August 2026
[competitive analysis](docs/market-analysis.md): core GEX calculations, local
operation, replay, and generic tunability are not a sufficient moat. The
stronger opportunity is reproducible provider/model comparison backed by a
governed point-in-time corpus. That corpus does not yet exist.

## Now: Databento Live-Path Certification

**Candidate packet:** `GEX-LIVE-001`

**Rigor:** L3

**Status:** next, not active

Open a routed work packet before implementation or any credentialed run. Live
credentials, paid entitlements, retained market data, and readiness promotion
require explicit owner authority under the
[SAED adoption profile](docs/SAED_ADOPTION_PROFILE.md).

Databento is the shortest path because its adapter, Black-76 inversion,
temporal checks, offline replay, and bounded certification command already
exist. It remains `live-uncertified`: the repository has not demonstrated
active ES/NQ chain coverage, entitlement behavior, live OI availability,
payload drift, reconnect behavior, or production diagnostics.

### Intended Scope

1. Strengthen the certification contract before using credentials. Require
   explicit thresholds for contract definitions, option trades, underlying
   quotes, expiries, strikes, freshness, sequence integrity, and usable IV
   inputs; a single definition/quote/trade sample is not chain certification.
2. Make open-interest status explicit. Subscribe to and normalize the licensed
   statistics path when available, or report OI as unavailable without falling
   back silently or combining it with trade volume.
3. Measure native, Black-76-inverted, and configured-fallback IV separately,
   including quote age, inversion failures, and fallback coverage.
4. Add production-suitable logging controls and redaction checks for
   credentials, account identifiers, licensed payloads, and report output.
5. Exercise disconnect, reconnect, resubscription, stale-data, entitlement, and
   shutdown behavior in deterministic tests and in an acknowledged bounded
   live window where the provider allows it.
6. Certify ES first, then NQ with its own multiplier and report. Keep every
   result scoped to the exact credential, entitlement set, environment, symbol,
   and observation window.
7. Decide and record, before capture, whether observed data may be retained,
   redacted, and used in research. Corpus population belongs to the next packet
   after the live gate passes.

### Exit Criteria

- Offline regression, adversarial, temporal-integrity, package, and redaction
  gates still pass.
- A redacted credentialed report proves the declared ES chain-coverage and
  quantitative-input thresholds for a bounded observation window.
- OI availability, IV provenance, fallback share, latency/freshness, malformed
  frames, disconnects, reconnects, subscription requests/IDs, and provider
  acknowledgements or errors where exposed are visible rather than inferred.
- No credentials, account identifiers, or non-redistributable payloads enter
  committed fixtures, logs, screenshots, or reports.
- Documentation and provider readiness are reconciled with the evidence. A
  connection alone does not promote the adapter, and a single run proves only
  its declared window unless the work packet defines a stronger recurrence
  rule.
- NQ is evaluated separately after the ES gate; an ES pass does not certify NQ.

If credentials or entitlements are unavailable, the repository-owned portion
can still strengthen the harness and deterministic tests. The live outcome must
remain open rather than being inferred from offline evidence.

## Next: Governed Real-Session Evidence

After one live path meets its bounded gate:

1. Capture licensed, point-in-time market days with source, rights, redaction,
   cost, symbol, session, expiry, and as-of metadata.
2. Register immutable train, calibration, and untouched test splits before
   evaluating outcomes.
3. Replay identical sessions through OI, raw-volume, and directionalized-volume
   models without summing or relabeling their quantities.
4. Define outcome windows, executable timing, and costs before reading the test
   results.
5. Publish descriptive disagreement and stability evidence first. Keep
   `predictive_validity=unmeasured` until governed out-of-sample evidence
   supports a narrower claim.

Exit when another researcher can reproduce the registered corpus identity,
model profile, experiment manifest, semantic output, and declared split without
using post-as-of data in decision-time inputs. Later held-out observations may
be used only as predeclared outcomes. The prospective moat is this governed
history, not the existence of replay commands alone.

## Then

- Define and version a supported read-only Python research interface. Existing
  CLI and JSON artifacts are useful foundations, but they are not yet a stable
  public Python, REST, or MCP contract.
- Build the multi-symbol scanner only on provider paths that expose comparable
  per-symbol coverage and feed quality. Start with certified ES/NQ scope before
  adding MES, MNQ, SPX, SPY, QQQ, or IWM.
- Deliver live alerts, TradingView/webhook/Discord integrations, and hosted
  views only from the certified path; retain provider and model provenance in
  every message.
- Add dedicated expiry-exposure and date-tagged day-over-day journal fields.
- Evaluate `pipx`, a tagged release, and package publication as separately
  authorized distribution work.
- Consider DEX, vanna, charm, vega, theta, and scenario P/L only after the live
  option-chain and evaluation contracts are stable.

## Deferred

Broad retail options flow, dark pools, mobile/social features, trade execution,
and proprietary daily commentary are not current priorities. Reconsider them
only if target-persona research changes the product thesis.

## Completed Baseline

Version `0.3.0` established the offline research certification workbench:
contract-aware Black-76/Black-Scholes calculations, normalized provider and
replay paths, captured sessions, model comparisons, experiment/corpus
contracts, batch evaluation, deterministic certification gates, packaging
checks, and explicit evidence ceilings. See [CHANGELOG.md](CHANGELOG.md) for the
shipped record; completed checklists are intentionally not repeated here.

Contributor-sized tasks live in
[docs/good-first-issues.md](docs/good-first-issues.md), not in this roadmap.

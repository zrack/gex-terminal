# Product Vision

`gex-terminal` should become the auditable, local-first market-structure
instrument for ES/NQ options research. Its purpose is not to produce one more
confident gamma line. Its purpose is to let a user understand what produced a
structural proxy, where credible models disagree, whether the source is healthy,
and what later evidence did or did not support the original read.

Implementation status and sequencing belong in [ROADMAP.md](../ROADMAP.md).
Shipped history belongs in [CHANGELOG.md](../CHANGELOG.md). Market facts and
competitive conclusions belong in
[Competitive Landscape](market-analysis.md).

## North Star

> Show me the current structural proxy, tell me exactly why it looks that way,
> show where credible models disagree, and let me replay the same state later.

The durable product promise is **inspectability before interpretation**. Every
important output should answer:

- Which provider records, contracts, timestamps, and quantities produced it?
- Which pricing model, expiry, multiplier, rate, IV source, and position model
  were applied?
- Which parts are observed, inferred, configured, or derived?
- Do other credible position models agree?
- Is the source complete and fresh enough for this exact claim?
- Can another person reproduce the result from the same point-in-time inputs?
- What did later evidence show, and what remains unmeasured?

## Initial Target Hypothesis And Job

The initial target is one behavioral segment: a technically capable ES/NQ
research operator who owns the data relationship and personally tests or uses
structural models. That person may work as a quant, developer, researcher, or
advanced trader, but the common behavior—not the job title—is the hypothesis.
Phase 0 of the [roadmap](../ROADMAP.md) must validate or replace it before it is
treated as a confirmed market.

Their recurring job is not “tell me where price will go.” It is:

> Help me form, inspect, preserve, and later evaluate a model-dependent view of
> options market structure without hiding data quality or turning a proxy into
> observed dealer inventory.

Less-technical advanced futures traders are the first adjacent audience when a
live path has a defined support envelope. The buying unit and willingness to
pay remain open questions. Mobile-first novices, commentary-seeking traders,
and users seeking automatic execution are not the first target.

## The Real Product Experience

The application should feel like one research loop rather than a collection of
commands.

### Today

Start with a source preflight: entitlement state, active contract, chain
coverage, freshness, OI state, IV provenance, and any degraded inputs. Then show
the current proxy regime, dominant structures, and material changes with a
visible proof ceiling.

### Explain

Let the user open any wall, flip, exposure band, or alert and trace it back to
the contracts and assumptions that produced it. Explain the mechanical model
without claiming that the model observed participant identity, intent, or a
future outcome.

### Compare

Run identical point-in-time inputs through open interest, raw volume,
directionalized volume, and future licensed attribution methods without adding
or relabeling unlike quantities. Make agreement, disagreement, coverage, and
uncertainty more prominent than a single composite score.

### Replay

Replay the exact event-time session, not a reconstructed screenshot. Preserve
source identity, model version, parameter changes, quality transitions, and the
conclusion that was available at each point in time.

### Review

Bind a saved read to later descriptive and outcome evidence. Keep favorable
excursion, adverse excursion, fixed-horizon movement, executable assumptions,
costs, and realized account returns separate. Retain negative, unresolved, and
failed-source cases alongside successes.

## Signature Outcomes

### Inspectable Regime View

Present the selected model's positive or negative exposure proxy, strike
profile, concentration, spot, quality state, and next structural change in one
compact surface. Volatility, pinning, support, resistance, and acceleration
remain hypotheses to evaluate rather than observed dealer behavior.

### Model-Dissent Map

Show where position models agree on sign, walls, ranks, and change—and where
they do not. The product should be most useful on ambiguous days because it can
explain why confidence is limited.

### Replayable Market Days

Preserve governed point-in-time sessions, replay them on their event-time
clock, and bind results to input, provider, policy, and model identities.
Consistency hashes can detect corruption; source rights, authenticity, and
historical immutability require separate authority.

### Portable Levels And Local Alerts

Make derived levels, exposure bands, quality changes, and model-dissent events
portable to user-owned tools. Every export or alert should retain enough
provider, model, timing, and readiness provenance to remain interpretable away
from the application.

### Evidence Vault

Build a governed history of sessions, experiments, model versions, and results
that can be reproduced on a clean machine. Its value is an honest record of
where models were stable, unstable, descriptive, useful, or unsupported—not a
curated gallery of wins.

### Developer Surface

Offer stable read-only domain objects and artifact contracts so providers,
models, research notebooks, local services, and integrations can reuse the
same semantics. External interfaces must not create a second, less-governed
definition of the data or model.

## Product Form

The durable shape is an open research kernel surrounded by optional convenience
and operational layers:

- **Open Lab:** deterministic demo/replay, transparent calculations,
  contributor adapters, model comparison, and local artifacts.
- **Professional Desktop:** packaged installation, guided bring-your-own-data
  setup, certified live workflows, background operation, alerts, integrations,
  upgrades, diagnostics, and support.
- **Research Team:** rights-aware derived-artifact sharing, governed experiment
  and corpus controls, reproducible comparisons, and administrative support.

This is a product hypothesis, not a commitment to specific packaging or
pricing. The open MIT kernel should remain useful on its own. Any paid layer
must sell convenience, operational confidence, collaboration, or support—not
obscure the calculation that creates trust.

An optional hosted service is compatible with the vision only when data rights,
privacy, support, and economics are explicit. Local operation and bring-your-own
credentials remain the default posture. Raw licensed market data must not be
centralized or redistributed merely because derived collaboration is useful.

## Trust Contract

- Provider readiness, runtime connection state, input quality, numerical
  correctness, descriptive usefulness, predictive validity, execution quality,
  and profitability remain separate claims.
- No output implies dealer/customer identity, opening/closing activity, or
  institutional intent unless licensed fields establish it.
- No live connection certifies a provider; no fixture certifies a live path;
  no backtest certifies executable performance.
- Source gaps and model disagreement remain visible. Missing evidence is not
  converted to zero or hidden behind a confidence badge.
- Evaluation definitions are fixed before outcomes are inspected. Complete
  eligible populations and null findings remain available.
- User credentials, raw licensed data, and private research stay local unless a
  separate, explicit agreement authorizes another path.

## Product Boundaries

Broad equity-options flow, dark pools, political data, news aggregation,
social/community feeds, automated trade calls, brokerage execution, and generic
AI commentary are not part of the core thesis. Higher Greeks, multi-asset
coverage, hosted delivery, and an evidence-aware assistant are possible
extensions only when the primary workflow, data rights, and user demand support
them.

The product should not win by sounding more certain than the evidence. It
should win by making uncertainty inspectable and useful.

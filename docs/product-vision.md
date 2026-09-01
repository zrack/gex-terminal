# Product Vision

`gex-terminal` is an open, local-first market-structure research workbench for
people who want to inspect how a GEX estimate was produced. It is not trying to
be a cheaper clone of a closed dashboard. Its durable advantage should come
from provider-normalized inputs, replaceable models, reproducible point-in-time
research, and explicit evidence ceilings.

Implementation status and sequencing belong in [ROADMAP.md](../ROADMAP.md).
Shipped history belongs in [CHANGELOG.md](../CHANGELOG.md).

## Product Promise

A researcher should be able to answer:

- Which provider records and position quantity produced this view?
- Which pricing model, expiry, multiplier, rate, and IV provenance were used?
- How would the result change under another explicit position model?
- Can another person replay the same point-in-time inputs and reproduce it?
- What does the evidence establish, and what remains unobserved or unmeasured?

The workbench should make those answers easier without requiring a hosted
account or hiding calculations behind a proprietary interface.

## Primary Users

- **Quant and model researchers** comparing assumptions, providers, sessions,
  and outcomes.
- **Python and data engineers** extending normalized adapters and reproducible
  research contracts.
- **Advanced ES/NQ traders** studying transparent structural proxies after a
  live data path has met its declared certification gate.

Mobile-first novices, commentary-seeking traders, and users seeking automatic
trade execution are not the primary product target.

## Signature Outcomes

### Inspectable Proxy Regime View

Present the selected position model's positive or negative exposure proxy,
documented strike-profile compatibility level, gamma-wall concentration, spot,
and next structural trigger in one compact view. Volatility, pinning, support,
and resistance interpretations remain hypotheses for evaluation rather than
observed dealer behavior.

### Replayable Market Days

Let researchers preserve a governed point-in-time session, replay it on its
event-time clock, compare walls and profile changes, and bind the result to its
input identity and model profile. In-file consistency hashes detect corruption;
source rights, authenticity, and historical immutability require separate
authority.

### Portable Levels And Local Alerts

Make derived levels, exposure bands, quality states, and structural changes
portable to local files and user-owned tools. Every export or alert should
retain enough provider, model, timing, and readiness provenance to avoid turning
a proxy into an unexplained signal.

### Comparable Position Models

Replay identical sessions through open interest, raw trade volume,
directionalized trade volume, and any future licensed participant-attribution
method without adding or relabeling unlike quantities. Comparison should expose
coverage and disagreement before attempting to score predictive value.

### Cross-Symbol Research

Allow comparable ES/NQ and related-symbol study only where each provider path
can show contract coverage, freshness, provenance, and quality. A scanner should
rank modeled structural change, not imply dealer inventory or forecast risk
that the inputs do not observe.

## Product Boundaries

The product does not infer dealer/customer identity, opening/closing activity,
or institutional intent without licensed fields that supply those facts. It
does not treat a live connection as provider certification, offline correctness
as predictive validation, or a backtest as executable performance. Broad
options flow, dark pools, social/mobile delivery, execution, and proprietary
commentary remain outside the core thesis unless user evidence changes it.

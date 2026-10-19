# Model Assumptions

`gex-terminal` estimates intraday gamma exposure for research and engineering
experimentation. It is not financial advice, an execution signal, or a
replacement for licensed market-data products.

This document states the assumptions that turn normalized option-chain inputs
into displayed GEX. Numerical validation and its evidence ceiling are documented
separately in [model-validation.md](model-validation.md).

## Current Model

Schema-v2 contract rows are priced before aggregation:

- Futures options use Black-76 gamma.
- Equity and index options use Black-Scholes gamma. The engine API supports a
  continuous carry/dividend rate; normalized adapters currently use their
  documented value or zero.
- Each row uses its own implied volatility, DTE, and contract multiplier.
- Dollar GEX is expressed in USD gamma exposure per 1% underlying move.
- The day-count convention is `ACT/365`.
- Equal-strike rows are aggregated only after contract-level pricing.

A timezone-bearing `expiry_timestamp` is the authoritative source for
fractional DTE and takes precedence over an explicit `days_to_expiry` value. If
no authoritative timestamp exists, explicit contract DTE is used next. A
date-only `expiry` label supports selection but does not imply an
exchange-specific settlement instant; the configured scalar DTE is the visible
fallback.

Schema-v1 messages remain on the original strike-level Black-Scholes path.
Mixed v1/v2 option state reports `mixed_legacy_fallback` rather than presenting
partly contract-aware output as authoritative.

The terminal aggregates exposure into:

- Total net GEX.
- Gamma wall.
- Call wall and put wall.
- Strike-profile flip and nearest-neutral strike.
- Concentration bands.
- Call/put imbalance.

## Quantity And Position Sources

Schema v2 labels each option quantity and volatility input with explicit provenance:

- `volume_semantics`: `incremental` updates add to prior state; `cumulative`
  updates replace the prior absolute value.
- `position_source`: `trade_volume` or `open_interest`.
- `iv_source`: `provider`, `black_76_inverted`, or `configured_default`; only
  the latter is counted and surfaced as degraded feed quality.

Databento's live option-trade path can derive `black_76_inverted` IV from the
option trade price, latest observed continuous-futures midpoint, authoritative
expiry timestamp, and configured risk-free rate. The `iv_provenance` object
records those inputs, the bisection method, convergence status, iterations, and
absolute option-price error. This is an asynchronous trade/midpoint pairing,
not a synchronized executable option quote or an exchange-published IV.

Contract state is scoped by provider, contract ID, and position source. Sequence
numbers can suppress duplicate updates. If a cumulative source resets below its
previous value, the new provider value becomes the current absolute state and a
quality counter records the rollback. If both trade volume and open interest
exist for the same provider contract, the consumer prefers a positive
trade-volume state and otherwise falls back to open interest instead of summing
two descriptions of positioning. Snapshot provenance counts source conflicts.

Trade volume is responsive but does not reveal whether trades opened or closed
positions, can reflect churn, and does not identify customer/dealer direction.
Open interest is often delayed and still does not establish who owns which side.
Neither source is dealer inventory.

When incremental trade records carry a known aggressor side, the terminal also
computes a parallel directionalized-volume model. It treats aggressor buys as
gamma sold by the passive counterparty and aggressor sells as gamma bought by
the passive counterparty. Unknown-side volume is reported as uncovered and is
not signed. This alternate model does not establish that the passive
counterparty is a dealer, identify participants, classify opening/closing flow,
or replace the default model. See [model-comparison.md](model-comparison.md).

Schema v1 retains its historical accumulated-volume proxy for compatibility.
Snapshot provenance identifies that path as `legacy_volume_proxy`.

## Call And Put Sign Convention

The current model treats call exposure as positive and put exposure as negative:

- Call GEX = `selected_call_quantity * gamma_scaling_factor`
- Put GEX = `selected_put_quantity * gamma_scaling_factor * -1`
- Net GEX = `call_gex + put_gex`

This convention is simple and explainable, but it is not a complete
dealer-positioning model. Actual hedging direction depends on trade direction,
customer/dealer classification, inventory, and opening/closing state. Those
fields are not inferred without evidence.

## Strike-Profile Flip And Compatibility Field

`strike_profile_flip` is estimated only in strike space:

- If a strike bucket has exactly zero net GEX, that strike is the crossing.
- If adjacent strikes change sign, the crossing is linearly interpolated.
- If no adjacent sign change exists, `strike_profile_flip` is `null`.

`nearest_neutral_strike` is always the observed strike bucket with the smallest
absolute net GEX. The historical `zero_gamma`/`zero_gamma_strike` field is kept
for UI and export compatibility: it uses the strike-profile flip when one exists
and otherwise falls back to the nearest-neutral strike.

This is not the underlying price where a full option portfolio's gamma becomes
zero after repricing every contract across hypothetical spot prices. Calling it
a portfolio zero-gamma root would exceed the implemented evidence.

## Gamma Wall And Concentration

The gamma wall is the strike with the largest absolute net GEX concentration.
The call wall and put wall are based on the largest call-side and absolute
put-side exposure respectively.

The concentration band reports the smallest strike range that contains the
configured share of absolute net GEX. It describes clustering in the selected
chain; it does not prove support, resistance, or future volatility.

## Expiry Selection

The runtime can select `all`, `0dte`, or an exact expiry label with
`--expiry-filter` or the terminal `x` key. Authoritatively expired contracts are
excluded. A 0DTE match uses the session's timezone-bearing as-of time and expiry
metadata; date-only labels can identify the calendar bucket but still use the
configured DTE for pricing unless a more precise input exists.

Changing the expiry filter changes the selected contract population. Changing
the scalar DTE changes only rows that need that fallback.

## Known Limitations

- No observed dealer/customer participant classification; the optional
  aggressor-directionalized proxy assumes a passive dealer-side counterparty.
- No opening/closing trade classification.
- No vanna, charm, delta exposure, vega exposure, or theta exposure.
- Live option-chain coverage remains provider- and entitlement-specific.
- Tradovate quote frames do not establish native implied volatility; fallback
  IV is marked as degraded and cannot certify quantitative GEX.
- Databento trade-price IV inversion depends on the latest observed futures
  midpoint and can be stale or asynchronous; the certification report measures
  occurrence and provenance, not executable calibration quality.
- That midpoint must be timestamped no later than the option trade and no older
  than the configured maximum age. Its age and threshold are explicit
  provenance; timing failure forces labeled fallback IV and blocks quantitative
  certification.
- Market-maker inventory and proprietary positioning assumptions are not
  modeled.
- Exchange settlement conventions are not inferred from a date-only expiry.
- No predictive return, trading-edge, calibration, or live P&L validity has been
  measured.

These limits are part of the model contract. The project prefers an explicit
unmeasured state over confidence that the evidence does not support.

## Contributor Guidance

When changing model behavior:

- Add independent numerical oracles and deterministic tests for the exact
  assumption being changed.
- Keep the base sensitivity scenario equal to the actual snapshot path.
- Update snapshot provenance, the model-evidence report, and this document when
  formulas, signs, inputs, or fallbacks change.
- Include a replay, captured session, or sanitized fixture when behavior depends
  on provider payloads.
- Keep provider-specific parsing outside the engine.
- Do not present modeled levels as financial advice, guaranteed boundaries, or
  predictive evidence.

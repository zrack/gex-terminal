# Model Assumptions

`gex-terminal` estimates intraday gamma exposure for research and engineering
experimentation. It is not financial advice, an execution signal, or a
replacement for licensed market-data products.

This document explains the current model assumptions so contributors can improve
the calculation path without treating the output as a black box.

## Current Model

The engine calculates theoretical Black-Scholes gamma for each strike, then
scales that gamma into dollar gamma exposure per 1% move in the underlying.

Current inputs:

- Current underlying spot or futures price.
- Strike price.
- Implied volatility.
- Days to expiry.
- Risk-free rate.
- Contract multiplier.
- Accumulated intraday call and put volume.

The terminal then aggregates strike-level exposure into:

- Total net GEX.
- Gamma wall.
- Call wall and put wall.
- Zero-gamma node.
- Concentration bands.
- Call/put imbalance.

## Volume-As-Open-Interest Proxy

Official open interest is usually delayed and may not update throughout the
session. For intraday research, `gex-terminal` currently uses cumulative session
volume as a practical proxy for changing open interest.

This makes the terminal responsive to live activity, but it also introduces
important limitations:

- Volume does not reveal whether trades opened or closed positions.
- Volume can double-count churn at the same strike.
- Volume does not distinguish customer flow from dealer flow.
- Volume can overstate exposure during high-turnover sessions.
- Low-volume strikes can appear less important than their true open interest
  would imply.

Future provider integrations should add official open interest when available
and let users compare volume-weighted, open-interest-weighted, and hybrid views.

## Call And Put Sign Convention

The current model treats call exposure as positive and put exposure as negative:

- Call GEX = `call_volume * gamma_scaling_factor`
- Put GEX = `put_volume * gamma_scaling_factor * -1`
- Net GEX = `call_gex + put_gex`

This convention is simple and useful for building an explainable first model,
but it is not a complete dealer-positioning model. In real markets, the sign of
dealer hedging pressure depends on trade direction, customer/dealer positioning,
inventory, and whether trades are opening or closing.

Future work should add dealer/customer direction inference when a provider
exposes enough trade context to support it.

## Zero-Gamma Node

The zero-gamma node is estimated from the strike-level net GEX array:

- If a strike has exactly zero net GEX, that strike is returned.
- If adjacent strikes change sign, the node is linearly interpolated between
  those strikes.
- If no sign change exists, the model falls back to the strike with the smallest
  absolute net GEX.

This makes the output deterministic and stable for replay data, but it should be
read as a structural estimate rather than an exact market boundary.

## Gamma Wall And Concentration

The gamma wall is the strike with the largest absolute net GEX concentration.
The call wall and put wall are based on the largest call-side and put-side
exposure respectively.

The concentration band reports the smallest strike range that contains a target
share of absolute net GEX. This is intended to show whether exposure is tightly
clustered or spread across the chain.

## Known Limitations

Current limitations versus more mature commercial dealer-positioning tools:

- No official open-interest ingestion yet.
- No dealer/customer trade-direction model yet.
- No opening/closing trade classification.
- No vanna, charm, delta exposure, vega exposure, or theta exposure yet.
- Live option-chain discovery still depends on provider-specific implementation
  work.
- Market-maker inventory and proprietary positioning assumptions are not modeled.
- The model does not account for all expiration-specific, settlement, or
  exchange microstructure details.

These limits are intentional to document. The project should prefer a transparent
model that contributors can inspect and improve over opaque confidence.

## Contributor Guidance

When changing model behavior:

- Add deterministic tests for the exact assumption being changed.
- Update this document when formulas, signs, inputs, or fallback behavior change.
- Include replay or fixture data when the change depends on provider payloads.
- Keep provider-specific parsing outside the engine.
- Avoid presenting modeled levels as financial advice or guaranteed support and
  resistance.

# Model Assumptions

`gex-terminal` estimates intraday gamma exposure for research and engineering
experimentation. It is not financial advice, an execution signal, or a
replacement for licensed market-data products.

This document states the assumptions that turn normalized option-chain inputs
into displayed GEX. Numerical validation and its evidence ceiling are documented
separately in [model-validation.md](model-validation.md).

## Current Model

Schema-v2 contract rows are priced before aggregation:

- European futures options use Black-76 gamma. Newly normalized Databento
  futures options with confirmed American exercise use the
  `american_futures_crr` early-exercise model described below.
- Equity and index options use Black-Scholes gamma. The engine API supports a
  continuous carry/dividend rate; normalized adapters currently use their
  documented value or zero.
- Each row uses its own implied volatility, DTE, and contract multiplier.
- Dollar GEX is expressed in USD gamma exposure per 1% underlying move.
- The day-count convention is `ACT/365`.
- Equal-strike rows are aggregated only after contract-level pricing.

Exercise style is a separate contract attribute from pricing model. Databento
definitions preserve supported exercise-style metadata, including the option
CFI classification. Historical captures that explicitly selected Black-76 keep
that formula and its unmeasured American approximation qualification. New
American futures observations select a numerical early-exercise model for both
premium inversion and gamma. In particular, CME quarterly ES/NQ options allow early exercise;
weekly and end-of-month families have different exercise rules. See the current
[ES contract rules](https://www.cmegroup.com/rulebook/CME/IV/350/358A/358A.pdf) and
[NQ contract rules](https://www.cmegroup.com/rulebook/CME/IV/350/359A/359A.pdf).
Do not infer exercise style from the underlying symbol alone.

Missing exercise style remains `unknown`, including older captures that did not
save it. Replaying those captures does not recover discarded metadata or
silently classify the contracts as European. Terminal details, snapshot exports
and Wind Tunnel results expose the selected model and the
qualification for historical approximations or unknown styles. Matching a European exercise
style only qualifies this particular assumption; it does not certify fair
value, all pricing inputs, dealer positioning or predictive validity.

The risk-free rate is a configured annual rate rather than an observed historical
yield curve. It is held fixed within a calculation/scenario. Timestamp-derived
DTE, the configured DTE fallback, contract multipliers, and IV provenance remain
separate inputs; none changes an American contract into a European one.

### American Futures Numerical Model

The American model assumes a premium-paid option on a lognormal futures
martingale: the futures risk-neutral drift is zero, not the spot rate. At each
CRR node it chooses the greater of immediate intrinsic value and discounted
continuation. The default averages adjacent 512/513-step trees, with an
analytical European Black-76 control variate to reduce discretization bias.
Gamma uses the slopes at the second tree layer, with a matching European
control variate, and is specific to call or put. Immediate exercise has zero
gamma. IV inversion uses the same American premium model.

Synthetic regression vectors are independently benchmarked against QuantLib
1.40 finite-difference American prices and gamma. The tested reference cases
measure numerical error and convergence, not market pricing accuracy. Constant
volatility, a configured flat discount rate, lognormal futures and finite
resolution remain assumptions. Provenance distinguishes solver price residual
from numerical discretization and records the method and tree sizes. QuantLib
is a test reference, not an application dependency.

See [QuantLib's American option example](https://github.com/lballabio/QuantLib-SWIG/blob/master/Python/examples/american-option.py)
and [CME's explanation of E-mini option premium cashflows](https://www.cmegroup.com/articles/2024/index-options-box-spreads-as-financing-tool.html).
This model does not cover futures-style margin-paid option premiums.

A timezone-bearing `expiry_timestamp` is the authoritative source for
fractional DTE and takes precedence over an explicit `days_to_expiry` value. If
no authoritative timestamp exists, explicit contract DTE is used next. A
date-only `expiry` label supports selection but does not imply an
exchange-specific settlement instant; the configured scalar DTE is the visible
fallback.

Native Databento event ordering and fill identities preserve nanoseconds.
Reported quote-age and fractional-DTE model calculations use Python's
microsecond datetime clock. Offline validation checks those reported values
against that clock while checking causal native quote/trade order separately.

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
- `iv_source`: `provider`, `black_76_inverted`, `american_futures_inverted`,
  `prior_valid`, or `unavailable` for new Databento observations. Historical
  `configured_default` captures remain readable and qualified as before.

Databento's live option-trade path can derive `black_76_inverted` IV from the
option trade price, latest observed continuous-futures midpoint, authoritative
expiry timestamp, and configured risk-free rate. The `iv_provenance` object
records those inputs, the bisection method, convergence status, iterations, and
absolute option-price error. This is an asynchronous trade/midpoint pairing,
not a synchronized executable option quote or an exchange-published IV.
Confirmed American rows invert the American futures model instead. Solver
convergence does not measure market-model accuracy.

New failed inversions do not manufacture 15% IV. A previously accepted provider
or converged IV for the same contract and selected model may be retained if it
strictly precedes the current event and is at most 300 seconds old. The retained
value, original source, time, age, rate and failed current inversion inputs are
recorded. Retained values never refresh this observation clock or seed another
retention chain; later observations are never applied backward.

If no eligible observation exists, IV is explicitly `null` with
`iv_source=unavailable`. Raw volume remains in contract state and capture, while
that contract's exposure is unpriced. `pricing_coverage` separates selected raw
contracts/quantity, priced contracts/quantity, retained-IV quantity and unpriced
quantity/reasons. One unresolved latest contract observation affects its whole
current accumulated quantity, not merely its last trade size. A later valid
observation can price that quantity from that point forward. Entirely unpriced
selections produce no modeled exposure rather than fabricated zero gamma.

Terminal and Wind Tunnel show pricing coverage as both priced/selected contracts
and priced/selected quantity, with percentages. These denominators follow the
current expiry and quantity-source selection; they are not event counts.
Earlier valid IVs count as priced and are separately labeled. An empty selection
shows no selected contracts, while legacy aggregates without contract records
show coverage as not reported. A partial selection never rounds to 100% coverage.

In a full saved session, a contract without another trade keeps its last captured
IV while its accumulated session quantity remains selected. That observation can
be hours older than the closing checkpoint. The 300-second rule above governs
retention after a new failed inversion; it is not a universal expiry for every
unchanged IV. Closing calculations hold those IVs constant and reprice at the
checkpoint futures price and remaining maturity. Pricing coverage measures which
selected quantities have usable model inputs; it does not establish a fresh,
synchronized closing option chain. Expired contracts remain in the capture but
leave active coverage and GEX.

Wind Tunnel reports **accepted-IV age** independently of pricing coverage.
The active selected cohort determines both denominators, but age categories
cover only priced contracts: within 300 seconds, older, unknown, or not
applicable. Counts and selected quantities are reported separately. Provider
or converged-IV observations use their accepted event time; retained prior-valid
IV uses its original accepted observation and provenance, never the later
failed tick. Configured or legacy unspecified IV has no observed age.

The original state measures age at its frozen capture cutoff. A scenario
measures age at that cutoff plus the requested model-time advance, with no new
observations. Missing or invalid clocks and unsupported provenance remain
unknown. An observation clearly after the capture is unknown, not fresh.
If a nanosecond event cannot be ordered against a capture cutoff saved only
to microseconds, its age stays unknown and is counted as capture-precision
ambiguity rather than confirmed future data. No timestamp is invented to fill
that gap.

This 300-second age reference is a disclosure, not a pricing filter. It neither
expires unchanged accepted IV nor changes the failed-inversion retention rule.
Captured source health is also separate: **REPLAY** is a mode, while a health
such as **degraded** describes the source ledger and can include events outside
the current active pricing cohort.

Terminal's `v` details and Wind Tunnel's Source & assumptions explain each
unpriced contract. When captured evidence is available, they show the original
premium, violated model bound, underlying input and quote age. Terminal details
also show the premium-to-bound gap. Those values
describe the failed inversion at capture time, including after a scenario shifts
the underlying; the display does not reinvert or fill missing IV. An incompatible
premium/input pair explains the model failure, but does not establish the market
or feed reason for that disagreement. Raw quantities remain visible and unpriced
exposure stays excluded from GEX.

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

A side without nonzero modeled exposure has no wall. Its wall is `null` in JSON,
unavailable in text and omitted from plotted/exported levels. The first strike
in an all-zero side is not a wall. This applies symmetrically to calls and puts.

Call/put imbalance is call exposure divided by absolute put exposure. With no
put exposure the ratio is undefined and exported as `null`; the display says
**Calls only** when only calls contribute, **Puts only** when only puts
contribute, or **No selected quantities** when neither contributes. A put-only
ratio of zero is valid but does not imply that call observations exist. These
side labels describe the selected quantities, not market-wide positioning.

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

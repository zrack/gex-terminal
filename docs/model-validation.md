# Model Validation

`gex-terminal` separates numerical implementation evidence from market claims.
The model-evidence gate checks analytical gamma values, dollar-GEX scaling, and
deterministic aggregation. Predictive return, calibration, trading edge, and
live P&L validity remain explicitly unmeasured.

## Run The Evidence Gate

Write a JSON or Markdown report:

```bash
gex-terminal model-evidence model_evidence.json
gex-terminal model-evidence model_evidence.md
```

The command exits nonzero if a numerical or deterministic check fails. Its
current evidence ceiling is **numerical correctness and deterministic
aggregation only**.

## Independent Oracles

The report compares the engine with fixed analytical references:

| Case | Inputs | Expected gamma or GEX |
| --- | --- | ---: |
| Black-Scholes ATM | $S=K=100$, $T=1$, $r=0.05$, $\sigma=0.20$ | `0.018762017345847` gamma |
| Black-Scholes with carry | same inputs, carry $q=0.02$ | `0.018950578755009` gamma |
| Black-76 ATM | $F=K=100$, $T=1$, $r=0.05$, $\sigma=0.20$ | `0.018879647164533` gamma |
| ES Black-76 scaling | $F=K=5000$, $T=1/365$, $r=0.045$, $\sigma=0.15$, quantity `100`, multiplier `50` | `$12,701,305.382447` per 1% move |

The deterministic checks cover repeatability, contract-row order invariance,
and linear scaling with the selected position quantity. Focused regression tests
also compare analytical gamma with a finite-difference option-price derivative,
check call/put signs and multipliers, reject invalid/non-finite inputs, and keep
the base sensitivity scenario equal to the computed contract-aware snapshot.

## Versioned Model Contract

Snapshot schema `gex-terminal.snapshot.v2` records the model provenance needed
to interpret an output:

- model version `gex-terminal.gex-model.v2`;
- normalized message schema versions used;
- calculation mode and pricing models;
- selected position sources and conflicts;
- selected and expired contract counts;
- active expiry filter and as-of time;
- `ACT/365` day count and GEX units;
- aggregation method and strike-profile flip semantics.

Schema-v2 futures options use Black-76. Equity and index options use
Black-Scholes, including an optional carry rate in the engine API. Each contract
row is priced with its own time to expiry and multiplier before rows are
aggregated by strike. A timezone-bearing `expiry_timestamp` is authoritative for
fractional DTE and overrides a supplied `days_to_expiry`; explicit DTE is next,
then the configured scalar fallback. A date-only expiry label cannot imply an
exchange settlement time.

Legacy schema-v1 messages remain supported through the original strike-level
Black-Scholes path. If v1 and v2 option messages are mixed in one session, the
consumer reports `mixed_legacy_fallback` instead of presenting contract-aware
results as authoritative.

## Position Evidence

Schema v2 distinguishes `incremental` and `cumulative` volume semantics and
records whether quantity came from `trade_volume` or `open_interest`. Contract
state is keyed by provider, contract ID, and position source. Repeated
cumulative updates replace the current absolute quantity; incremental updates
add to it. When both trade volume and open interest exist for the same provider
contract, the consumer selects one source instead of summing two descriptions
of positioning.

This remains a positioning proxy. It does not establish dealer/customer side,
opening versus closing flow, or dealer inventory.

## Strike-Profile Semantics

The engine exposes two truthful strike-space measures:

- `strike_profile_flip`: a linear interpolation between adjacent strike buckets
  whose net-GEX values change sign; it is `null` when no adjacent crossing
  exists.
- `nearest_neutral_strike`: the observed strike bucket with the smallest
  absolute net GEX.

The historical `zero_gamma`/`zero_gamma_strike` field is retained for format and
UI compatibility. It equals the strike-profile flip when one exists and falls
back to the nearest-neutral strike otherwise. It is **not** a portfolio gamma
root found by repricing the entire book across hypothetical underlying prices.
Reports and research claims should use `strike_profile_flip` when that narrower
meaning matters.

## Evidence Ceiling

Passing the gate does not validate the source data, the call-positive/put-negative
sign convention, the volume/open-interest proxy, dealer direction, predictive
returns, or live profitability. Those require separately specified datasets,
benchmarks, labels, and out-of-sample tests. Until such evidence exists, the
correct predictive status is `unmeasured`.

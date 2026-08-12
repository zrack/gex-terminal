# Offline Validation Workbench

The offline validation workbench exercises provider mapping, temporal integrity,
position-source comparisons, and saved-price behavior without opening a market
data connection. Passing these workflows is software evidence, not live-provider
or predictive certification.

## Databento Record Replay

Replay mixed `definition`, `mbp-1`, `trades`, and `statistics` records from
JSON, JSONL, DBN, DBN.ZST, or DBZ:

```bash
gex-terminal databento-replay INPUT.jsonl OUTPUT.json \
  --symbol ES --multiplier 50 --max-underlying-age 2
```

DBN formats require the optional `.[databento]` dependency but do not require an
API key. JSON/JSONL records need a `record_type` or `schema` discriminator.
Records pass through the same Databento record handler used by live mode.

The report separates definitions, underlying quotes, option trades, OI updates,
IV inversion/fallback counts, dropped/control records, feed quality, and a
computed snapshot. `software_path_certified=true` requires aligned timestamps,
matching futures identity, at least one converged IV inversion, no fallback IV,
and no parse errors. `live_transport_certified` is always false.

## Temporal Integrity

Black-76 trade-price inversion records option and futures event times,
`underlying_price_age_ms`, `maximum_underlying_age_ms`, futures identity, option
price, futures midpoint, rate, time to expiry, iterations, and solver error.

A futures midpoint is not eligible when it is older than the configured limit,
timestamped after the option trade, missing event time, or mapped to another
futures contract. Crossed and one-sided books are also rejected. The option
trade may remain in the raw-volume model with labeled fallback IV, but the
quantitative-input gate fails.

## Adversarial Software Certification

```bash
gex-terminal databento-offline-certify offline_certification.json \
  --symbol ES --multiplier 50
```

The twelve deterministic cases cover the aligned path, trade-before-definition,
trade-before-underlying, stale and future-dated midpoints, wrong futures identity,
invalid option price, unknown control records, duplicate sequences, crossed and
one-sided books, and provider error records. This proves fail-closed software
behavior only.

## Saved Price-Action Evaluation

Each input observation supplies a timestamp, decision-time spot, named levels by
model, optional directional coverage, and a strictly later `future_path`:

```json
{"timestamp":"2026-08-01T14:30:00Z","spot":6000,
 "models":{"raw":{"gamma_wall":6020,"zero_gamma":5975}},
 "future_path":[{"minutes":5,"price":6008}]}
```

```bash
gex-terminal price-action-evaluate INPUT.json OUTPUT.json
```

The report measures level distance, touches, crossings, terminal return, and
favorable/adverse moves. Observations receive chronological train, calibration,
and test labels. Results remain `descriptive_only`, `promotion_allowed=false`,
and `predictive_validity=unmeasured`.

## OI, Raw Volume, And Directionalized Comparison

Provide one timezone-bearing `as_of` and normalized messages containing an
underlying tick plus `open_interest` and `trade_volume` option states:

```bash
gex-terminal position-model-compare INPUT.json OUTPUT.json \
  --symbol ES --multiplier 50
```

Messages after `as_of` or without event time are rejected. OI is cumulative and
unknown-direction; trade volume is incremental and may preserve aggressor
direction. Each source receives its own snapshot. Sources are never summed, and
dealer inventory and predictive validity stay unmeasured.

Bundled examples live under `gex_terminal/data/provider_fixtures/`:

- `databento_mixed_offline_records.jsonl`
- `price_action_validation_example.json`
- `position_model_comparison_example.json`

## Still Requires External Evidence

Offline work cannot certify authentication, entitlements, current active-chain
coverage, payload drift, real latency/reconnect behavior, or licensed OI
availability. Predictive promotion additionally requires point-in-time real
history, preregistered decisions, untouched out-of-sample data, and costs.

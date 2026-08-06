# Directionalized Volume Model Comparison

`gex-terminal` can calculate an optional aggressor-directionalized volume model
beside the unchanged call-positive/put-negative GEX proxy. The alternate model
is a research comparison, not a replacement default or a predictive signal.

## Model Contract

For each incremental trade with known aggressor direction:

- Buy aggressor volume is treated as gamma sold by the passive counterparty.
- Sell aggressor volume is treated as gamma bought by the passive counterparty.
- Trades without direction remain in `unknown_aggressor_volume` and do not
  contribute signed exposure to the alternate model.

This assumes the passive counterparty is the dealer-side proxy. The feed does
not establish participant identity or whether a trade opens or closes a
position. Snapshot and comparison outputs therefore retain:

- `participant_classification: unobserved`
- `opening_closing_classification: unobserved`
- `predictive_validity: unmeasured`

Schema-v2 messages may carry optional `aggressor_side` values `buy` or `sell`
and a `direction_source` of `provider` or `quote_inference`. Known direction is
accepted only for incremental `trade_volume`; cumulative volume and open
interest remain unknown-direction quantities.

## Comparison Harness

Generate a Markdown, JSON, or CSV report from a normalized replay:

```bash
gex-terminal --replay /path/to/side-aware-session.jsonl \
  --model-comparison model_comparison.md
```

Exercise the complete Databento fixture mapper, consumer, both models, and the
comparison report without credentials:

```bash
gex-terminal inject-provider bundled:databento-glbx \
  --model-comparison model_comparison.md
```

The report compares:

- Total net GEX and regime sign.
- Gamma-wall and zero-gamma distance.
- Strike-sign agreement.
- Strike-profile rank correlation.
- Normalized-profile L1 distance.
- Known versus unknown directional volume coverage.

If no usable side data exists, the report returns
`insufficient_directional_coverage` and leaves comparison metrics unscored.
Agreement or disagreement between models is not evidence of forecasting value.

## Databento Semantics

The fixture mapper preserves Databento trade-side codes as provider-sourced
aggressor direction: `B`/bid becomes `buy`, `A`/ask becomes `sell`, and missing
or indeterminate values become `unknown`. This does not transform aggressor
direction into customer/dealer identity.

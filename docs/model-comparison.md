# Directionalized Volume Model Comparison

`gex-terminal` can calculate an optional aggressor-directionalized volume model
beside the unchanged call-positive/put-negative GEX proxy. The alternate model
is a research comparison, not a replacement default or a predictive signal.

Use [Wind Tunnel](wind-tunnel.md) for an interactive comparison of a saved ES or
NQ checkpoint. Use the CLI harness below for a report from a normalized replay
or provider-shaped fixture. The position-source ladder adds OI as a separate
view; it does not change the browser's two-model comparison.

## Compare Saved Data In Wind Tunnel

Open **Start GEX.command → Saved data — Both → ES or NQ** in a reviewed setup
with saved-data support. Register both symbols to make both checkpoints
available in one Wind Tunnel source picker. Terminal keeps the symbol selected
at launch. [First Run](first-run.md#open-saved-es-or-nq-data) owns source
registration, long-session loading and local-file limits.

Select **Model comparison**. A frozen Terminal checkpoint uses **Terminal
selected proxy** as its default; a bundled replay uses **Volume proxy**.
The second column uses aggressor-directionalized trade volume. Each column
shows original and scenario net GEX, dominant wall, pricing coverage and
accepted-IV age. Inspect directional coverage as well as pricing coverage:
the signed model can use a smaller quantity cohort than the default.

Price, IV and elapsed-time controls reprice both models from the same frozen
checkpoint. Price changes are underlying points; IV changes are absolute
volatility points; elapsed time does not consume later events. One-axis presets
reset the other changes to zero. **Run 54-case grid** separately tests 27
coordinates for each model: ES price −25/0/+25 or NQ −100/0/+100, IV −1/0/+1,
and elapsed time 0/30/60 minutes. Its nearest-expiry exclusion is off. The grid
always starts from the original checkpoint, independently of the current shocks.

The strike charts share axes and mark the original and scenario futures prices.
**Focused** starts around both prices and includes displayed dominant walls;
**Full range** restores every modeled strike to the charts. Changing the range
does not request another calculation or change totals, quantities, exclusions
or grid conclusions. The exact-values table retains all modeled strikes.

Read these findings separately:

| Finding | What it establishes |
| --- | --- |
| Same net sign or wall at one point | Agreement for these models, inputs and available quantity cohorts at that point |
| Same sign or wall across the grid | Agreement or stability at the explicitly tested points only |
| Different magnitudes | A difference that may reflect the proxy's signs, eligible quantities, IVs or expiry composition |
| Missing direction or unpriced contracts | An evidence limit; unavailable exposure cannot be counted as zero or stable |
| Older accepted IV | The age of a usable pricing input, separate from pricing coverage and saved source health |

Changing the source or scenario clears stale results and grid conclusions.
Neither agreement nor stability establishes dealer inventory, forecasting
accuracy or a probability. Compare the displayed model clocks and coverage
before explaining a magnitude difference.

### Display Responses And Portable Evidence

The browser requests a compact comparison response. It retains summaries,
strike matrices, coverage, accepted-IV ages, exclusions and grid results while
omitting repeated contract-contribution lists and the echoed checkpoint.
This is a transport optimization, not a smaller research population.

**Save scenario** recalculates a full receipt from the retained original input.
Exported and reopened receipts contain the frozen checkpoint, both models,
contract contributions and the grid when requested. Reopening verifies the
calculation and reports a verified status; a matching rounded headline alone
does not establish reproduction. See
[receipt verification](wind-tunnel.md#save-export-and-reproduce) and
[Export Formats](exports.md#wind-tunnel-experiments).

Repeated pricing work is reused only when its complete ordered pricing inputs
match. Quantity cohorts remain independently aggregated. Large American-option
grids can still take seconds to tens of seconds; cold and warm runs differ.
Local measurements are workload- and runtime-specific, not live latency,
throughput or service-level guarantees. [Architecture](architecture.md) owns
the cache and process boundaries.

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

## Position-Source Ladder

The point-in-time position comparison adds open interest as a third, independent
view beside raw and directionalized trade volume:

- `open_interest` uses only OI rows at or before the declared information cutoff;
- `raw_trade_volume` uses only incremental trade-volume rows; and
- `directionalized_trade_volume` signs only the known-direction subset of those
  trade rows under the documented passive-counterparty assumption.

The ladder reports model values and pairwise differences; it never adds the
three views into one exposure estimate. Future-dated or missing-time messages
are rejected from the comparison and counted in `vintage_control`. OI
publication lag must already be represented by the supplied event time.

Use `position-model-compare INPUT.json OUTPUT.json` for an explicit point-in-time
payload. JSON, Markdown, and CSV outputs carry the same non-summation,
participant/open-close, live-certification, and predictive-validity limits. The
portable NQ example and all three output formats are also generated by:

```bash
gex-terminal demo-lab nq_demo_lab --replay-session nq-research-loop
```

See [Demo Lab](demo-lab.md) for its copied-input and receipt contract.

## Databento Semantics

The fixture mapper preserves Databento trade-side codes as provider-sourced
aggressor direction: `B`/bid becomes `buy`, `A`/ask becomes `sell`, and missing
or indeterminate values become `unknown`. This does not transform aggressor
direction into customer/dealer identity.

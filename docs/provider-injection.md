# Offline Provider Injection

Provider injection lets contributors replay raw or provider-shaped sample data
without opening a live market-data connection. It is meant to test the adapter,
consumer, engine, export, and Provider Health path with repeatable fixtures.

This does not prove live entitlements, current provider field drift, or real
network reconnect behavior. It does prove that captured or documented samples
can become inspectable GEX state.

## Provider Fixture Workbench

Run every bundled provider-shaped fixture through the offline workbench:

```bash
gex-terminal fixture-lab provider_fixture_lab.md
gex-terminal fixture-lab provider_fixture_lab.json
gex-terminal fixture-lab provider_fixture_lab.csv
```

The workbench currently covers sanitized Tradovate live frames, a Tradovate
metadata join, Databento GLBX-style fixtures, a yfinance ETF option-chain sample,
and a Cboe-style option quote CSV. Use it before and after adapter changes to
produce one shareable pass/fail scorecard with health counters, computed gamma
wall, strike-profile flip/compatibility level, and saved snapshot baselines.

The checked-in example output is available at
[docs/examples/provider_fixture_lab.md](examples/provider_fixture_lab.md).

## Tradovate Frames

Inject sanitized Tradovate-style WebSocket frames:

```bash
gex-terminal inject-provider bundled:tradovate-live-sample
```

Export the resulting snapshot:

```bash
gex-terminal inject-provider bundled:tradovate-live-sample \
  --export injected_tradovate.md
```

If a raw sample does not carry strike/type fields directly, pass a sanitized
contract-discovery fixture:

```bash
gex-terminal inject-provider bundled:tradovate-md-quotes
```

The Tradovate injector accepts JSON files containing an `a[...]` payload body
and JSONL files containing complete `a[...]` frames.

## Databento Fixtures

Databento sample injection joins definition metadata to trade records, then
optionally injects an underlying quote fixture:

```bash
gex-terminal inject-provider bundled:databento-glbx
```

This exercises the documented `GLBX.MDP3` fixture mapping without requiring a
live Databento key.

The fixture includes known buy/sell and unknown trade-side examples. Generate a
side-by-side model report through the same adapter and consumer path:

```bash
gex-terminal inject-provider bundled:databento-glbx \
  --model-comparison model_comparison.md
```

## yfinance Samples

yfinance samples are useful for delayed SPY/QQQ-style equity/ETF option-chain
research:

```bash
gex-terminal inject-provider bundled:yfinance-etf-options
```

This path is not a futures-options substitute for ES/NQ.

## Cboe-Style CSV Samples

Cboe-style option quote CSV samples can be injected with an explicit fixture
format:

```bash
gex-terminal inject-provider bundled:cboe-option-quotes-csv
```

The CSV parser accepts common header names for underlying symbol/price, strike,
option type, volume or open interest, implied volatility, and expiration.

## Reading Results

The command prints a compact operator summary with:

- spot
- gamma wall
- strike-profile/zero-gamma compatibility level
- normalized message count
- provider frame count
- parse error count
- dropped payload count
- subscription status
- subscribed symbol count
- health state

Use `--export .json`, `--export .csv`, or `--export .md` to save the full
snapshot, including `provider_injection` metadata and `feed_quality` counters.

The `bundled:NAME` selector resolves resources inside either the source package
or installed wheel. Pass a filesystem path, `--metadata`, and
`--underlying-fixture` when teaching or testing a custom local payload. The
`fixture-lab` command runs every bundled case and exits nonzero if any case
fails.

## Adding A Provider Fixture Case

Good provider fixture cases should include:

- Sanitized payloads with no account IDs, tokens, usernames, or session secrets.
- Enough underlying and option data to produce at least one computable snapshot.
- Metadata fixtures when the provider separates option definitions from prices
  or trades.
- An expected health state, especially when malformed or dropped messages are
  intentionally included.
- A short description of what parser behavior the fixture protects.

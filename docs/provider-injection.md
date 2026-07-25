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
wall, zero-gamma level, and saved snapshot baselines.

The checked-in example output is available at
[docs/examples/provider_fixture_lab.md](examples/provider_fixture_lab.md).

## Tradovate Frames

Inject sanitized Tradovate-style WebSocket frames:

```bash
gex-terminal inject-provider tests/fixtures/tradovate_live_sample.jsonl \
  --provider tradovate \
  --symbol ES
```

Export the resulting snapshot:

```bash
gex-terminal inject-provider tests/fixtures/tradovate_live_sample.jsonl \
  --provider tradovate \
  --symbol ES \
  --export injected_tradovate.md
```

If a raw sample does not carry strike/type fields directly, pass a sanitized
contract-discovery fixture:

```bash
gex-terminal inject-provider tests/fixtures/tradovate_md_quotes.json \
  --provider tradovate \
  --symbol ES \
  --metadata tests/fixtures/tradovate_contract_discovery.json
```

The Tradovate injector accepts JSON files containing an `a[...]` payload body
and JSONL files containing complete `a[...]` frames.

## Databento Fixtures

Databento sample injection joins definition metadata to trade records, then
optionally injects an underlying quote fixture:

```bash
gex-terminal inject-provider tests/fixtures/databento_trade_records.json \
  --provider databento \
  --symbol ES \
  --metadata tests/fixtures/databento_definition_records.json \
  --underlying-fixture tests/fixtures/databento_underlying_mbp1_record.json
```

This exercises the documented `GLBX.MDP3` fixture mapping without requiring a
live Databento key.

## yfinance Samples

yfinance samples are useful for delayed SPY/QQQ-style equity/ETF option-chain
research:

```bash
gex-terminal inject-provider tests/fixtures/yfinance_option_chain_records.json \
  --provider yfinance \
  --symbol SPY
```

This path is not a futures-options substitute for ES/NQ.

## Cboe-Style CSV Samples

Cboe-style option quote CSV samples can be injected with an explicit fixture
format:

```bash
gex-terminal inject-provider tests/fixtures/cboe_option_quotes_sample.csv \
  --fixture-format cboe-option-quotes \
  --symbol SPY
```

The CSV parser accepts common header names for underlying symbol/price, strike,
option type, volume or open interest, implied volatility, and expiration.

## Reading Results

The command prints a compact operator summary with:

- spot
- gamma wall
- zero-gamma level
- normalized message count
- provider frame count
- parse error count
- dropped payload count
- subscription status
- subscribed symbol count
- health state

Use `--export .json`, `--export .csv`, or `--export .md` to save the full
snapshot, including `provider_injection` metadata and `feed_quality` counters.

## Adding A Provider Fixture Case

Good provider fixture cases should include:

- Sanitized payloads with no account IDs, tokens, usernames, or session secrets.
- Enough underlying and option data to produce at least one computable snapshot.
- Metadata fixtures when the provider separates option definitions from prices
  or trades.
- An expected health state, especially when malformed or dropped messages are
  intentionally included.
- A short description of what parser behavior the fixture protects.

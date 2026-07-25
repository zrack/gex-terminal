# Replay Research Mode

Replay mode lets contributors exercise GEX calculations and terminal states
without live market data or broker credentials.

## Bundled Sessions

List the bundled sessions:

```bash
gex-terminal list-replays
```

Run a bundled session:

```bash
gex-terminal --replay-session trend-day
gex-terminal --replay-session chop-day
gex-terminal --replay-session volatility-spike
gex-terminal --replay-session gap-fade
gex-terminal --replay-session call-wall-breakout
gex-terminal --replay-session zero-gamma-flip
gex-terminal --replay-session expiration-compression
```

The current research fixtures are:

- `trend-day`: rising spot with call-side accumulation.
- `chop-day`: range-bound balanced call/put flow.
- `volatility-spike`: downside move with higher IV and put-heavy flow.
- `gap-fade`: gap-up open that rejects higher call walls and rotates lower.
- `call-wall-breakout`: upside breakout that walks the call wall higher.
- `zero-gamma-flip`: flow rotation across the zero-gamma boundary.
- `expiration-compression`: late 0DTE pinning around the gamma wall.
- `quality-stress`: valid fixture with off-symbol drops and partial chain
  coverage for Provider Health testing.

## Replay Research Lab

Run every bundled replay session through the offline lab:

```bash
gex-terminal replay-lab replay_lab.md
gex-terminal replay-lab replay_lab.json
gex-terminal replay-lab replay_lab.csv
```

The lab report includes a session dashboard, replay alerts, session-to-session
comparisons, and saved final snapshots for reproducible baseline review. See
[docs/replay-lab.md](replay-lab.md) for the full workflow.

## Demo Lab Pack

Generate a no-credential demo pack from a replay session:

```bash
gex-terminal demo-lab demo_lab
gex-terminal demo-lab demo_lab --replay-session gap-fade
```

The pack bundles the color preview, actual terminal screenshot, snapshot
exports, TradingView overlay exports, Replay Lab reports, Provider Fixture Lab
reports, and a manifest. It is the easiest path for GitHub screenshots and
contributor issue attachments.

## Provider Injection

Provider injection exercises raw or provider-shaped samples through adapter
parsing, consumer state, GEX math, snapshot export, and Provider Health
counters without opening a live connection:

```bash
gex-terminal inject-provider tests/fixtures/tradovate_live_sample.jsonl --provider tradovate --symbol ES
gex-terminal inject-provider tests/fixtures/databento_trade_records.json --provider databento --symbol ES --metadata tests/fixtures/databento_definition_records.json --underlying-fixture tests/fixtures/databento_underlying_mbp1_record.json
gex-terminal inject-provider tests/fixtures/yfinance_option_chain_records.json --provider yfinance --symbol SPY
gex-terminal inject-provider tests/fixtures/cboe_option_quotes_sample.csv --fixture-format cboe-option-quotes --symbol SPY
```

Use this for captured/demo provider samples and converter work. Use normalized
replay fixtures when you want to test the engine contract directly. See
[docs/provider-injection.md](provider-injection.md) for details.

Run the Provider Fixture Workbench when you want a single scorecard across all
bundled provider-shaped samples:

```bash
gex-terminal fixture-lab provider_fixture_lab.md
```

That report is useful for adapter pull requests because it includes pass/fail
state, feed-health counters, computed levels, and saved snapshots without using
live credentials.

## Fixture Validation

Validate normalized JSONL before submitting fixtures:

```bash
gex-terminal validate-fixture sample_data/es_trend_day.jsonl
```

The validator checks JSON syntax, required normalized fields, option type,
positive prices/strikes, non-negative volume, IV shape, and basic fixture
coverage such as underlying ticks and option strikes.

## Offline Quality Scenarios

Demo/export workflows can simulate feed-health issues:

```bash
gex-terminal --demo --quality-scenario stale
gex-terminal --demo --quality-scenario partial-chain
gex-terminal --demo --quality-scenario dropped
gex-terminal --demo --quality-scenario latency
gex-terminal --demo --quality-scenario all
```

These scenarios mutate the local consumer state only. They do not represent a
real provider outage, but they make stale ticks, missing strikes, dropped
messages, and latency visible in the Provider Health panel and exported
snapshots.

## Model Sensitivity

Generate a model sensitivity report:

```bash
gex-terminal --demo --sensitivity sensitivity.md
gex-terminal --replay-session trend-day --sensitivity sensitivity.csv
```

The report compares base GEX output against assumption shifts for contract
multiplier, expiry, risk-free rate, implied volatility, and volume/open-interest
proxy scaling.

# Offline Provider Fixture Workbench

- Generated: `2026-09-04T13:40:02`
- Cases run: `5`
- Passed: `5`
- Healthy live: `0`
- Simulated: `3`
- Degraded: `2`
- Failed: `0`
- Days to expiry: `0.25`
- Contract multiplier: `50`

`Zero Gamma` below is the historical compatibility field: adjacent
strike-profile interpolation when present, otherwise the nearest-neutral strike.
It is not a portfolio root obtained by repricing across hypothetical spot.

## Provider Scorecard

| Case | Provider | Format | Symbol | Mode | Network | Health | Messages | Frames | Parse Err | Dropped | Gamma Wall | Zero Gamma |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tradovate Live Frames | tradovate | tradovate | ES | REPLAY | no | degraded | 6 | 3 | 1 | 1 | 5,950.0 | 5,909.6 |
| Tradovate Metadata Join | tradovate | tradovate | ES | REPLAY | no | simulated | 3 | 1 | 0 | 0 | 5,950.0 | 5,907.4 |
| Databento GLBX Fixture | databento | databento | ES | REPLAY | no | degraded | 4 | 4 | 0 | 0 | 5,950.0 | 5,906.0 |
| yfinance ETF Options | yfinance | yfinance | SPY | REPLAY | no | simulated | 5 | 1 | 0 | 0 | 515.0 | 505.5 |
| Cboe Option Quotes CSV | cboe | cboe-option-quotes | SPY | REPLAY | no | simulated | 8 | 4 | 0 | 0 | 515.0 | 505.5 |

## Case Notes

### Tradovate Live Frames

- Fixture: `gex_terminal/data/provider_fixtures/tradovate_live_sample.jsonl`
- Description: Sanitized WebSocket-style quote frames with one intentionally malformed quote for feed-health testing.
- Command: `gex-terminal inject-provider bundled:tradovate-live-sample`
- Source: `offline_provider_fixture`; network used `no`; runtime `REPLAY` / `DISCONNECTED`.
- Result: `computed` mapping, `degraded` health, `6` normalized messages, `3` provider frames.
- Levels: gamma wall `5,950.0`, zero gamma `5,909.6`, net GEX `+34.45M`.
- Notes: `simulated local feed; provider frame parse errors recorded; malformed payloads recorded; unsupported or off-symbol payloads dropped`

### Tradovate Metadata Join

- Fixture: `gex_terminal/data/provider_fixtures/tradovate_md_quotes.json`
- Description: Quote payload joined to sanitized contract-discovery metadata.
- Command: `gex-terminal inject-provider bundled:tradovate-md-quotes`
- Source: `offline_provider_fixture`; network used `no`; runtime `REPLAY` / `DISCONNECTED`.
- Result: `computed` mapping, `simulated` health, `3` normalized messages, `1` provider frames.
- Levels: gamma wall `5,950.0`, zero gamma `5,907.4`, net GEX `+28.23M`.
- Notes: `simulated local feed`

### Databento GLBX Fixture

- Fixture: `gex_terminal/data/provider_fixtures/databento_trade_records.json`
- Description: Synthetic GLBX.MDP3 definitions, option trades, and underlying mbp-1 quote sample.
- Command: `gex-terminal inject-provider bundled:databento-glbx`
- Source: `offline_provider_fixture`; network used `no`; runtime `REPLAY` / `DISCONNECTED`.
- Result: `computed` mapping, `degraded` health, `4` normalized messages, `4` provider frames.
- Levels: gamma wall `5,950.0`, zero gamma `5,906.0`, net GEX `+10.91M`.
- Notes: `simulated local feed; 3 option tick(s) used labeled fallback IV`

### yfinance ETF Options

- Fixture: `gex_terminal/data/provider_fixtures/yfinance_option_chain_records.json`
- Description: Delayed equity/ETF option-chain sample for SPY-style research.
- Command: `gex-terminal inject-provider bundled:yfinance-etf-options`
- Source: `offline_provider_fixture`; network used `no`; runtime `REPLAY` / `DISCONNECTED`.
- Result: `computed` mapping, `simulated` health, `5` normalized messages, `1` provider frames.
- Levels: gamma wall `515.0`, zero gamma `505.5`, net GEX `+2.50M`.
- Notes: `simulated local feed`

### Cboe Option Quotes CSV

- Fixture: `gex_terminal/data/provider_fixtures/cboe_option_quotes_sample.csv`
- Description: Cboe-style option quote CSV sample using common column names.
- Command: `gex-terminal inject-provider bundled:cboe-option-quotes-csv`
- Source: `offline_provider_fixture`; network used `no`; runtime `REPLAY` / `DISCONNECTED`.
- Result: `computed` mapping, `simulated` health, `8` normalized messages, `4` provider frames.
- Levels: gamma wall `515.0`, zero gamma `505.5`, net GEX `+1.24M`.
- Notes: `simulated local feed`

## Contributor Uses

- Confirm that adapter changes still produce computable snapshots offline.
- Share one report when proposing a new provider fixture or parser change.
- Compare provider health counters before opening a live-data debugging issue.
- Keep fixture samples sanitized so reports are safe to post publicly.

## Recommended Next Checks

- Review degraded health counters in: tradovate-live-sample, databento-glbx.
- Attach the Markdown report to provider-adapter issues or pull requests.
- Use the JSON report as a baseline when changing adapter normalization.
- Add new sanitized provider samples as fixture cases before wiring live credentials.

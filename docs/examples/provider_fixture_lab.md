# Offline Provider Fixture Workbench

- Generated: `2026-07-24T22:34:28`
- Cases run: `5`
- Passed: `5`
- Degraded: `1`
- Failed: `0`
- Days to expiry: `0.25`
- Contract multiplier: `50`

## Provider Scorecard

| Case | Provider | Format | Symbol | Health | Messages | Frames | Parse Err | Dropped | Gamma Wall | Zero Gamma |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tradovate Live Frames | tradovate | tradovate | ES | degraded | 6 | 3 | 1 | 1 | 5,950.0 | 5,909.6 |
| Tradovate Metadata Join | tradovate | tradovate | ES | healthy | 3 | 1 | 0 | 0 | 5,950.0 | 5,907.4 |
| Databento GLBX Fixture | databento | databento | ES | healthy | 4 | 4 | 0 | 0 | 5,950.0 | 5,905.9 |
| yfinance ETF Options | yfinance | yfinance | SPY | healthy | 5 | 1 | 0 | 0 | 515.0 | 505.5 |
| Cboe Option Quotes CSV | cboe | cboe-option-quotes | SPY | healthy | 8 | 4 | 0 | 0 | 515.0 | 505.5 |

## Case Notes

### Tradovate Live Frames

- Fixture: `tests/fixtures/tradovate_live_sample.jsonl`
- Description: Sanitized WebSocket-style quote frames with one intentionally malformed quote for feed-health testing.
- Command: `gex-terminal inject-provider tests/fixtures/tradovate_live_sample.jsonl --provider tradovate --symbol ES`
- Result: `degraded` health, `6` normalized messages, `3` provider frames.
- Levels: gamma wall `5,950.0`, zero gamma `5,909.6`, net GEX `+34.45M`.
- Notes: `provider frame parse errors recorded; malformed payloads recorded; unsupported or off-symbol payloads dropped`

### Tradovate Metadata Join

- Fixture: `tests/fixtures/tradovate_md_quotes.json`
- Description: Quote payload joined to sanitized contract-discovery metadata.
- Command: `gex-terminal inject-provider tests/fixtures/tradovate_md_quotes.json --provider tradovate --symbol ES --metadata tests/fixtures/tradovate_contract_discovery.json`
- Result: `healthy` health, `3` normalized messages, `1` provider frames.
- Levels: gamma wall `5,950.0`, zero gamma `5,907.4`, net GEX `+28.23M`.
- Notes: `feed checks clean`

### Databento GLBX Fixture

- Fixture: `tests/fixtures/databento_trade_records.json`
- Description: Synthetic GLBX.MDP3 definitions, option trades, and underlying mbp-1 quote sample.
- Command: `gex-terminal inject-provider tests/fixtures/databento_trade_records.json --provider databento --symbol ES --metadata tests/fixtures/databento_definition_records.json --underlying-fixture tests/fixtures/databento_underlying_mbp1_record.json`
- Result: `healthy` health, `4` normalized messages, `4` provider frames.
- Levels: gamma wall `5,950.0`, zero gamma `5,905.9`, net GEX `+10.97M`.
- Notes: `feed checks clean`

### yfinance ETF Options

- Fixture: `tests/fixtures/yfinance_option_chain_records.json`
- Description: Delayed equity/ETF option-chain sample for SPY-style research.
- Command: `gex-terminal inject-provider tests/fixtures/yfinance_option_chain_records.json --provider yfinance --symbol SPY`
- Result: `healthy` health, `5` normalized messages, `1` provider frames.
- Levels: gamma wall `515.0`, zero gamma `505.5`, net GEX `+1.24M`.
- Notes: `feed checks clean`

### Cboe Option Quotes CSV

- Fixture: `tests/fixtures/cboe_option_quotes_sample.csv`
- Description: Cboe-style option quote CSV sample using common column names.
- Command: `gex-terminal inject-provider tests/fixtures/cboe_option_quotes_sample.csv --fixture-format cboe-option-quotes --symbol SPY`
- Result: `healthy` health, `8` normalized messages, `4` provider frames.
- Levels: gamma wall `515.0`, zero gamma `505.5`, net GEX `+1.24M`.
- Notes: `feed checks clean`

## Contributor Uses

- Confirm that adapter changes still produce computable snapshots offline.
- Share one report when proposing a new provider fixture or parser change.
- Compare provider health counters before opening a live-data debugging issue.
- Keep fixture samples sanitized so reports are safe to post publicly.

## Recommended Next Checks

- Review degraded health counters in: tradovate-live-sample.
- Attach the Markdown report to provider-adapter issues or pull requests.
- Use the JSON report as a baseline when changing adapter normalization.
- Add new sanitized provider samples as fixture cases before wiring live credentials.

# Market-Data Adapters

`gex-terminal` keeps market-data ingestion separate from calculation and UI code.
Adapters are responsible for translating provider-specific payloads into the
small normalized message contract consumed by `StatefulGexConsumer`.

## Adapter Contract

Adapters implement `MarketDataAdapter`:

```python
class MarketDataAdapter(ABC):
    async def stream_market_data(self) -> None:
        ...
```

The adapter should call `consumer.update_market_state(...)` with JSON messages
created by `dumps_normalized_message`.

## Normalized Messages

Underlying ticks:

```json
{
  "schema_version": 2,
  "type": "underlying_tick",
  "provider": "example",
  "symbol": "ES",
  "price": 5943.25,
  "event_time": "2026-08-04T17:30:00Z"
}
```

Options volume ticks:

```json
{
  "schema_version": 2,
  "type": "options_volume_tick",
  "provider": "example",
  "contract_id": "example-es-option-123",
  "symbol": "ES",
  "strike": 5950,
  "option_type": "C",
  "volume": 100,
  "iv": 0.15,
  "iv_source": "provider",
  "expiry": "2026-08-07",
  "expiry_timestamp": "2026-08-07T20:00:00Z",
  "instrument_class": "futures_option",
  "volume_semantics": "cumulative",
  "position_source": "trade_volume",
  "contract_multiplier": 50,
  "event_time": "2026-08-04T17:30:00Z"
}
```

Schema v2 requires provider, contract ID, symbol, expiry, instrument class,
volume semantics, position source, positive IV, IV source, and a timezone-bearing
event time in addition to strike, option type, and volume. `incremental` volume must be positive and accumulates;
`cumulative` volume may be zero and replaces the prior absolute value for that
provider contract and position source. `position_source` is `trade_volume` or
`open_interest`. If both exist, the consumer prefers positive trade volume and
otherwise falls back to open interest rather than summing them.

Futures options map to Black-76; equity and index options map to Black-Scholes.
`iv_source` is `provider` or `configured_default`. Adapters that use a fallback
IV must label it and expose degraded feed quality. A
timezone-bearing `expiry_timestamp` can drive fractional DTE; a date-only
`expiry` label supports filtering but cannot silently invent settlement time.

Messages without `schema_version` remain schema v1. They preserve the original
strike-level Black-Scholes and incremental-volume behavior for existing replay
fixtures. Mixed v1/v2 sessions report a legacy fallback calculation instead of
claiming contract-aware provenance.

## Provider Selection

List known providers:

```bash
gex-terminal --providers
```

Select a live provider:

```bash
gex-terminal --mode live --provider tradovate --symbol ES
gex-terminal --mode live --provider databento --symbol ES
gex-terminal --mode live --provider ibkr --symbol ES
gex-terminal --mode live --provider yfinance --symbol SPY
```

`replay` is selected automatically when using `--replay`.

## Replay Adapter

The replay adapter reads normalized JSONL records from disk. Select packaged
sessions by name so commands work from an installed wheel:

```bash
gex-terminal list-replays
gex-terminal --replay-session demo
gex-terminal --replay-session full-session
```

Replay files are the preferred way to reproduce UI and engine behavior without
live credentials. `demo_replay.jsonl` is a compact screenshot/demo fixture, while
`es_synthetic_full_session.jsonl` simulates open, mid-session, and late-session
ES 0DTE activity for contributor testing.

The in-terminal replay browser uses the same normalized JSONL contract. In demo
or replay mode, pressing `p` opens the browser, Enter loads the selected bundled
session, and the TUI resets consumer state through the consumer and engine path.
It does not run in live mode.

The replay adapter also verifies and replays
`gex-terminal.captured-session.v1` files. Captures default to event-time pacing;
legacy JSONL defaults to fixed delay. See
[captured-sessions.md](captured-sessions.md) for capture integrity and timing
controls.

## Tradovate Adapter

The Tradovate adapter currently includes:

- Local credential validation before network calls.
- REST authentication with distinct REST and market-data tokens plus renewal.
- Product, contract-maturity, contract dependency, and bounded suggestion
  discovery. Exact `contract/find` is not treated as an option-chain endpoint.
- Official raw-token WebSocket authorization frames and explicit authorization
  and subscription acknowledgement gates.
- Nested quote-entry mapping for underlying trades, `TotalTradeVolume`, and
  `OpenInterest`; cumulative provider values use schema-v2 cumulative semantics.
- Bounded reconnect/backoff, heartbeat, retryable HTTP handling, cancellation,
  and quote unsubscription during shutdown.
- Provider diagnostics for frame count, parse errors, dropped quotes,
  subscription status, subscribed symbol count, and reconnect count.
- Malformed quote quarantine so one bad option tick does not block other valid
  quotes in the same frame.

Sanitized fixtures ship under `gex_terminal/data/provider_fixtures/` and are
exercised from any installed location with `gex-terminal fixture-lab OUTPUT`.
They prove parser and software-path behavior, not credential, entitlement,
market coverage, or real reconnect behavior.

Official quote frames do not establish native implied volatility. If no joined
metadata supplies IV, the adapter uses its configured fallback, increments a
counter, and marks the model input degraded. Quantitative GEX is not certified
for such a run.

Run the explicit read-only certification gate only when you intend to open a
credentialed external connection:

```bash
gex-terminal tradovate-certify /tmp/tradovate-certification.json \
  --ack-live-network --tradovate-environment demo --symbol ES
```

The report is redacted and the command exits nonzero unless transport is
certified. The adapter remains registry status `scaffold`; this repository does
not claim a successful live or demo certification.

## Databento Adapter

The Databento adapter is scaffolded behind `--provider databento`. It validates
`DATABENTO_API_KEY`, keeps live ingestion isolated, and now includes tested
fixture-mapping helpers for `GLBX.MDP3` futures options definitions, trades,
underlying `mbp-1` quotes, and statistics-style open interest.

See [docs/databento-fixtures.md](databento-fixtures.md) for the synthetic
fixture design, schema mapping, and contributor rules. Live Databento streaming
is still future work; the current helpers are intended to make payload review
and normalization safer before credentials or entitlements are required.

Optional dependency:

```bash
pip install -e ".[databento]"
```

## Interactive Brokers Adapter

The IBKR adapter is scaffolded behind `--provider ibkr`. It expects TWS or IB
Gateway connection settings through `IBKR_HOST`, `IBKR_PORT`, and
`IBKR_CLIENT_ID`, and currently raises a clear setup message until contract and
tick normalization are implemented.

Optional dependency:

```bash
pip install -e ".[ibkr]"
```

## yfinance Adapter

The yfinance adapter is available behind `--provider yfinance`. It is intended
only for delayed equity/ETF options snapshots such as SPY or QQQ, not ES/NQ
futures options.

Optional dependency:

```bash
pip install -e ".[yfinance]"
gex-terminal --mode live --provider yfinance --symbol SPY
```

The adapter requests the nearest option expiration, publishes one delayed quote
and option-chain snapshot, then normalizes rows into the shared adapter contract.
It uses yfinance `volume` first and falls back to `openInterest` when volume is
missing. This is useful for no/low-cost ETF research, but it should not be
presented as a substitute for licensed futures options data. A sanitized example
chain ships as the `yfinance` case in the installed Provider Fixture Workbench.

## Adding a Provider

When adding a provider:

- Keep provider SDKs or protocol details inside `gex_terminal/adapters/`.
- Register the adapter in `gex_terminal/adapters/registry.py`.
- Normalize payloads before they reach `StatefulGexConsumer`.
- Add replay or fixture tests for representative provider payloads.
- Document required credentials and data entitlements.
- Avoid logging credentials, tokens, account IDs, or full raw frames containing
  private details.

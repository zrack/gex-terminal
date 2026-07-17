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
  "type": "underlying_tick",
  "symbol": "ES",
  "price": 5943.25
}
```

Options volume ticks:

```json
{
  "type": "options_volume_tick",
  "strike": 5950,
  "option_type": "C",
  "volume": 100,
  "iv": 0.15
}
```

Required option fields are `strike`, `option_type`, and `volume`. Implied
volatility is optional and falls back to the consumer default when omitted.

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

The replay adapter reads normalized JSONL records from disk:

```bash
gex-terminal --replay sample_data/demo_replay.jsonl
gex-terminal --replay sample_data/es_synthetic_full_session.jsonl
```

Replay files are the preferred way to reproduce UI and engine behavior without
live credentials. `demo_replay.jsonl` is a compact screenshot/demo fixture, while
`es_synthetic_full_session.jsonl` simulates open, mid-session, and late-session
ES 0DTE activity for contributor testing.

## Tradovate Adapter

The Tradovate adapter currently includes:

- Local credential validation before network calls.
- REST authentication.
- Initial contract discovery through `contract/find`.
- WebSocket quote subscription scaffolding.
- Underlying and option quote normalization hooks.

The remaining production task is validating exact option-chain and quote payload
shapes against live or demo Tradovate API access. Sanitized payload fixtures are
welcome.

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
presented as a substitute for licensed futures options data.

## Adding a Provider

When adding a provider:

- Keep provider SDKs or protocol details inside `gex_terminal/adapters/`.
- Register the adapter in `gex_terminal/adapters/registry.py`.
- Normalize payloads before they reach `StatefulGexConsumer`.
- Add replay or fixture tests for representative provider payloads.
- Document required credentials and data entitlements.
- Avoid logging credentials, tokens, account IDs, or full raw frames containing
  private details.

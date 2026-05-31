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

## Replay Adapter

The replay adapter reads normalized JSONL records from disk:

```bash
gex-terminal --replay sample_data/demo_replay.jsonl
```

Replay files are the preferred way to reproduce UI and engine behavior without
live credentials.

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

## Adding a Provider

When adding a provider:

- Keep provider SDKs or protocol details inside `gex_terminal/adapters/`.
- Normalize payloads before they reach `StatefulGexConsumer`.
- Add replay or fixture tests for representative provider payloads.
- Document required credentials and data entitlements.
- Avoid logging credentials, tokens, account IDs, or full raw frames containing
  private details.

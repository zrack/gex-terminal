# Databento Fixture Mapping

This note documents the first Databento fixture design for `gex-terminal`.
It is not a live Databento adapter yet. The current implementation adds
synthetic, sanitized payload fixtures and mapping helpers so contributors can
discuss and test the provider contract before paid credentials are required.

## Current Status

- Dataset target: `GLBX.MDP3`.
- Option-chain parent symbols: `ES.OPT`, `NQ.OPT`, or
  `<UNDERLYING>.OPT` for another futures root.
- Implemented locally: synthetic fixtures, option-definition metadata mapping,
  option-trade volume mapping, underlying quote mapping, and open-interest
  extraction from statistics-like rows.
- Not implemented yet: authenticated Databento client setup, live/historical
  requests, entitlement handling, symbol selection by active expiration, and
  official open-interest ingestion into the consumer state.

## Databento Schemas To Validate

These are the provider-side schemas the live adapter should eventually use:

| Purpose | Databento schema | Local fixture |
| --- | --- | --- |
| Futures option definitions | `definition` | `gex_terminal/data/provider_fixtures/databento_definition_records.json` |
| Option trades / volume | `trades` | `gex_terminal/data/provider_fixtures/databento_trade_records.json` |
| Underlying future quote | `mbp-1` | `gex_terminal/data/provider_fixtures/databento_underlying_mbp1_record.json` |
| Open interest / settlement stats | `statistics` | `gex_terminal/data/provider_fixtures/databento_statistics_records.json` |
| Expected normalized output | app JSONL contract | `gex_terminal/data/provider_fixtures/databento_normalized_expected.jsonl` |

Databento documents CME futures and futures options under the `GLBX.MDP3`
dataset, with `definition` records for instrument metadata, trade/quote schemas
for intraday events, and `statistics` records for values such as open interest
and settlement. The live adapter should verify exact field names from the Python
SDK object or DataFrame shape before routing messages into the app.

Useful provider references:

- [Options on futures introduction](https://databento.com/docs/examples/options/options-on-futures-introduction)
- [GLBX.MDP3 dataset](https://databento.com/docs/venues-and-datasets/glbx-mdp3)
- [Schemas and data formats](https://databento.com/docs/schemas-and-data-formats)
- [Open interest and settlement example](https://databento.com/docs/examples/futures/retrieving-oi-and-settlement-prices)

## Normalized App Contract

The app consumes only the shared normalized messages described in
[docs/adapters.md](adapters.md). Databento-specific fields stay inside
`gex_terminal/adapters/databento.py`.

Underlying quote:

```json
{
  "schema_version": 2,
  "type": "underlying_tick",
  "provider": "databento",
  "symbol": "ES",
  "price": 5943.25,
  "event_time": "2026-06-12T15:30:00Z"
}
```

Option volume tick:

```json
{
  "schema_version": 2,
  "type": "options_volume_tick",
  "provider": "databento",
  "contract_id": "12345",
  "contract_symbol": "ESM6 C5950",
  "symbol": "ES",
  "strike": 5950,
  "option_type": "C",
  "volume": 42,
  "iv": 0.15,
  "iv_source": "configured_default",
  "expiry": "2026-06-19",
  "instrument_class": "futures_option",
  "volume_semantics": "incremental",
  "position_source": "trade_volume",
  "aggressor_side": "buy",
  "direction_source": "provider",
  "event_time": "2026-06-12T15:30:00Z"
}
```

## Mapping Rules

| Normalized field | Databento source |
| --- | --- |
| `symbol` | Runtime target symbol such as `ES` or `NQ`, not the raw contract code |
| `price` | `price`, `close`, last-price field, or midpoint of bid/ask fields |
| `strike` | Definition `strike_price`, `strikePrice`, or `strike` |
| `option_type` | Definition class/put-call field, or `C`/`P` parsed from raw option symbol |
| `volume` | Trade `size`, `quantity`, or `volume` |
| `expiry` | Definition `expiration`, `expiration_date`, or `expiry` |
| `iv` | Positive provider IV when present; otherwise the explicit `0.15` configured default used by this fixture mapper. |
| `contract_id` | Stable Databento `instrument_id` scoped to provider `databento` |
| `event_time` | Timezone-bearing `ts_event` or equivalent provider event time |
| `volume_semantics` | `incremental` for individual trade sizes |
| `position_source` | `trade_volume` for trade messages; a future statistics mapping must use `open_interest` with `cumulative` semantics |
| `aggressor_side` | Databento trade `side`: `B`/bid maps to `buy`, `A`/ask maps to `sell`, and absent/indeterminate side maps to `unknown` |
| `direction_source` | `provider` when a known Databento side is preserved; otherwise `unknown` |
| `iv_source` | `provider` when supplied by a record/definition; otherwise the labeled `configured_default` fallback degrades feed quality |
| open interest | `statistics` rows with open-interest stat fields; extraction is fixture-tested but live ingestion remains unimplemented |

## Contributor Fixture Rules

- Use synthetic or sanitized payloads only.
- Do not include account IDs, API keys, order IDs, usernames, or raw private
  frames.
- Keep fixtures small enough for code review.
- Include the Databento dataset and schema name in the fixture wrapper.
- Include enough definition rows to join trade records by `instrument_id`.
- Add tests for every new field shape before changing live adapter behavior.
- Do not reinterpret aggressor side as observed customer/dealer identity or
  opening/closing classification.

## Verification

Run the Databento mapper tests:

```bash
python -m unittest -v tests.test_databento_mapping
```

Run the installed-resource workbench without referring to source paths:

```bash
gex-terminal fixture-lab /tmp/provider_fixture_lab.md
```

Run the full test suite before submitting fixture changes:

```bash
python -m unittest discover -s tests
```

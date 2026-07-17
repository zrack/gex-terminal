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
| Futures option definitions | `definition` | `tests/fixtures/databento_definition_records.json` |
| Option trades / volume | `trades` | `tests/fixtures/databento_trade_records.json` |
| Underlying future quote | `mbp-1` | `tests/fixtures/databento_underlying_mbp1_record.json` |
| Open interest / settlement stats | `statistics` | `tests/fixtures/databento_statistics_records.json` |
| Expected normalized output | app JSONL contract | `tests/fixtures/databento_normalized_expected.jsonl` |

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
  "type": "underlying_tick",
  "symbol": "ES",
  "price": 5943.25
}
```

Option volume tick:

```json
{
  "type": "options_volume_tick",
  "strike": 5950,
  "option_type": "C",
  "volume": 42,
  "expiry": "2026-06-19"
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
| `iv` | Optional. Databento trades/definitions do not provide a guaranteed live IV field, so IV may be omitted or supplied by a later model/source. |
| open interest | `statistics` rows with open-interest stat fields; not wired into consumer state yet |

## Contributor Fixture Rules

- Use synthetic or sanitized payloads only.
- Do not include account IDs, API keys, order IDs, usernames, or raw private
  frames.
- Keep fixtures small enough for code review.
- Include the Databento dataset and schema name in the fixture wrapper.
- Include enough definition rows to join trade records by `instrument_id`.
- Add tests for every new field shape before changing live adapter behavior.

## Verification

Run the Databento mapper tests:

```bash
python -m unittest -v tests.test_databento_mapping
```

Run the full test suite before submitting fixture changes:

```bash
python -m unittest discover -s tests
```

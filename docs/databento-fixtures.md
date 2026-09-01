# Databento Fixture Mapping

This note documents both the deterministic Databento fixture design and the
credentialed live path for `gex-terminal`. Fixtures remain available so the
provider contract can be reviewed without paid credentials; they do not certify
the live service.

## Current Status

- Dataset target: `GLBX.MDP3`.
- Option-chain parent symbols: `ES.OPT`, `NQ.OPT`, or
  `<UNDERLYING>.OPT` for another futures root.
- Implemented locally: official SDK live client setup, mixed `definition`,
  `trades`, and `mbp-1` subscriptions, option-definition joins, ES/NQ
  continuous-futures midpoint tracking, option-trade normalization, aggressor
  side, and Black-76 IV inversion with explicit provenance.
- Fixture-only: statistics/open-interest extraction. It is not yet subscribed
  into live consumer state.
- Operationally unverified in this repository: credentials, entitlements,
  current contract coverage, latency, reconnect gaps, and a successful
  `databento-certify` report.

## Databento Schemas To Validate

These are the provider-side schemas used or mapped by the adapter:

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
SDK records before routing messages into the app.

Useful provider references:

- [Options on futures introduction](https://databento.com/docs/examples/options/options-on-futures-introduction)
- [Live Python client](https://databento.com/docs/api-reference-live/client/live-blocking)
- [Parent and continuous symbology](https://databento.com/docs/standards-and-conventions/symbology)
- [GLBX.MDP3 dataset](https://databento.com/docs/venues-and-datasets/glbx-mdp3)
- [Schemas and data formats](https://databento.com/docs/schemas-and-data-formats)
- [Open interest and settlement example](https://databento.com/docs/examples/futures/retrieving-oi-and-settlement-prices)

## Normalized App Contract

The app consumes only the shared normalized messages described in
[docs/adapters.md](adapters.md); that document is the canonical wire-schema
example. Databento-specific parsing and joins stay inside
`gex_terminal/adapters/databento.py`.

Databento's main contract delta is IV inversion provenance. A
`black_76_inverted` option tick carries the option trade price/source, futures
midpoint/source, midpoint age and maximum allowed age, risk-free rate, time to
expiry, solver method/status/iterations, and absolute price error. Definition
records supply stable contract identity, strike, type, and expiry. Statistics
records map open interest as a cumulative quantity in fixture/offline flows;
the live statistics subscription remains roadmap work.

## Mapping Rules

| Normalized field | Databento source |
| --- | --- |
| `symbol` | Runtime target symbol such as `ES` or `NQ`, not the raw contract code |
| `price` | `price`, `close`, last-price field, or midpoint of bid/ask fields |
| `strike` | Definition `strike_price`, `strikePrice`, or `strike` |
| `option_type` | Definition class/put-call field, or `C`/`P` parsed from raw option symbol |
| `volume` | Trade `size`, `quantity`, or `volume` |
| `expiry` | Definition `expiration`, `expiration_date`, or `expiry` |
| `iv` | Positive provider IV when present; otherwise a converged Black-76 inversion from option trade price and the latest futures midpoint; otherwise the explicit configured fallback. |
| `contract_id` | Stable Databento `instrument_id` scoped to provider `databento` |
| `event_time` | Timezone-bearing `ts_event` or equivalent provider event time |
| `volume_semantics` | `incremental` for individual trade sizes |
| `position_source` | `trade_volume` for trade messages; fixture-tested statistics mapping uses `open_interest` with `cumulative` semantics, while live statistics subscription remains roadmap work |
| `aggressor_side` | Databento trade `side`: `B`/bid maps to `buy`, `A`/ask maps to `sell`, and absent/indeterminate side maps to `unknown` |
| `direction_source` | `provider` when a known Databento side is preserved; otherwise `unknown` |
| `iv_source` | `provider`, `black_76_inverted`, or `configured_default`; only the fallback degrades feed quality |
| `iv_provenance` | Required for inverted IV: method/status, option price/source, futures midpoint/source/time, rate, time to expiry, iterations, and absolute price error |
| open interest | `statistics` rows with open-interest stat fields; extraction is fixture-tested but live ingestion remains unimplemented |

## Live Subscriptions And Certification

The live adapter makes three subscriptions in one `GLBX.MDP3` session:

1. `definition` with parent symbols `ES.OPT`/`NQ.OPT` and `ES.FUT`/`NQ.FUT`,
   using the weekly definition replay available for this dataset.
2. `mbp-1` for the volume-based continuous future `ES.v.0` or `NQ.v.0`.
3. `trades` for the option parent `ES.OPT` or `NQ.OPT`.

The adapter matches definition `underlying_id` to the instrument ID currently
mapped by the continuous future. It counts and drops trades on other futures
months instead of inverting them against the wrong forward price.

Run a bounded, read-only report only when external access is intended:

```bash
gex-terminal databento-certify /tmp/databento-certification.json \
  --ack-live-network --symbol ES --multiplier 50 --certification-duration 20
```

The gate fails closed unless the full quantitative-input result passes. It reports
separate transport and chain-ingestion results; the final result requires
definitions, an underlying quote, option trades, at least one converged
Black-76 inversion, and zero fallback-IV ticks. This still does not establish
dealer inventory, synchronized executable quotes, or predictive validity.

Certify NQ in a separate run with `--symbol NQ --multiplier 20` and a distinct
report path. A partial report is still written for review, but the process exits
`2` unless the complete quantitative-input result passes.

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

Replay a mixed local provider stream through the live record handler and run the
adversarial matrix:

```bash
gex-terminal databento-replay \
  gex_terminal/data/provider_fixtures/databento_mixed_offline_records.jsonl \
  /tmp/databento-offline.json --symbol ES --multiplier 50
gex-terminal databento-offline-certify /tmp/databento-adversarial.json \
  --symbol ES --multiplier 50
```

These commands never open a network connection and never certify live transport.
See [offline-validation.md](offline-validation.md).

Run the Databento mapper tests:

```bash
python -m unittest -v tests.test_databento_mapping tests.test_databento_live \
  tests.test_databento_certification tests.test_implied_volatility
```

Run the installed-resource workbench without referring to source paths:

```bash
gex-terminal fixture-lab /tmp/provider_fixture_lab.md
```

Run the full test suite before submitting fixture changes:

```bash
python -m unittest discover -s tests
```

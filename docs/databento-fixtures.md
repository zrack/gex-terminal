# Databento Fixture Mapping

This note documents both the deterministic Databento fixture design and the
credentialed live path for `gex-terminal`. Fixtures remain available so the
provider contract can be reviewed without paid credentials; they do not certify
the live service.

## Current Status

- Dataset target: `GLBX.MDP3`.
- Option-chain parent symbols: `ES.OPT`, `NQ.OPT`, or
  `<UNDERLYING>.OPT` for another futures root.
- Implemented locally: official SDK live client setup; required `definition`,
  `mbp-1`, and `trades` requests; optional `statistics` request;
  option-definition joins; ES/NQ continuous-futures midpoint tracking;
  option-trade and OI normalization; aggressor side; Black-76 IV inversion;
  bounded shutdown; and reconnect/sequence diagnostics.
- Operationally unverified in this repository: credentials, entitlements,
  current contract coverage, licensed OI availability, latency, provider-side
  resubscription, recurring reliability, and a successful credentialed
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
- [Reconnect callback](https://databento.com/docs/api-reference-live/client/add-reconnect-callback)
- [Parent and continuous symbology](https://databento.com/docs/standards-and-conventions/symbology)
- [GLBX.MDP3 dataset](https://databento.com/docs/venues-and-datasets/glbx-mdp3)
- [Schemas and data formats](https://databento.com/docs/schemas-and-data-formats)
- [Common fields, flags, and sequence](https://databento.com/docs/standards-and-conventions/common-fields-enums-types)
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
records map open interest as a cumulative quantity in offline handling and the
optional live path; availability remains an observed status, not an assumption.

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
| `position_source` | `trade_volume` for trade messages; open-interest statistics use `open_interest` with `cumulative` semantics |
| `aggressor_side` | Databento trade `side`: `B`/bid maps to `buy`, `A`/ask maps to `sell`, and absent/indeterminate side maps to `unknown` |
| `direction_source` | `provider` when a known Databento side is preserved; otherwise `unknown` |
| `iv_source` | `provider`, `black_76_inverted`, or `configured_default`; only the fallback degrades feed quality |
| `iv_provenance` | Required for inverted IV: method/status, option price/source, futures midpoint/source/time, rate, time to expiry, iterations, and absolute price error |
| open interest | `statistics` rows whose statistic type represents open interest; availability stays explicit and separate from trade volume |

## Live Requests And Certification

The live adapter submits three required requests and one optional request in one
`GLBX.MDP3` session:

1. `definition` with parent symbols `ES.OPT`/`NQ.OPT` and `ES.FUT`/`NQ.FUT`,
   using the weekly definition replay available for this dataset.
2. `mbp-1` for the volume-based continuous future `ES.v.0` or `NQ.v.0`.
3. `trades` for the option parent `ES.OPT` or `NQ.OPT`.
4. Optional `statistics` for the option parent, requested with replay start so
   an entitled open-interest observation can enter consumer state.

`Live.subscribe(...)` returns a local integer request ID. The adapter records
which schemas returned IDs and which failed synchronously, but does not label an
ID as a provider acknowledgement. Provider records and explicit error frames
are the evidence that a requested path produced observations. Optional OI is
reported as `observed`, `unavailable`, `unsupported`, `entitlement_denied`, or
`not_requested`; a generic provider error is not silently attributed to OI.

The adapter matches definition `underlying_id` to the instrument ID currently
mapped by the continuous future. It counts and drops trades on other futures
months instead of inverting them against the wrong forward price.

Run a bounded, read-only report only when external access is intended:

```bash
gex-terminal databento-certify /tmp/databento-certification.json \
  --ack-live-network --symbol ES --multiplier 50 --certification-duration 20
```

The selected `databento-<symbol>-prelive-v1` policy is resolved before I/O.
Its ES and NQ profiles enforce canonical multipliers of `50` and `20`.
Both profiles currently require at least 50 provider frames, 24 definitions, 5
underlying quotes, 20 option trades, 12 normalized option states, 2 expiries, 8
strikes, and 12 trade-sequence observations. Freshness, sequence
coverage/integrity, multiplier coverage, usable-IV coverage, and inverted-IV
age coverage must each be 100%; fallback-IV and inversion-failure coverage must
be zero; maximum observed underlying age is 2,000 ms. These are
repository-owned pre-live policy choices, not an empirically validated claim of
market sufficiency.

The gate fails closed unless the full quantitative-input result passes. It
reports transport, chain-ingestion, target-identity, quantitative-input, and
open-interest results separately. `open_interest_observed` states whether an OI
record was seen; `open_interest_window_validated` states whether the window
observed OI while also passing chain ingestion. OI observation is not required
for the trade-volume path, so unavailable OI remains visible without being
substituted or treated as a validated OI window.
This still does not establish dealer inventory, synchronized executable option
quotes, predictive validity, or ongoing reliability.

Certify NQ in a separate run with `--symbol NQ --multiplier 20` and a distinct
report path. A partial report is still written for review, but the process exits
`2` unless the complete quantitative-input result passes.

## Lifecycle And Sequence Evidence

The adapter requests the SDK reconnect policy and registers reconnect and
callback-error callbacks. It records callback boundaries and the first provider
frame seen afterward. The report's post-reconnect/resubscription observation
means only that data resumed after the callback; it is not a per-schema
resubscription acknowledgement. A quiet window can pass without manufacturing
a reconnect, provided callback registration and all other gates pass.

Shutdown is part of the transport contract. The pinned SDK's `stop()` call is
nonblocking; awaitable stop implementations and `wait_for_close()` run under
bounded timeouts. A closure timeout invokes the SDK termination fallback,
increments the stop-error count, and prevents `clean_stop=true`.

Databento `sequence` is a venue sequence. Since `trades` is a subset of venue
messages, jumps between trade records can be expected and are reported only as
descriptive discontinuities/skipped values. Duplicates are also reported. The
certification integrity failure signal is a maybe-bad-book flag or an observed
out-of-order value; a gap in the numbers alone is not called feed loss.

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
  tests.test_databento_certification tests.test_databento_certification_policy \
  tests.test_implied_volatility
```

Run the installed-resource workbench without referring to source paths:

```bash
gex-terminal fixture-lab /tmp/provider_fixture_lab.md
```

Run the full test suite before submitting fixture changes:

```bash
python -m unittest discover -s tests
```

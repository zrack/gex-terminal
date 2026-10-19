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
  "volume_semantics": "incremental",
  "position_source": "trade_volume",
  "aggressor_side": "buy",
  "direction_source": "provider",
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

Open-interest messages may additionally carry the pair
`open_interest_reference_date` (an ISO `YYYY-MM-DD` date) and
`open_interest_update_action` (`add` or `delete`). They are valid only for
cumulative `open_interest` and must appear together. The reference date identifies
the trading date measured; `event_time` remains the publication or revision time.
The reference date cannot follow the UTC publication date.
The consumer selects the newest reference date before comparing publication
times within that date. A delete carries zero quantity and retains a tombstone,
so an older observation cannot restore the deleted value. An added zero is an
observed zero; a delete means withdrawn data, and an absent observation remains
unavailable. Messages omitting both fields retain their existing sequence
behavior, but cannot replace a dated OI observation once one exists. Positive
trade volume stays a separate state and retains precedence.

Sequenced, incremental Databento trade-volume messages may carry
`provider_trade_event_id`, a lowercase SHA-256 fingerprint of the native trade
record. A venue sequence can contain several distinct trades. Identified fills
with the same sequence accumulate separately; exact fingerprint retransmissions
and lower sequences are rejected. Only the current sequence group's identifiers
are retained, with a 4,096-entry bound that rejects further entries rather than
evicting duplicate evidence. Captured-session intake preserves this validated
field; frozen checkpoints export aggregated quantities without the identifier
cache. Other providers, cumulative quantities, OI and older messages without the
field retain their existing ordering behavior.

`contract_multiplier` is the dollar value of one price point per option contract.
A provider field with the same name may instead count deliverable contracts;
adapters must establish its unit before emitting a normalized multiplier.
Missing supported dollar metadata leaves the normalized multiplier absent;
the consumer then uses its explicit configured fallback and records that
fallback in snapshot provenance.

Schema-v2 underlying ticks may carry a provider-scoped `contract_id`; option
ticks may link to it through `underlying_contract_id`. Linked positions are
eligible for calculation only while that provider's current futures contract
matches. A rollover preserves old raw quantities and OI tombstones for
inspection but quarantines their exposure. A later quote on a retired contract,
an older quote, or an identity-less quote replacing an identified quote is
rejected. Returning to a retired mapping requires an explicit consumer
`reset_state` and a fresh identity session. Identity-free legacy sessions keep
their existing behavior; a known option link survives later metadata omissions.
Provider timestamps preserve nanosecond ordering, including revisions within
the same microsecond.

Feed-quality reports include `underlying_identity` when a current/retired
contract, quarantined position or rejected quote provides identity evidence.
Identity-free legacy sessions omit the empty field so saved research receipts
retain their original decision hashes; identity evidence remains bound by the
receipt integrity check.

Schema v2 may also carry optional trade-direction provenance. `aggressor_side`
is `buy` or `sell`; `direction_source` is `provider` or `quote_inference`.
Known direction is valid only for incremental `trade_volume`. Missing direction,
cumulative volume, and open interest remain explicitly unknown rather than being
inferred. See [model-comparison.md](model-comparison.md).

Futures options map to Black-76; equity and index options map to Black-Scholes.
Optional `exercise_style` is `american`, `european`, or `unknown`; omission stays
unknown. `exercise_style_source` and `provider_cfi` retain supporting provider
metadata. Style describes the contract rather than selecting a different
formula: both implemented formulas assume European exercise. American rows are
explicitly labeled as an approximation with unmeasured error; unknown rows
remain unqualified. See [model assumptions](model-assumptions.md).
`iv_source` is `provider`, `black_76_inverted`, or `configured_default`.
Black-76 inversion requires its complete timing and solver provenance. Adapters
that use a configured fallback IV must label it and expose degraded feed
quality. A
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

Acknowledgement waits process each frame's event array in wire order. A matching
successful response is retained while later market-data events are routed;
success is returned only after the frame has been processed. A matching failed
response or an `error`/`md/error` event prevents success, including when it
appears after a successful response in the same frame. Unrelated request IDs
cannot satisfy the acknowledgement wait. Connected/subscribed transitions occur
only after the corresponding wait succeeds. Processing stops at a fatal error;
market updates accepted before that error remain retained.

Acknowledgement IDs must be JSON integers; a boolean or floating-point value
cannot satisfy a request ID. Status values must be finite integers. Numeric
inputs reject booleans and nonfinite values before conversion. Prices, strikes,
IV, multipliers, and timeouts must be positive; contract counts and retry counts
must be integral, with zero allowed for reconnect attempts. Cumulative
quantities and sequences may be zero but cannot be negative or fractional.
Integral numeric strings remain supported. A numeric `Retry-After` is capped
at 30 seconds; an invalid value uses the bounded exponential retry delay.

Shutdown awaits both owned heartbeat and renewal tasks and attempts subscription
and socket cleanup even if one background task has already failed. Such a
failure records a subscription error. Malformed-quote and background-task logs
retain an exception type instead of arbitrary provider values.

### Implemented Mapping And Evidence Boundaries

The current discovery path calls `product/find`, `contractMaturity/deps`, and
`contract/deps`, then adds a bounded `contract/suggest` fallback. It enriches
contracts with the available maturity expiry and product point value,
deduplicates candidates, selects an underlying, caps option subscriptions, and
registers metadata by contract ID and symbol. These mechanics can be tested
locally; they do not establish that the selected contracts cover the current
ES/NQ option universe.

The [official API reference](https://api.tradovate.com/), reviewed on
2026-10-18, documents
`contract/getoptionschain` as a response object containing `products`,
`contractMaturities`, and `contracts`, rather than a flat chain of fully joined
option rows. This adapter does not call that endpoint. The published `Contract`
schema contains `id`, `name`, `contractMaturityId`, and `timestamp`;
`ContractMaturity` provides `expirationDate` and an optional `underlyingId`.
The reference alone does not establish the extra option metadata required by
this adapter's current discovery path.

Accepted aliases such as `strikePrice`, `callPut`/`putCall`/`optionType`,
`impliedVol`/`impliedVolatility`/`iv`, and extra expiry fields are implementation
compatibility paths. Their presence in constructed fixtures is not evidence
that Tradovate returns them for ES/NQ. The legacy flat quote path remains
schema v1 and incremental; it is not a verified provider chain format.

The documented market-data example is nested: quotes carry `contractId`,
`timestamp`, and `entries`, including `Trade.price`, `TotalTradeVolume.size`,
and `OpenInterest.size`. The adapter joins the quote to its registered metadata
and emits schema-v2 cumulative trade-volume and open-interest messages
separately. Repeated absolute values replace prior state rather than adding
again. Positive trade volume takes precedence for calculation; otherwise
positive OI can supply the fallback position source. The two quantities are
never summed, and neither establishes dealer inventory.

The documented quote example does not establish native implied volatility.
When no IV value is present in the quote and joined metadata, the adapter
uses its configured fallback, increments a counter, and marks the input
degraded. Quantitative GEX is not certified for such a run. A tolerated IV alias
with a synthetic value proves only that the software accepts that input;
actual field availability, units, and provenance still require provider
evidence. A missing or timezone-naive quote clock similarly produces a labeled
receipt-time fallback rather than proof of a provider event time.

The bounded, explicitly synthetic chain fixture lives at
`gex_terminal/data/provider_fixtures/tradovate_option_chain_synthetic.json`.
Its regression tests drive the production adapter and consumer; they do not
authenticate an observed provider payload. Other local provider fixtures can
be exercised from an installed location with `gex-terminal fixture-lab OUTPUT`.
The [offline regression matrix](offline-validation.md#tradovate-offline-regression-matrix)
covers discovery, mapping, malformed inputs, acknowledgement ordering, scripted
lifecycle behavior, and negative certification gates without credentials.

### Provider Access And Remaining Qualification

Tradovate's [retail API-access instructions](https://tradovate.zendesk.com/hc/en-us/articles/4403105829523-How-Do-I-Get-Access-to-the-Tradovate-API)
currently require a live account holding more than $1,000, the CME information
license agreement, and the API Access add-on to generate a retail API key.
The key's [Contract Library and Market Data permissions](https://tradovate.zendesk.com/hc/en-us/articles/4408873526547-How-Do-I-Change-My-API-Key-Permissions)
are separate. Choosing the demo environment selects the simulation REST
service; it does not establish a waiver of API access or market-data rights.
The [market-data guidance](https://tradovate.zendesk.com/hc/en-us/articles/115011506088-What-are-the-non-professional-market-data-rates)
distinguishes top of book from market depth and requires depth for the DOM.
It does not establish that Level 2 is universally required to discover a full
option chain. Record the actual account's permissions, subscriptions, and
observed response rather than infer them from an environment flag.

[Issue #4](https://github.com/zrack/gex-terminal/issues/4) remains open until
actual sanitized **demo or live** ES/NQ payloads and their field mappings are
reviewed, including the IV field or its absence and entitlement/setup notes.
Synthetic regressions do not satisfy that requirement. This payload-mapping
gate is distinct from broader credentialed coverage, latency, reconnect, and
quantitative-input qualification; closing the mapping issue would not
automatically certify those broader capabilities or promote registry status.

The separate read-only `tradovate-capture` command prepares that observation by
retaining bounded contract REST responses and market-data WebSocket evidence
before normalization. It requires explicit network acknowledgement and a valid
capture policy, writes only to a new private directory, excludes authentication
material, and records limits and omissions. It does not change this adapter's
discovery implementation, accept unverified aliases as observed fields, or
automatically produce shareable fixtures. Follow
[Tradovate Raw-Payload Capture](tradovate-capture.md) for setup, separate ES/NQ
runs, file interpretation, and review. Actual retained samples still require
validation before issue #4 can close.

Run the explicit read-only certification gate only when you intend to open a
credentialed external connection:

```bash
gex-terminal tradovate-certify /tmp/tradovate-certification.json \
  --ack-live-network --tradovate-environment demo --symbol ES
```

The report is redacted and the command exits nonzero unless transport is
certified. Transport requires authentication, acknowledged authorization and
subscriptions, frames and normalized messages, a connected state at the end of
the observation window, and no recorded probe or entitlement errors. The probe
reads the connection state before its own cancellation closes an otherwise
healthy session; an earlier disconnect cannot pass on old success flags. It
reads final subscription and error counters after awaited cleanup, so a failure
discovered during shutdown still invalidates the result.

A transport pass can contain only underlying messages. The separate
quantitative gate also requires accepted underlying and option state, no IV
or receipt-time fallback, and no recorded parse, dropped-message, or malformed
input errors. It requires zero accepted legacy option ticks and zero untimed
market events, reported as `model_inputs.legacy_option_tick_count` and
`model_inputs.untimed_market_event_count` in JSON and in the Markdown report.
The legacy flat compatibility path remains available, but its schema-v1 option
ticks cannot pass the quantitative gate even if a timestamp is supplied.
Reported option-contract counts deduplicate the trade-volume and OI states for
the same provider/contract identity. Authentication capability flags are known
only when the response contains a literal JSON boolean; strings, numbers and
other values are reported as unknown.
`native_implied_volatility_observed` describes the implementation's
accepted IV inputs; the name does not turn an unverified alias or synthetic
value into provider evidence. Report errors retain an exception type and a
fixed reason rather than arbitrary provider/library message text. The adapter
remains registry status `scaffold`; this repository does not claim a successful
live or demo certification.

## Databento Adapter

The Databento adapter is implemented behind `--provider databento` for ES and
NQ. It validates `DATABENTO_API_KEY` and the optional SDK, then opens one
mixed-schema `GLBX.MDP3` session. It submits three required requests and one
optional request:

- `definition` replay for the configured option-product parent universe and
  `<ROOT>.FUT` with parent symbology.
- `mbp-1` for the volume-based continuous future `<ROOT>.v.0`.
- `trades` for that option-product universe with provider aggressor side preserved.
- Optional `statistics` for the same universe's open interest.

ES/NQ daily, weekly, end-of-month and quarterly options have distinct product
parents. The adapter keeps those provider product families separate from the
normalized `ES`/`NQ` futures underlying. Diagnostics record configured parents and
families actually observed; a submitted parent list does not establish complete
live coverage. [Databento Fixture Mapping](databento-fixtures.md) owns the defaults
and provider-specific field units.

The integer returned by the SDK for each request is a local request ID, not a
provider acknowledgement. Diagnostics therefore distinguish requested schemas,
schemas for which a request ID returned, failed schemas, and records actually
observed. Required-request submission without synchronous error is necessary
but not sufficient for certification.

Option trades join to point-in-time definitions. If a provider IV is absent,
the adapter uses the trade price, latest futures midpoint, authoritative expiry
timestamp, and configured risk-free rate to invert Black-76. A converged value
uses `iv_source=black_76_inverted` and carries an `iv_provenance` object. Missing,
out-of-bounds, or non-convergent inputs use the separately labeled configured
fallback and degrade feed quality.
An option definition's `underlying_id` must match the current continuous-future
instrument ID for both trades and OI additions; other futures months are counted
and dropped rather than priced against the wrong forward. OI additions arriving
before a usable quote identifies the selected future are dropped without
buffering. A statistics delete can invalidate known OI without a current quote
because it creates no exposure. Bootstrap and identity-mismatch counters make
those drops explicit.

Databento's definition `contract_multiplier` counts deliverables and is not used
as the app's dollar multiplier. Supported, scaled `unit_of_measure_qty` with
`USD`/`IPNT` units and the canonical ES/NQ point value supplies dollar metadata;
otherwise the app retains its configured fallback. Undefined provider values
cannot become plausible prices, multipliers or added OI quantities. A statistics
delete carries zero regardless of its unused provider quantity.

Open interest remains a separate cumulative position source. Its status is one
of `observed`, `invalidated`, `unavailable`, `unsupported`, `entitlement_denied`, or
`not_requested`. Optional OI failure does not silently become trade volume and
does not block a trade-volume certification path. The report distinguishes
`open_interest_observed` from `open_interest_window_validated`. The latter is
true only when OI was observed and the chain-ingestion gate passed. An explicit
unavailable/unsupported state may leave the trade-volume path eligible, but it
does not validate OI for that window.
Statistics must carry a valid reference trading date and add/delete action.
The adapter preserves publication `ts_event` as `event_time` and emits the
reference date/action separately. Consumer revision ordering and deletion rules
are defined in [Normalized Messages](#normalized-messages).
Accepted deletes are counted separately; `invalidated` means no active OI
observation remains after deletion, while an accepted added zero is `observed`.

The live client requests the SDK reconnect policy and registers a callback.
Diagnostics distinguish callback registration, callback errors, observed
reconnect boundaries, and frames seen after a reconnect. A post-reconnect frame
is bounded resumption evidence, not an acknowledgement that every schema was
resubscribed. If no reconnect occurs during a run, the report says so rather
than manufacturing an event.

Sequence diagnostics preserve Databento venue sequence values by publisher and
channel. Because a trades stream omits non-trade venue messages,
nonconsecutive values and repeated sequence values are descriptive. Repeated
values may describe distinct native trades; trade retransmissions are checked
using the separate native fingerprint. The quantitative gate
fails on the provider maybe-bad-book flag or observed out-of-order sequence, not
on a numeric discontinuity alone.

Shutdown calls the pinned SDK's nonblocking `stop()` and awaits
`wait_for_close()` under a bounded timeout; awaitable stop implementations are
bounded too. Only confirmed closure sets `clean_stop=true`; timeout or failure
records a stop error and uses the SDK termination fallback.

See [Databento Fixture Mapping](databento-fixtures.md) for the policy values,
synthetic fixture design, live mapping, and contributor rules. Fixture and
scripted-client success do not establish authentication, entitlements, current
ES/NQ coverage, licensed OI availability, latency, or provider-side reconnect
behavior.

Run the bounded redacted gate with explicit network acknowledgement:

```bash
gex-terminal databento-certify /tmp/databento-certification.json \
  --ack-live-network --symbol ES --multiplier 50 --certification-duration 20
```

The adapter registry status remains `live-uncertified`. The command selects the
versioned ES or NQ policy before network I/O, rejects a noncanonical multiplier,
and writes all required-versus-observed checks into the report. A credentialed
report that clears transport, chain-ingestion, and quantitative-input checks is
necessary evidence for its exact symbol, dataset, credential, entitlement set,
and run window. It does not automatically promote a global adapter label;
promotion requires maintainer-approved recurrence evidence. Predictive validity
remains unmeasured.

Run NQ independently with `--symbol NQ --multiplier 20` and a different output
path. The command writes partial evidence but exits `2` unless the complete
quantitative-input gate passes; exit `0` is not awarded for transport alone.

Black-76 inversion also requires the futures midpoint to precede the option
trade by no more than `--max-underlying-age` seconds (default `2`). Quote age is
preserved in `iv_provenance`. Future-dated, stale, crossed, one-sided, and
wrong-contract inputs cannot produce inverted IV.

Local JSON/JSONL/DBN records can use the identical handler through
`databento-replay`; `databento-offline-certify` runs the deterministic
adversarial matrix. See [offline-validation.md](offline-validation.md).

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

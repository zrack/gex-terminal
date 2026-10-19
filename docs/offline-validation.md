# Offline Validation Workbench

The offline validation workbench exercises provider mapping, temporal integrity,
position-source comparisons, and saved-price behavior without opening a market
data connection. Passing these workflows is software evidence, not live-provider
or predictive certification.

## Tradovate Acknowledgement Frames

Run the in-memory frame and scripted-session regressions without credentials:

```bash
python -m unittest -v tests.test_tradovate_ack_frames tests.test_tradovate_adapter tests.test_tradovate_protocol tests.test_tradovate_certification
```

The cases exercise matching acknowledgements interleaved with market data,
trailing errors, unrelated request IDs and authorization/subscription state
gates. Frames pass through the production adapter; controlled sessions verify
delivery to the consumer. A successful response must not discard later events
from its frame, and matching failed responses or `error`/`md/error` events in
that frame prevent success.

These constructed frames verify software behavior. They do not satisfy the
actual-provider-payload requirement of
[issue #4](https://github.com/zrack/gex-terminal/issues/4). Tradovate remains
`scaffold`; no live access or payload capture is part of this test command.

## Tradovate Offline Regression Matrix

Run the production-path mapping, discovery, lifecycle, and certification
regressions together without credentials:

```bash
python -m unittest -v tests.test_tradovate_option_chain tests.test_tradovate_parameters tests.test_tradovate_lifecycle tests.test_tradovate_adapter tests.test_tradovate_protocol tests.test_tradovate_ack_frames tests.test_tradovate_certification
```

The bounded fixture
`gex_terminal/data/provider_fixtures/tradovate_option_chain_synthetic.json`
uses the custom envelope `gex-terminal.synthetic-tradovate-chain-scenarios.v1`.
Its provenance declares `origin=constructed` and
`observed_provider_payload=false`. Two ES/NQ scenarios supply fixture metadata
and nested quote frames to the production adapter and consumer instead of
merely asserting that invented JSON fields exist. The envelope is not a
Tradovate API schema or authenticated market sample.

| Area | Offline evidence | Evidence ceiling |
| --- | --- | --- |
| Discovery | Scripted REST product/maturity/dependency requests, suggestion fallback, deduplication and the configured contract cap | Does not establish the real ES/NQ option universe or provider field availability |
| Position mapping | Nested quote entries joined to fixture metadata; cumulative trade volume and OI retained separately | Does not establish actual OI entitlement, publication cadence, or dealer inventory |
| Input boundaries | Missing and malformed contract/quote fields, invalid numeric and time inputs, plus valid neighbors in a frame | Does not establish which fields the service currently sends |
| Parameters | Finite positive prices, IV and timeouts; integral quantities and limits; typed acknowledgement IDs/status; bounded `Retry-After` | Does not establish provider field units or permission to coerce unsupported values |
| Frame ordering | Matching/unrelated IDs, market data before and after acknowledgements, trailing errors, timeout and cancellation | Does not measure network latency or a service-side reconnect |
| Lifecycle | Scripted retry, renewal, reconnect, subscription and shutdown paths | Does not establish actual authentication, entitlements or server-side resubscription |
| Certification failure | Incomplete or failed scripted runs keep the relevant gate false; fallback IV remains degraded | A synthetic passing report is a test of the report contract, not a real certification |

The scripted lifecycle cases cover rejected/challenged authentication, bounded
HTTP retry exhaustion, distinct REST and market-data tokens through renewal,
renewal failure, reauthorization and resubscription on a second mock socket,
reconnect exhaustion, and cancellation that awaits both owned background tasks
before completing cleanup. These assertions exercise the implementation's
calls and state transitions without contacting the service.
An already-failed heartbeat must not prevent awaiting the renewal task,
unsubscribing the contracts, or closing the socket. The failure still records
a subscription error and cannot produce a successful certification report.

Negative certification cases distinguish an authorized transport from useful
model inputs. A run that already disconnected, reported a probe error or lacked
the required acknowledgement/message evidence cannot retain an earlier
transport pass. Underlying-only traffic does not pass the quantitative gate;
neither do configured IV, receipt-time fallback, recorded input errors, accepted
legacy option ticks or untimed market events. The last two counters appear in
`model_inputs` as `legacy_option_tick_count` and `untimed_market_event_count`,
and in Markdown output. A timestamp on a legacy schema-v1 option does not make
that option eligible for quantitative certification. Authentication capability
tests also keep malformed string or numeric values unknown rather than coerce
them into a claimed boolean permission.
Error reports retain fixed reason text rather than the original exception
message. The observation-window connection state is sampled before the probe's
own normal cancellation so cleanup does not manufacture a run-window failure.
Final error and subscription counters are read after cleanup to retain failures
that become visible only while awaiting background tasks. A `TimeoutError`
raised by the stream itself is a probe failure, not the normal observation
deadline. Volume and OI for one option count as one normalized contract.

Schema-v2 absolute volume observations replace earlier values; they must not
accumulate merely because the same quote arrives twice. OI remains a separate
cumulative source, with positive trade volume preferred for the selected
snapshot. Missing IV uses the labeled configured fallback. Synthetic IV values
cannot establish that Tradovate supplies native IV. The original flat quote
compatibility path remains schema v1, with its legacy incremental behavior.

The fixture guard rejects known secret-bearing keys recursively, including
injected nested test cases. It is not a general PII detector or permission to
commit a real provider export; real captures still require the project's
[capture governance](capture-governance.md).

See [Tradovate mapping and qualification](adapters.md#implemented-mapping-and-evidence-boundaries)
for the difference between documented nested quote entries, tolerated metadata
aliases, and the still-unobserved ES/NQ payloads. The adapter's implemented
product/maturity/dependency discovery path does not call the documented
`contract/getoptionschain` endpoint or implement a new join for its grouped
response.

These tests may complete the offline portion of a contribution while
[issue #4](https://github.com/zrack/gex-terminal/issues/4) stays open. That issue
needs actual sanitized **demo or live** ES/NQ payloads, reviewed field mappings
including IV availability or absence, and entitlement/setup notes. Broader
credentialed coverage and real reconnect qualification are separate later
gates; no live connection is opened by the regression command above.

## Databento Record Replay

Replay mixed `definition`, `mbp-1`, `trades`, and `statistics` records from
JSON, JSONL, DBN, DBN.ZST, or DBZ:

```bash
gex-terminal databento-replay INPUT.jsonl OUTPUT.json \
  --symbol ES --multiplier 50 --max-underlying-age 2
```

DBN formats require the optional `.[databento]` dependency but do not require an
API key. JSON/JSONL records need a `record_type` or `schema` discriminator.
Records pass through the same Databento record handler used by live mode.

The report separates definitions, underlying quotes, option trades, OI updates,
IV inversion/fallback counts, dropped/control records, feed quality, and a
computed snapshot. `software_path_certified=true` requires aligned timestamps,
matching futures identity, at least one converged IV inversion, no fallback IV,
and no parse errors. `live_transport_certified` is always false.

## Expanded Databento Verification

The issue #35 test package adds three complementary forms of evidence:

- `tests/test_databento_parameters.py` exercises 1,774 parameter cases across
  all 52 ES/NQ product families, calls/puts, expiry horizons, units/fallbacks,
  SDK/decoded inputs and invalid boundaries. It uses an independent scalar
  Black-76 oracle.
- `tests/test_databento_state_machine.py` checks 6,000 events against a separate
  dictionary oracle with seeds `35`, `2035`, `6502` and `99035`, plus 256
  predefinition/prequote arrivals. Every accepted or rejected operation is
  reconciled, including zero, deletes, stale revisions and sequence resets.
- `tests/test_databento_rollover.py` verifies contract isolation, retired and
  delayed reconnect quotes, preserved raw state, reset behavior and nanosecond
  ordering. Old-month exposure must never use a different future's quote.

Run them without credentials:

```bash
python -m unittest -v tests.test_databento_parameters tests.test_databento_state_machine tests.test_databento_rollover
```

For installed functionality, first build a candidate wheel and install it with
its `.[databento]` dependency in a fresh virtual environment. Then run:

```bash
python scripts/verify_databento_functional.py --python /path/to/fresh-env/bin/python --wheel /path/to/candidate.whl --output /tmp/databento-functional.json
```

The worker runs outside the checkout, verifies all installed package bytes
against the candidate wheel and blocks socket connections. It invokes the
public CLI for equivalent synthetic JSONL and DBN sessions, checks independently
calculated GEX, quantities, multiplier provenance and futures identity, and
exercises terminal replay, keyboard export and the empty state after rollover.
The 18 cases cover initial OI, revisions, deletion and rollover for both ES/NQ;
the report retains an explicit inventory of generated inputs, outputs and SVGs.
Screenshots are headless Textual evidence, not a manual accessibility review.

Measure the changed provider handler rather than only normalized input:

```bash
python -m scripts.verify_databento_load --output /tmp/databento-provider-load.json
```

The default run streams 6,570 synthetic raw provider records over 52 families
and 208 contracts. It checks exact trade/OI state and accepted counts, revisions,
deletions, selected quantities and bounded state. Timing excludes snapshots,
tracemalloc and asyncio debug; a separate replay measures memory and repeats
correctness checks. The report records source hashes, environment, workload,
actual measurements and configured budgets; exit `2` means a gate failed.
Defaults are at least 50 records/second, at most 1,000 ms per sampled snapshot
and at most 256 MiB peak memory. These are offline test budgets, not live
capacity promises. Use `--help` to select a bounded larger workload or stricter
explicit budget.

## Temporal Integrity

Black-76 trade-price inversion records option and futures event times,
`underlying_price_age_ms`, `maximum_underlying_age_ms`, futures identity, option
price, futures midpoint, rate, time to expiry, iterations, and solver error.

A futures midpoint is not eligible when it is older than the configured limit,
timestamped after the option trade, missing event time, or mapped to another
futures contract. Crossed and one-sided books are also rejected. The option
trade may remain in the raw-volume model with labeled fallback IV, but the
quantitative-input gate fails.

## Adversarial Software Certification

```bash
gex-terminal databento-offline-certify offline_certification.json \
  --symbol ES --multiplier 50
```

The twelve deterministic cases cover the aligned path, trade-before-definition,
trade-before-underlying, stale and future-dated midpoints, wrong futures identity,
invalid option price, unknown control records, duplicate sequences, crossed and
one-sided books, and provider error records. This proves fail-closed software
behavior only.

Databento trade sequence numbers are venue sequence values, while the trades
schema is only a subset of venue events. A numeric jump between trades is
therefore descriptive, not proof of feed loss. The live-policy integrity check
uses the provider maybe-bad-book flag and observed out-of-order values; it also
reports discontinuities, skipped values, and duplicates for review.

## Scripted Live-Lifecycle Contract

`tests/test_databento_live.py` drives the production adapter with local scripted
clients. The matrix covers required request success/failure, optional
statistics outcomes, provider and entitlement errors, malformed records,
disconnect completion, reconnect callbacks, a frame after reconnect,
cancellation, and bounded shutdown.

These tests distinguish four different facts:

- A returned integer is a local subscription request ID, not a provider
  acknowledgement.
- Reconnect callback registration and invocation prove only that the callback
  path ran.
- A post-reconnect frame shows bounded data resumption, not that every schema
  was resubscribed or acknowledged.
- `clean_stop=true` requires the pinned SDK's nonblocking `stop()` request and
  bounded awaitable `wait_for_close()` to confirm closure; timeout records an
  error and exercises the termination fallback.

The scripted clients make lifecycle behavior deterministic. They cannot prove
SDK/service payload drift, real entitlements, provider-side replay, or network
reliability.

## Saved Price-Action Evaluation

Each input observation supplies a timestamp, decision-time spot, named levels by
model, optional directional coverage, and a strictly later `future_path`:

```json
{"timestamp":"2026-08-01T14:30:00Z","spot":6000,
 "models":{"raw":{"gamma_wall":6020,"zero_gamma":5975}},
 "future_path":[{"minutes":5,"price":6008}]}
```

```bash
gex-terminal price-action-evaluate INPUT.json OUTPUT.json
```

The report measures level distance, touches, crossings, terminal return, and
favorable/adverse moves. Observations receive chronological train, calibration,
and test labels. Results remain `descriptive_only`, `promotion_allowed=false`,
and `predictive_validity=unmeasured`.

## OI, Raw Volume, And Directionalized Comparison

Provide one timezone-bearing `as_of` and normalized messages containing an
underlying tick plus `open_interest` and `trade_volume` option states:

```bash
gex-terminal position-model-compare INPUT.json OUTPUT.json \
  --symbol ES --multiplier 50
```

Messages after `as_of` or without event time are rejected. OI is cumulative and
unknown-direction; trade volume is incremental and may preserve aggressor
direction. Each source receives its own snapshot. Sources are never summed, and
dealer inventory and predictive validity stay unmeasured.

Bundled examples live under `gex_terminal/data/provider_fixtures/`:

- `databento_mixed_offline_records.jsonl`
- `price_action_validation_example.json`
- `position_model_comparison_example.json`

## Governed Research And Broader Offline Gates

Versioned profiles, reproducible experiment manifests, append-only corpus
registration, multi-session comparison, model properties, provider-fault
simulation, and generated-chain performance budgets are documented in
[Research Governance](research-governance.md). These commands extend the
software-evidence surface; they do not raise its external evidence ceiling.

Captured-session registration has an additional fail-closed authority gate.
The captured header's policy schema, ID, and SHA-256 must exactly match the
policy supplied to `corpus-register`; research use must be approved, declared
rights and redistribution must match, and redaction must be verified. See
[Capture Governance](capture-governance.md) for the policy contract.

## Still Requires External Evidence

Offline work cannot certify authentication, entitlements, current active-chain
coverage, payload drift, real latency/reconnect behavior, or licensed OI
availability. Predictive promotion additionally requires point-in-time real
history, preregistered decisions, untouched out-of-sample data, and costs.

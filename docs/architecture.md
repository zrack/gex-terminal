# Architecture

`gex-terminal` is organized around one rule: provider-specific data handling,
state ownership, model calculation, terminal rendering, and export/report
workflows stay separated.

## Runtime Components

| Layer | Files | Responsibility |
| --- | --- | --- |
| CLI orchestration | `gex_terminal/cli.py` | Parse command-line options, load config, select runtime mode, start adapters, run exports, and coordinate shutdown. |
| Configuration | `gex_terminal/config.py` | Read the invocation directory's `.env` and environment defaults into a typed `GexConfig`. |
| Provider adapters | `gex_terminal/adapters/`, `gex_terminal/market_data_adapter.py`, `gex_terminal/contracts.py` | Convert live, delayed, provider-shaped, or replay payloads into versioned normalized messages with contract identity and timing semantics. |
| State consumer | `gex_terminal/consumer.py` | Own spot, provider-scoped contract positions, projections, expiry selection, lifecycle, and feed-quality state behind an async lock. |
| GEX model | `gex_terminal/engine.py`, `gex_terminal/regime.py`, `gex_terminal/model_evidence.py` | Price Black-Scholes/Black-76 contract rows, aggregate dollar GEX, derive structural levels, and export bounded numerical evidence. |
| Terminal UI | `gex_terminal/tui.py`, `gex_terminal/gex_terminal.tcss` | Render metrics, matrix rows, first-run guidance, replay browser, model-assumption controls, feed quality, event log, and exports. |
| Offline labs | `gex_terminal/replay_lab.py`, `gex_terminal/demo_lab.py`, `gex_terminal/provider_fixture_lab.py` | Produce replay, demo, and provider-fixture reports without live credentials. |
| Research/export tools | `gex_terminal/snapshot_formats.py`, `gex_terminal/overlays.py`, `gex_terminal/sensitivity.py`, `gex_terminal/research_journal.py`, `gex_terminal/session_store.py`, `gex_terminal/session_capture.py` | Save snapshots, overlays, model-sensitivity reports, journal entries, historical records, and integrity-checked normalized sessions. |
| Packaged data | `gex_terminal/data/`, `gex_terminal/package_data.py` | Resolve bundled replay and sanitized provider resources independently of the current working directory. |

## Data Contract

Adapters emit normalized JSON messages into `StatefulGexConsumer`.

Underlying tick:

```json
{
  "schema_version": 2,
  "type": "underlying_tick",
  "provider": "example",
  "symbol": "ES",
  "price": 5968.25,
  "event_time": "2026-08-04T17:30:00Z"
}
```

Option-volume tick:

```json
{
  "schema_version": 2,
  "type": "options_volume_tick",
  "provider": "example",
  "contract_id": "example-es-option-123",
  "symbol": "ES",
  "strike": 5975,
  "option_type": "C",
  "volume": 1200,
  "iv": 0.14,
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

Schema v2 keeps mutable state under `(provider, contract_id, position_source)`.
Incremental values accumulate; cumulative values replace the previous absolute
quantity. When trade volume and open interest describe the same provider
contract, the consumer chooses one source rather than adding them. All
schema-v2 options require explicit `iv` and `iv_source`; configured defaults
degrade feed quality instead of being presented as native provider IV. Futures
options map to Black-76 and equity/index options to Black-Scholes. Contract rows
use their own DTE and multiplier before equal strikes are aggregated. An
authoritative timezone-bearing expiry timestamp takes precedence over explicit
contract DTE, followed by the configured scalar fallback.
Optional schema-v2 aggressor direction accumulates as buy, sell, or unknown
volume inside the same selected contract state. The engine computes a parallel
directionalized matrix from those buckets while the default call/put matrix
remains unchanged. Cumulative quantities clear directional attribution because
they cannot reconstruct the side composition of prior trades.

Schema v1 remains accepted for the historical strike-level replay path. The
consumer ignores off-symbol underlying ticks, tracks malformed or dropped
messages, excludes authoritatively expired contracts, and filters `all`, `0dte`,
or an exact expiry. A mixed v1/v2 session reports a legacy fallback calculation.

## First-Run Flow

The default first-run path is designed to be useful without credentials.

```text
gex-terminal --demo
        |
        v
seeded demo state -> terminal renders immediately
        |
        v
press p
        |
        v
TUI opens replay browser -> Up/Down choose session -> Enter loads JSONL
        |
        v
press x/d/m/i to adjust expiry/model controls, press e to export, or use CLI reports
```

In demo mode, the in-terminal replay browser starts with `zero-gamma-flip`
because that session shows a clear regime transition. The selector uses the
same normalized message contract as the replay adapter, so UI polish remains
covered by the same consumer and engine path as offline regression tests.

The selector is intentionally limited to demo and replay mode. Live provider
tasks may be running in the background, so live mode keeps replay loading out of
the active session.

## Live Provider Flow

```text
gex-terminal --mode live --provider tradovate --symbol ES
        |
        v
CLI validates mode/provider/config
        |
        v
adapter streams provider payloads
        |
        v
adapter normalizes frames and records provider diagnostics
        |
        v
consumer updates state and feed-quality counters
        |
        v
engine computes snapshots on refresh
        |
        v
TUI displays structure, lifecycle state, and feed health
```

Live adapters should never write credentials to logs, snapshots, fixtures, or
reports. Captured provider payloads must be sanitized before they become tests
or documentation examples.

Tradovate is still a scaffold. Its official-protocol implementation waits for
raw-token authorization and subscription acknowledgements, but only the
explicit, redacted `tradovate-certify --ack-live-network` workflow can measure a
credential/environment/run window. Fixture success cannot promote registry
status or establish native-IV availability.

Databento is `live-implemented-uncertified`: one official SDK session combines
definition replay, ES/NQ option trades, and a continuous-futures `mbp-1` quote.
The adapter performs provider joining and Black-76 IV inversion before emitting
schema-v2 messages; the consumer remains the sole owner of mutable contract
state. Only `databento-certify --ack-live-network` can measure one credential,
entitlement set, symbol, and bounded run window.

## Offline Research Flow

Offline tools reuse the same consumer and engine boundaries:

- `--replay PATH` and `--replay-session NAME` stream normalized JSONL.
- `replay-lab` compares bundled replay sessions and alert behavior.
- `demo-lab` packages visuals, snapshots, overlays, replay reports, fixture
  reports, and a manifest.
- `fixture-lab` runs provider-shaped fixtures through adapter mapping and model
  output.
- `journal` saves local replay-session entries and compares level changes.
- `session-store` saves local snapshot records and exports historical summaries.
- `--record-session` writes normalized replay/live events to an integrity-checked
  capture; `--captured-session` verifies and replays them with event-time pacing.
  The TUI disables replay-session switching while capture is active because a
  consumer reset is not a normalized event boundary.
- `--sensitivity` recomputes the same snapshot under alternate assumptions.
- `model-evidence` runs analytical oracles and deterministic checks, with
  predictive market validity left `unmeasured`.
- `databento-replay` routes local JSON/JSONL/DBN records through the live record
  handler after temporal-integrity checks; `databento-offline-certify` exercises
  adversarial cases without a live claim.
- `price-action-evaluate` and `position-model-compare` produce descriptive,
  point-in-time research artifacts while leaving predictive validity unmeasured.

Generated output stays local by default under ignored folders such as
`demo_lab/`, `demo_pack/`, `research_journal/`, and `historical_sessions/`.

## State Ownership

`StatefulGexConsumer` is the only layer that should mutate market state. It
owns:

- `current_spot` and `session_open`
- aggregate `chain_state`
- provider-scoped `contract_state` keyed by contract identity and position source
- optional per-expiry `expiry_state`
- lifecycle timestamps
- provider and feed-quality counters
- subscription and entitlement status

Use `reset_state(...)` before loading a new offline session into an existing
terminal app. That clears market data and quality counters behind the same lock
used by live updates.

## Contributor Boundaries

- Add provider protocol code inside `gex_terminal/adapters/`.
- Keep normalized message changes compatible with `StatefulGexConsumer`.
- Keep model changes in `engine.py` or `regime.py`, then add independent numeric
  oracles, deterministic fixture tests, and model-evidence coverage.
- Keep terminal presentation changes in `tui.py` and `gex_terminal.tcss`.
- Keep artifact format changes in the relevant export/report module.
- Update README only for user-facing workflows; put implementation detail in
  docs like this one.

## Verification Map

| Change area | Suggested tests |
| --- | --- |
| Consumer lifecycle or feed quality | `tests/test_gex_consumer.py`, `tests/test_feed_quality.py` |
| Model math or structural levels | `tests/test_gex_engine.py`, `tests/test_engine_structure.py`, `tests/test_regime.py` |
| TUI table or first-run behavior | `tests/test_tui_table.py`, `tests/test_tui_first_run.py`, `tests/test_demo_lab.py` |
| Replay/lab/report behavior | `tests/test_replay_lab.py`, `tests/test_demo_lab.py`, `tests/test_research_journal.py`, `tests/test_session_store.py` |
| Capture integrity or event clocks | `tests/test_session_capture.py`, `tests/test_replay_adapter.py` |
| Provider mapping | `tests/test_provider_injector.py`, `tests/test_provider_fixture_lab.py`, provider-specific adapter tests |
| Snapshot/overlay exports | `tests/test_snapshot_formats.py`, `tests/test_overlays.py` |
| Model evidence or sensitivity parity | `tests/test_model_evidence.py`, `tests/test_sensitivity.py` |
| Wheel resources and release metadata | `tests/test_release_contract.py`, CI installed-wheel smoke workflow |

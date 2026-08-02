# Architecture

`gex-terminal` is organized around one rule: provider-specific data handling,
state ownership, model calculation, terminal rendering, and export/report
workflows stay separated.

## Runtime Components

| Layer | Files | Responsibility |
| --- | --- | --- |
| CLI orchestration | `gex_terminal/cli.py` | Parse command-line options, load config, select runtime mode, start adapters, run exports, and coordinate shutdown. |
| Configuration | `gex_terminal/config.py` | Read `.env` and environment defaults into a typed `GexConfig`. |
| Provider adapters | `gex_terminal/adapters/`, `gex_terminal/market_data_adapter.py` | Convert live, delayed, provider-shaped, or replay payloads into normalized messages. |
| State consumer | `gex_terminal/consumer.py` | Own spot, chain, expiry, lifecycle, and feed-quality state behind an async lock. |
| GEX model | `gex_terminal/engine.py`, `gex_terminal/regime.py` | Compute gamma, dollar GEX, walls, zero-gamma, concentration, and regime state. |
| Terminal UI | `gex_terminal/tui.py`, `gex_terminal/gex_terminal.tcss` | Render metrics, matrix rows, first-run guidance, replay browser, model-assumption controls, feed quality, event log, and exports. |
| Offline labs | `gex_terminal/replay_lab.py`, `gex_terminal/demo_lab.py`, `gex_terminal/provider_fixture_lab.py` | Produce replay, demo, and provider-fixture reports without live credentials. |
| Research/export tools | `gex_terminal/snapshot_formats.py`, `gex_terminal/overlays.py`, `gex_terminal/sensitivity.py`, `gex_terminal/research_journal.py`, `gex_terminal/session_store.py` | Save snapshots, overlays, model-sensitivity reports, journal entries, and historical session records. |

## Data Contract

Adapters emit normalized JSON messages into `StatefulGexConsumer`.

Underlying tick:

```json
{
  "type": "underlying_tick",
  "symbol": "ES",
  "price": 5968.25
}
```

Option-volume tick:

```json
{
  "type": "options_volume_tick",
  "strike": 5975,
  "option_type": "C",
  "volume": 1200,
  "iv": 0.14,
  "expiry": "0DTE"
}
```

The consumer ignores off-symbol underlying ticks, tracks malformed or dropped
messages, and keeps per-expiry buckets when `expiry` is present.

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
press d/m/i to adjust assumptions, press e to export, or use CLI reports
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
- `--sensitivity` recomputes the same snapshot under alternate assumptions.

Generated output stays local by default under ignored folders such as
`demo_lab/`, `demo_pack/`, `research_journal/`, and `historical_sessions/`.

## State Ownership

`StatefulGexConsumer` is the only layer that should mutate market state. It
owns:

- `current_spot` and `session_open`
- aggregate `chain_state`
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
- Keep model changes in `engine.py` or `regime.py`, then add deterministic
  fixture tests.
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
| Provider mapping | `tests/test_provider_injector.py`, `tests/test_provider_fixture_lab.py`, provider-specific adapter tests |
| Snapshot/overlay exports | `tests/test_snapshot_formats.py`, `tests/test_overlays.py` |

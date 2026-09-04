# Architecture

`gex-terminal` is organized around one rule: provider-specific data handling,
state ownership, model calculation, terminal rendering, and export/report
workflows stay separated.

## Repository Map

| Path | Architectural role |
| --- | --- |
| `gex_terminal/` | Installable application package and all runtime, model, and report modules |
| `gex_terminal/adapters/` | Provider protocol and replay implementations behind the normalized adapter boundary |
| `gex_terminal/data/` | Packaged synthetic replays and sanitized provider fixtures |
| `tests/` | Contract, model, provider, TUI, report, package, and documentation regression tests |
| `docs/` | Canonical technical, workflow, governance, decision, and packet documentation |
| `assets/` | Derived screenshots, diagrams, and product mockups; never canonical system truth |
| `main.py` | Backward-compatible wrapper around the package CLI |
| `pyproject.toml` | Package identity, dependencies, extras, and console entry point |
| `.env.example` | Provider and runtime configuration template; real credentials stay local |

The documentation ownership map is [docs/README.md](README.md). Release history
is in [CHANGELOG.md](../CHANGELOG.md), and future sequencing is in
[ROADMAP.md](../ROADMAP.md).

## Runtime Components

| Layer | Files | Responsibility |
| --- | --- | --- |
| CLI orchestration | `gex_terminal/cli.py` | Parse command-line options, load config, select runtime mode, start adapters, run exports, and coordinate shutdown. |
| Configuration | `gex_terminal/config.py` | Read the invocation directory's `.env` and environment defaults into a typed `GexConfig`. |
| Provider adapters | `gex_terminal/adapters/`, `gex_terminal/market_data_adapter.py`, `gex_terminal/contracts.py` | Convert live, delayed, provider-shaped, or replay payloads into versioned normalized messages with contract identity and timing semantics. |
| Provider certification | `gex_terminal/tradovate_certification.py`, `gex_terminal/databento_certification.py`, `gex_terminal/databento_certification_policy.py` | Select a versioned target policy before I/O, run acknowledged and bounded live-network gates, and derive redacted exact-run evidence without converting fixture evidence into a live claim. |
| Provider fixture and replay intake | `gex_terminal/provider_injector.py`, `gex_terminal/databento_offline.py` | Route provider-shaped local records through production mapping and adversarial checks without opening a live connection. |
| State consumer | `gex_terminal/consumer.py` | Own spot, provider-scoped contract positions, projections, expiry selection, lifecycle, and feed-quality state behind an async lock. |
| GEX model | `gex_terminal/engine.py`, `gex_terminal/regime.py`, `gex_terminal/model_evidence.py` | Price Black-Scholes/Black-76 contract rows, aggregate dollar GEX, derive structural levels, and export bounded numerical evidence. |
| Evaluation models | `gex_terminal/model_comparison.py`, `gex_terminal/position_model_comparison.py`, `gex_terminal/price_action_validation.py` | Compare separated position models and descriptive later-price paths without promoting predictive validity. |
| Capture and research authority | `gex_terminal/capture_governance.py`, `gex_terminal/session_capture.py`, `gex_terminal/model_profiles.py`, `gex_terminal/experiment_manifest.py`, `gex_terminal/research_corpus.py` | Fail closed on ambiguous live-capture decisions, bind captures to policy identity, validate versioned assumptions, and maintain reproducible experiment and append-only corpus identity. |
| Runtime safety | `gex_terminal/logging_config.py`, `gex_terminal/redaction.py` | Configure warning-level process logging by default and recursively sanitize secrets, sensitive identifiers, and labeled private payload fields before configured log or certification output. |
| Certification gates | `gex_terminal/model_properties.py`, `gex_terminal/provider_fault_lab.py`, `gex_terminal/performance_lab.py` | Exercise numerical properties, provider-shaped fault states, and explicit generated-chain performance budgets. |
| Terminal UI | `gex_terminal/tui.py`, `gex_terminal/gex_terminal.tcss` | Render metrics, matrix rows, first-run guidance, replay browser, model-assumption controls, feed quality, event log, and exports. |
| Offline labs | `gex_terminal/replay_lab.py`, `gex_terminal/demo_lab.py`, `gex_terminal/provider_fixture_lab.py`, `gex_terminal/batch_comparison.py` | Produce replay, demo, provider-fixture, and multi-session model-comparison reports without live credentials. |
| Research/export tools | `gex_terminal/snapshot_formats.py`, `gex_terminal/overlays.py`, `gex_terminal/sensitivity.py`, `gex_terminal/research_journal.py`, `gex_terminal/session_store.py` | Save snapshots, overlays, model-sensitivity reports, journal entries, and historical records from normalized state. |
| Packaged data | `gex_terminal/data/`, `gex_terminal/package_data.py` | Resolve bundled replay and sanitized provider resources independently of the current working directory. |

## Adapter-Consumer Boundary

Adapters emit versioned underlying and option-quantity messages into
`StatefulGexConsumer`. The canonical contract implementation is
`gex_terminal/market_data_adapter.py` plus `gex_terminal/contracts.py`; the
complete documented message shapes and provider extension rules live in
[Market-Data Adapters](adapters.md).

The boundary preserves provider-scoped contract identity, event time, expiry,
quantity semantics, position source, IV provenance, multiplier, and optional
trade-direction provenance. Mutable state is keyed by provider, contract, and
position source. Incremental values accumulate, cumulative values replace, and
open interest is never summed with trade volume. Contract rows are priced before
equal strikes are aggregated.

Schema v1 remains a legacy replay path; schema v2 is the contract-aware path.
Validation, filtering, pricing-model routing, IV provenance, and direction rules
belong to the adapter and model topic guides rather than this component map.

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
CLI acknowledgement/configuration
        |
        v
provider adapter -> normalized messages -> StatefulGexConsumer
        |
        v
engine snapshot -> TUI/report/capture
```

Live adapters should never write credentials to logs, snapshots, fixtures, or
reports. A live capture is a separate authority boundary:

```text
capture policy (rights + retention + redaction + research use)
        |
        v
validated policy identity -> live connection -> captured-session header
        |
        v
matching approved policy + verified redaction -> corpus registration
```

The policy records an operator decision; it neither grants provider rights nor
automatically makes retained observations redistributable. The capture header
stores only policy schema, ID, and SHA-256. Corpus registration of a captured
session additionally requires a matching policy, approved research use,
matching rights/redistribution metadata, and `redaction_status=verified`.

### Databento Certification Boundary

Databento remains `live-uncertified`. Its provider path is deliberately split
into implementation authority and exact-run evidence:

```text
ES/NQ target -> versioned certification policy -> DatabentoAdapter
        |
        v
required requests + optional statistics request -> provider records
        |
        v
consumer state + adapter diagnostics -> redacted certification report
```

The three required requests are `definition`, `mbp-1`, and `trades`; the
`statistics` open-interest request is optional. The SDK's returned integers are
local request IDs. They show that a request returned without a synchronous
exception; they are not provider acknowledgements. Actual records, distinct
chain coverage, and explicit errors supply the observation evidence.

The adapter requests the SDK reconnect policy and registers a reconnect
callback. Diagnostics count callback boundaries and the first frame observed
after each boundary. A post-callback frame is useful resumption evidence, but it
does not acknowledge each schema or prove provider-side resubscription. No
reconnect event is required to pass a window that did not disconnect.

Trade records carry venue sequence values even though `trades` is only a subset
of the venue event stream. Nonconsecutive values and duplicates are therefore
reported descriptively. The certification integrity gate uses the provider's
maybe-bad-book flag and observed out-of-order records; it does not reinterpret
every numeric discontinuity as feed loss.

Shutdown is bounded around the pinned SDK's nonblocking `stop()` contract and
its awaitable `wait_for_close()`. Awaitable stop implementations are also
bounded. Closure must complete within the time limit for `clean_stop=true`; a
timeout triggers the termination fallback and records a stop error. The outer
certification task also has a bounded cancellation grace period.

Tradovate is still a scaffold. Its official-protocol implementation waits for
raw-token authorization and subscription acknowledgements, but only the
explicit, redacted `tradovate-certify --ack-live-network` workflow can measure a
credential/environment/run window. Fixture success cannot promote registry
status or establish native-IV availability.

Only `databento-certify --ack-live-network` can measure one credential,
entitlement set, symbol, and bounded run window. The ES and NQ policies are
separate and enforce their canonical multipliers. Their thresholds are
repository-owned fail-closed choices, not an empirical definition of sufficient
market coverage. Open interest is separately reported as observed, unavailable,
unsupported, entitlement-denied, or not requested; it is never replaced by or
summed with trade volume. Detailed mapping and policy values live in
[Databento Fixture Mapping](databento-fixtures.md).

## Offline Research Flow

Offline tools reuse the same adapter, consumer, and engine boundaries through
five paths:

- **Normalized replay and capture:** packaged/local normalized events and
  integrity-checked captures enter through replay adapters and event-time
  controls. A capture cannot switch replay streams mid-file. Live capture
  additionally passes the capture-policy gate before provider startup.
  Consumer acceptance determines analytical timeline membership; rejected input
  remains only in counters/raw-input audit. Snapshot as-of follows accepted
  state, not the final raw record's timestamp.
- **Provider-shaped intake:** provider injection, fixture labs, and offline
  Databento certification reuse production mapping without opening a live
  connection or promoting readiness.
- **Model evaluation:** sensitivity, numerical evidence, position-model
  comparison, and descriptive later-price evaluation derive bounded artifacts
  from the selected source state.
- **Governed research:** model profiles, experiment manifests, append-only
  corpus registration, and batch comparison bind source identity, assumptions,
  splits, outcomes, costs, and semantic results.
- **Presentation and local storage:** replay/demo labs, journals, session stores,
  snapshots, and overlays present or retain derived state without becoming the
  canonical input authority.

The [documentation map](README.md) routes each workflow to its command and
artifact reference.

Bundled replay catalog entries own instrument identity (symbol and fallback
multiplier); a shared configuration resolver carries it into each offline
workflow. The legacy seeded demonstration is ES-only. Consumer calculations
attach selected-row multiplier provenance to snapshots, keeping effective
inputs distinct from the compatibility fallback field; see
[Export Formats](exports.md#snapshot-json) for the additive snapshot contract.

Generated output stays local by default under ignored folders such as
`demo_lab/`, `demo_pack/`, `research_journal/`, and `historical_sessions/`.

![Offline research authority and evidence flow](../assets/offline-research-architecture.svg)

Provider readiness is not runtime connection status. The readiness vocabulary
is `offline-certified`, `delayed`, `scaffold`, `live-uncertified`, and
`live-certified`. Runtime state includes `SIM`, `REPLAY`, `CONNECTED`, `LIVE`,
`STALE`, and `DISCONNECTED`; a live connection never promotes readiness by itself.
Provider-shaped injection is `REPLAY` with a disconnected transport and explicit
offline/no-network origin. Scripted fault tests may model live transitions, but
remain marked as simulations. Frozen `GexConfig` validates numeric values at
construction/replacement; UI updates validate before publishing state changes.

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

The CLI gives the terminal ownership of its active replay writer task. Replay
replacement is serialized and cancels/awaits that writer before calling
`reset_state(...)`; only after adapter cleanup may new input enter. A failed
writer blocks replacement and remains visible at CLI shutdown. Reset clears
market data and quality counters behind the same lock used by updates. Capture
and live-source sessions cannot switch replay.

## Contributor Boundaries

- Add provider protocol code inside `gex_terminal/adapters/`.
- Keep provider live-gate logic in the certification modules and provider-shaped
  offline intake in the injector/offline modules.
- Keep certification target identity and thresholds in the versioned policy
  module; do not hide threshold changes in a report formatter or adapter.
- Use the central logging and redaction modules for process output. Keep
  capture/corpus authority in the governance modules rather than inferring it
  from provider readiness or file integrity.
- Keep normalized message changes compatible with `StatefulGexConsumer`, the
  sole owner of mutable market state.
- Put pricing and structural-level changes in `engine.py` or `regime.py`;
  comparison, evaluation, IV, or profile changes belong in their focused model
  modules. Add independent oracles, deterministic fixtures, and the applicable
  evidence coverage.
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
| Capture integrity, policy, or event clocks | `tests/test_session_capture.py`, `tests/test_capture_governance.py`, `tests/test_replay_adapter.py` |
| Provider mapping | `tests/test_provider_injector.py`, `tests/test_provider_fixture_lab.py`, provider-specific adapter tests |
| Provider certification, policy, lifecycle, or readiness | `tests/test_tradovate_certification.py`, `tests/test_databento_certification.py`, `tests/test_databento_certification_policy.py`, `tests/test_databento_live.py`, `tests/test_provider_readiness.py` |
| Offline Databento or outcome evaluation | `tests/test_databento_offline.py`, `tests/test_position_model_comparison.py`, `tests/test_price_action_validation.py` |
| Snapshot/overlay exports | `tests/test_snapshot_formats.py`, `tests/test_overlays.py` |
| Model evidence or sensitivity parity | `tests/test_model_evidence.py`, `tests/test_sensitivity.py` |
| Experiment/corpus contracts | `tests/test_model_profiles.py`, `tests/test_experiment_manifest.py`, `tests/test_research_corpus.py` |
| Logging and recursive redaction | `tests/test_safety_controls.py` |
| Batch/property/fault/performance gates | `tests/test_batch_comparison.py`, `tests/test_offline_certification_extensions.py` |
| Wheel resources and release metadata | `tests/test_release_contract.py`, CI installed-wheel smoke workflow |

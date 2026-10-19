# Architecture

`gex-terminal` has two user-facing components: **Terminal**, a Textual dashboard
for replay and research workflows, and **Market Wind Tunnel**, a browser
workbench for exploring bundled scenarios, frozen Terminal checkpoints, or
checkpoints selected from a verified local captured session.
They use one installed Python package and the same calculation code. Standalone
and Both launches run separate processes with separate state. Terminal's explicit
`w` handoff instead owns an additional loopback service inside its process,
serving a detached immutable checkpoint. The optional starter opens either
component or manages both together.

Provider-specific data handling, state ownership, model calculation,
presentation, and export/report workflows stay separated. Starting both
interfaces does not synchronize their source, replay checkpoint, model controls
or scenario selections. An explicit handoff copies one demo/replay checkpoint;
it never synchronizes the mutable consumer with the browser.

This document owns the current architecture, including the C4 views below.
The diagrams describe shipped source; roadmap items and product concepts are
not deployed components. The [visual asset guide](../assets/README.md) records
the source and purpose of the derived SVGs.

## C4 Views

### System Context

The researcher operates one local workbench through two interfaces. Terminal
provides a replay dashboard and access to research workflows; Market Wind Tunnel
provides scenario controls, exposure plots and saved experiments. Synthetic
replay, calculation, comparison, export, and reproduction require no provider
connection. Optional provider connections belong to separately configured
terminal/CLI paths; Wind Tunnel accepts bundled sources, a validated frozen
Terminal demo/replay artifact, or bytes from a browser-selected complete capture.
Guided intake verifies the capture in memory and freezes a chosen event prefix;
it never opens a provider connection. Live checkpoint capture remains separately
gated, and capture integrity does not establish authenticity or data rights.
The separate read-only raw collector requires a valid policy and explicit
network acknowledgement. It writes private provider evidence for later review;
it does not feed Terminal state or Wind Tunnel intake.

```mermaid
flowchart LR
    researcher["Researcher / study participant"]
    subgraph workbench["gex-terminal — local research workbench"]
        terminal["Terminal<br/>Replay dashboard and research workflows"]
        wind["Market Wind Tunnel<br/>Browser scenario workbench"]
        raw["Read-only Tradovate collector<br/>Explicit CLI observation"]
    end
    providers["External market-data providers<br/>Optional configured connection"]
    capture[("Local complete captured session<br/>Operator-authorized offline input")]
    evidence[("Private raw provider evidence<br/>Review before sharing or mapping")]
    researcher <-->|Keyboard controls, metrics and exports| terminal
    researcher <-->|Scenario controls, plots and receipts| wind
    terminal -.->|Explicit immutable checkpoint handoff| wind
    researcher -->|Select local file and review verified checkpoint| capture
    capture -->|Selected bytes; no server file path| wind
    providers -.->|Separately configured terminal / CLI intake| terminal
    researcher -->|Policy and explicit network acknowledgement| raw
    providers -.->|Allowlisted contract responses and market data| raw
    raw -->|Bounded private files; no automatic fixture promotion| evidence
```

Provider availability, credentials, rights, and readiness are documented in
[Market-Data Adapters](adapters.md). The study build uses the offline path in
[Study Build](study-build.md); participant observations remain separate from
software verification.

### Containers And Local Storage

The standalone/Both layout below shows separate local runtime containers. Terminal runs
in a Python process with its Textual UI, intake task, consumer and engine.
Market Wind Tunnel consists of browser code and a separate Python service with
an aiohttp listener bound to `127.0.0.1`. Its checkpoint consumers and scenario
calculations live in that service process, not in Terminal. Research CLI
commands select their own workflow in a separate invocation of the same package.

In Both mode, the setup helper remains a parent process supervising the two
application children. The browser is an independently managed application;
the starter requests that it open the local launch URL. Installed resources and
research files are storage boundaries, not running services. There is no hosted
API, external chart service or database in this architecture. Guided intake sends
the browser-selected capture bytes to the local service; it does not expose the
filesystem to the browser or copy raw captures into the receipt workspace.

```mermaid
flowchart LR
    researcher["Researcher"]
    providers["External providers"]
    subgraph local["Researcher's machine"]
        starter["Optional starter<br/>Python parent in Both mode"]
        terminal["Terminal / research CLI process<br/>Python; own consumer and engine instances"]
        browser["Market Wind Tunnel browser<br/>HTML / JavaScript / bundled Plotly"]
        wind["Wind Tunnel service process<br/>Python / aiohttp; own checkpoint calculations"]
        package[("One installed package<br/>Shared code definitions, inputs and web assets")]
        files[("Terminal / CLI research files<br/>Inputs, packs, journals and exports")]
        capture[("Selected complete capture<br/>Existing local input file")]
        receipts[("Wind Tunnel receipts<br/>Separate wind-tunnel research subfolder")]
        raw[("Private raw Tradovate evidence<br/>Separate operator-owned directory")]
    end
    researcher -->|Choose Terminal, Wind Tunnel or Both| starter
    researcher -->|Terminal commands and keyboard| terminal
    researcher -->|Scenario controls and plots| browser
    starter -.->|Start and supervise owned child| terminal
    starter -.->|Start and supervise owned child| wind
    browser <-->|Capability-protected loopback HTTP| wind
    capture -->|File chooser reads selected bytes| browser
    browser -->|Bounded capture bytes; no input path| wind
    package -->|Load code and resources| terminal
    package -->|Load code, synthetic input and web assets| wind
    files -->|Replay, verify or reproduce input| terminal
    terminal -->|Write artifacts on request| files
    wind <-->|Save, reopen and reproduce receipts| receipts
    providers -.->|Optional configured live or delayed path| terminal
    terminal -->|Explicit raw-collector invocation only| raw
```

The repeated consumer and engine instances use the same installed code; there
is no shared mutable market state. Terminal's explicit handoff is a separate
layout: its owned loopback listener runs inside the Terminal process and serves
a validated copy from `capture_wind_tunnel_state`, not the live consumer.
`TerminalHandoff` retains every owned runner until cleanup completes, replaces
its previous service on a new handoff and stops on Terminal unmount. Existing
standalone/Both services are independent. Checkpoint files and per-checkpoint
receipt workspaces live under `wind_tunnel_handoffs/`; scenario requests embed
the copied input for reproduction without the original file or service.
Configuration for terminal/CLI workflows is loaded locally by `config.py`;
provider secrets remain outside the package and research artifacts. Installation
uses Python package dependencies, while running the frozen replay study and
Wind Tunnel needs no data-provider I/O. The package/resource boundary is verified
from a wheel outside the checkout.

`tradovate-capture` is a separate CLI invocation of the same installed package,
represented by the Terminal / research CLI process above. Its direct HTTP and
WebSocket workflow bypasses the normalized consumer and engine and writes only
its new private evidence directory. It cannot load raw evidence into Wind Tunnel
or register it as a normalized captured session. Authentication and market-data
permissions remain external prerequisites.

The optional setup helper, `scripts/install_app.py`, installs an explicitly
supplied wheel into an owned application folder. It verifies a fresh environment
before changing the active launch target and keeps research in a separate
directory. `scripts/build_app_bundle.py` prepares a local handoff containing that
helper, the wheel and an optional dependency wheelhouse. The builder is a setup
tool; the installed helper also supplies the starter and Both supervisor. Neither
is a hosted service or package registry. The generated offline launcher
initializes configuration in an empty working directory with provider settings
excluded, then writes requested exports in the selected research directory.
Direct `gex-terminal` invocations retain their existing configuration behavior.

Fresh Wind Tunnel-capable setup folders offer Terminal, Wind Tunnel or Both
through the starter. Both starts its background Wind Tunnel child first, waits
for the service's launch URL, requests a browser window, then starts its
foreground terminal child. Server output stays off the terminal UI. Quitting
Terminal stops only that combined session's Wind Tunnel service; an interruption
or service failure settles both owned children. It does not stop another launch
or close the user's browser. Closing a browser tab alone does not stop the
service. A startup failure cancels Both before Terminal opens. Separate launches
remain independent. Existing installer receipts retain their original launcher
bytes; the setup manifest identifies the installer commit separately when it
reuses a wheel from another source commit.

The Wind Tunnel reconstructs a declared bundled replay checkpoint in a fresh
consumer or validates an embedded frozen Terminal artifact for each calculation
request. It copies checkpoint rows, applies
scenario assumptions and prices those copies with the existing engine code.
Guided intake instead verifies selected capture bytes before retaining only
allowlisted normalized calculation fields in an ephemeral `SessionIntake`
registry. A chosen prefix is applied to a fresh consumer, then frozen into the
same opaque checkpoint transport. Its service exposes bundled or frozen source
identifiers, intake handles and bounded operations, never arbitrary input paths.
Only the operator's CLI can supply a checkpoint file path. An origin check and
per-run capability protect the API; the capability stays outside saved research.
Static browser assets are packaged with the wheel, so no external script or
chart service is required.
Receipts bind normalized requests, exact source and calculation identities,
and semantic results. Reproduction recalculates before declaring agreement.

### Application Components

These views expand Terminal, the Wind Tunnel service and the browser client.
The service may run separately or inside Terminal's process under its handoff
owner. Arrows name calls or data flow inside those boundaries, with HTTP as the
browser boundary. Consumer and engine boxes represent separate instances of the
same classes, not a common runtime service. Other research commands reuse those
classes in their own CLI invocation.

**Terminal components**

```mermaid
flowchart TB
    subgraph terminal["Terminal Python process"]
        cli["CLI + validated configuration<br/>cli.py / config.py"]
        intake["Replay / provider adapter<br/>or seeded demo input"]
        consumer["Own StatefulGexConsumer<br/>Market state and replay lifecycle"]
        engine["Own IntradayGexEngine + regime<br/>Contract pricing and structural levels"]
        tui["Textual terminal<br/>tui.py / tui_views.py"]
        exports["Snapshot writer<br/>snapshot.py"]
        frozen["wind_tunnel_checkpoint.py<br/>Validate and freeze copied demo / replay state"]
        handoff["TerminalHandoff<br/>Owned in-process loopback listener"]
        cli -->|Select source| intake
        cli -->|Start UI and transfer replay task ownership| tui
        intake -->|Versioned normalized messages| consumer
        consumer -->|Price selected rows; derive levels| engine
        tui -->|Snapshots and controlled replay replacement| consumer
        tui -->|Load replay after prior writer settles| intake
        tui -->|Export on request| exports
        tui -->|Explicit w action| frozen
        consumer -->|Copy under state lock| frozen
        frozen -->|Immutable artifact; no mutable state link| handoff
        tui -->|Own lifecycle and await cleanup| handoff
    end
    browser["Wind Tunnel browser<br/>Own scenario controls and results"]
    handoff <-->|Capability-protected loopback HTTP| browser
```

**Market Wind Tunnel browser and service components**

```mermaid
flowchart TB
    subgraph browser["Market Wind Tunnel browser"]
        web["wind_tunnel_web/app.js + Plotly<br/>Own controls, selected checkpoint and rendered results"]
    end
    capture[("Browser-selected local capture")]
    handoff["TerminalHandoff<br/>Alternative listener owner inside Terminal"]
    subgraph service["Wind Tunnel service runtime<br/>Separate process or Terminal-owned listener"]
        windcli["wind_tunnel_cli.py<br/>Start server and coordinate shutdown"]
        server["wind_tunnel_server.py<br/>HTTP routes, capability and request bounds"]
        intake["SessionIntake + capture verifier<br/>Bounded bytes; allowlisted ephemeral registry"]
        core["wind_tunnel.py<br/>Scenarios, surfaces and sampled searches"]
        checkpoint["Fresh StatefulGexConsumer<br/>Reconstruct bundled or selected capture prefix"]
        frozen["wind_tunnel_checkpoint.py<br/>Validated opaque immutable checkpoint"]
        pricing["Request-local IntradayGexEngine<br/>Price copied baseline / scenario rows"]
        receipts["Receipt identity and ReceiptStore<br/>Save, load and reproduce"]
        windcli -->|Standalone / Both startup| server
        server -->|Validated operation request| core
        server -->|Inspect selected bytes; retain safe fields only| intake
        intake -->|Chosen verified event prefix| checkpoint
        checkpoint -->|Freeze chosen capture state| frozen
        frozen -->|Portable source for each scenario request| core
        core -->|Apply source cutoff and replay messages| checkpoint
        checkpoint -->|Copied checkpoint rows| core
        core -->|Reprice explicit assumptions| pricing
        server -->|Requested receipt operation| receipts
        receipts -->|Recalculate and bind exact result identity| core
    end
    handoff -->|Start and own cleanup of local listener| server
    web <-->|Loopback HTTP: requests and JSON results| server
    capture -->|File chooser reads bytes| web
    server -->|Opaque checkpoint after prefix validation| web
```

The terminal's seeded demo writes synthetic messages directly through its
consumer rather than opening an adapter. Capture optionally wraps intake with
`RecordingConsumerProxy`; live capture first requires its approved policy
identity. The component view omits individual command helpers; the inventory
below identifies their source modules. Offline labs and governed research
commands select intake, consumers, models and artifact writers as needed;
profiles, experiment manifests and corpus rules bind their research identity.
Corpus verification and some report commands inspect files without running the
model, and are not additional writers of market state. Wind Tunnel's browser
holds interface state; its service recalculates from each declared request
instead of reading the Terminal consumer or following its replay writer.

The Wind Tunnel service component view applies to both launch layouts. A
standalone/Both service starts through `wind_tunnel_cli.py`; Terminal's `w`
action starts the same server through `TerminalHandoff` inside its own process.
The listener's owner, rather than the browser tab, coordinates shutdown.

**Read-only raw collector components**

```mermaid
flowchart LR
    operator["Operator<br/>Local credentials and capture policy"]
    provider["Tradovate<br/>Auth, contract library and market data"]
    subgraph process["Explicit tradovate-capture CLI process"]
        preflight["CLI + capture governance<br/>Validate acknowledgement, policy, bounds and new output"]
        collector["tradovate_capture.py<br/>Allowlisted requests and bounded socket observation"]
        writer["Private evidence writer<br/>Exclude auth; account for safety omissions"]
        manifest["Run manifest<br/>Policy identity, outcome, limits and file hashes"]
        preflight -->|Start only after refusal gates pass| collector
        collector -->|Eligible responses and ordered market events| writer
        collector -->|Owned lifecycle and bounded cleanup outcome| manifest
        writer -->|Retained-file identities and omission accounting| manifest
    end
    private[("New owner-only directory<br/>REST JSONL, WebSocket JSONL and manifest")]
    operator --> preflight
    collector <-->|Read-only contract and market-data protocol| provider
    writer --> private
    manifest --> private
```

The collector has no consumer, pricing, corpus, browser or automatic fixture
writer. Its private files preserve eligible provider shape before normalization;
their hashes establish local consistency, not authenticity or sharing rights.
HTTP redirects are disabled; WebSocket application messages, including the
authorization token, require the final secure provider endpoint to pass an exact
host/port/path and no-user-information check. The SDK may perform unauthenticated
redirect handshakes before that check. Owned heartbeat/receive failures are
retrieved together during cleanup rather than becoming raw orphan-task logs.
The operator must review permitted derivatives and validate actual ES/NQ mappings
before issue #4 can close. The component boundary and file/limit contract are
owned by [Tradovate Raw-Payload Capture](tradovate-capture.md).

Guided intake is limited to complete captures no larger than 4 MiB and 5,000
events, with at most four intakes retained in memory and 200 sampled checkpoint
choices. Raw bytes are verified before private labels, paths and extension
fields are discarded; retained contract labels become stable opaque IDs. A
chosen event includes only its prefix, and the production consumer determines
the accepted market-state cutoff. The browser discards its intake after opening
or cancelling it, and service cleanup clears the registry. Saving a scenario
persists its allowlisted frozen source in a receipt; it does not persist the
raw capture. These bounds and privacy rules are recorded in
[ADR-003](decisions/ADR-003-guided-session-intake.md).

## Repository Map

| Path | Architectural role |
| --- | --- |
| `gex_terminal/` | Installable application package and all runtime, model, and report modules |
| `gex_terminal/adapters/` | Provider protocol and replay implementations behind the normalized adapter boundary |
| `gex_terminal/data/` | Packaged synthetic replays and provider-shaped fixtures |
| `gex_terminal/wind_tunnel_web/` | Packaged browser UI, Plotly, icons and static assets served by the local Wind Tunnel service |
| `scripts/install_app.py`, `scripts/build_app_bundle.py` | Reviewed-wheel setup, generated launchers, optional Both supervisor and bundle preparation |
| `scripts/build_study_kit.py`, `scripts/build_participant_delivery.py`, `scripts/build_study_consent.py` | Maintainer preparation of frozen synthetic study kits, bounded participant-only delivery and optional blank consent rendering; no participant collection |
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
| Offline preflight | `gex_terminal/doctor.py` | Inspect local package/configuration/resources and temporary storage without a live adapter or optional SDK import; report safe structural diagnostics. |
| Local support and recovery | `gex_terminal/local_support.py`, `gex_terminal/artifact_lifecycle.py` | Separate redacted support evidence from owner-only private backups; verify whole recognized research groups and require a backup-bound, separately confirmed retention plan. |
| Provider adapters | `gex_terminal/adapters/`, `gex_terminal/market_data_adapter.py`, `gex_terminal/contracts.py` | Convert live, delayed, provider-shaped, or replay payloads into versioned normalized messages; preserve product versus underlying identity, validated units, publication time and optional OI reference/action provenance. |
| Provider certification | `gex_terminal/tradovate_certification.py`, `gex_terminal/databento_certification.py`, `gex_terminal/databento_certification_policy.py` | Select a versioned target policy before I/O, run acknowledged and bounded live-network gates, and derive redacted exact-run evidence without converting fixture evidence into a live claim. |
| Private raw provider evidence | `gex_terminal/tradovate_capture.py` | Require an explicit network acknowledgement and valid capture policy, constrain read-only contract/market-data operations, preserve eligible pre-normalization evidence with omissions and hashes, and own bounded private-file/network cleanup. |
| Provider fixture and replay intake | `gex_terminal/provider_injector.py`, `gex_terminal/databento_offline.py` | Route provider-shaped local records through production mapping and adversarial checks without opening a live connection. |
| State consumer | `gex_terminal/consumer.py` | Own spot, provider-scoped contract positions, projections, expiry selection, lifecycle, and feed-quality state behind an async lock; order referenced OI by trading date then publication revision and retain deletion tombstones. |
| GEX model | `gex_terminal/engine.py`, `gex_terminal/american_futures.py`, `gex_terminal/regime.py`, `gex_terminal/model_evidence.py` | Price Black-Scholes/Black-76 or American futures contract rows, report unavailable pricing coverage, aggregate dollar GEX, derive structural levels, and export bounded numerical evidence. |
| Evaluation models | `gex_terminal/model_comparison.py`, `gex_terminal/position_model_comparison.py`, `gex_terminal/price_action_validation.py` | Compare separated position models and descriptive later-price paths without promoting predictive validity. |
| Capture and research authority | `gex_terminal/capture_governance.py`, `gex_terminal/session_capture.py`, `gex_terminal/model_profiles.py`, `gex_terminal/experiment_manifest.py`, `gex_terminal/research_corpus.py` | Fail closed on ambiguous live-capture decisions, bind captures to policy identity, validate versioned assumptions, and maintain reproducible experiment and append-only corpus identity. |
| Runtime safety | `gex_terminal/logging_config.py`, `gex_terminal/redaction.py` | Configure warning-level process logging by default and recursively sanitize secrets, sensitive identifiers, and labeled private payload fields before configured log or certification output. |
| Certification gates | `gex_terminal/model_properties.py`, `gex_terminal/provider_fault_lab.py`, `gex_terminal/performance_lab.py` | Exercise numerical properties, provider-shaped fault states, and explicit generated-chain performance budgets. |
| Terminal UI | `gex_terminal/tui.py`, `gex_terminal/tui_views.py`, `gex_terminal/gex_terminal.tcss` | Render metrics, matrix rows and responsive layout; present focused replay/help views, model controls, source and quality context, event history and exports. |
| Wind Tunnel calculations | `gex_terminal/wind_tunnel.py` | Reconstruct a bundled replay cutoff or validate a frozen Terminal artifact, copy checkpoint rows, and use engine code for comparisons, surfaces and bounded searches. |
| Terminal checkpoint transport and lifecycle | `gex_terminal/wind_tunnel_checkpoint.py`, `gex_terminal/wind_tunnel_handoff.py` | Validate allowlisted offline state, preserve no-overwrite local inputs, embed portable source data and own loopback service cleanup. The consumer remains the sole mutable market-state owner. |
| Guided captured-session intake | `gex_terminal/session_intake.py`, `gex_terminal/session_capture.py` | Verify bounded selected bytes in memory, discard private extensions, retain a bounded allowlisted registry and freeze a selected prefix through the production consumer. |
| Wind Tunnel service and CLI | `gex_terminal/wind_tunnel_server.py`, `gex_terminal/wind_tunnel_cli.py` | Serve packaged assets and bounded loopback API operations, protect requests with a per-run capability, and save/verify/reproduce receipts. CLI example and reproduction commands also run without the browser server. |
| Wind Tunnel browser | `gex_terminal/wind_tunnel_web/` | Hold source/checkpoint/scenario selections, request calculations, render Plotly views and expose receipt controls; never read the Terminal's consumer state. |
| Setup and starter | `scripts/install_app.py`, `scripts/build_app_bundle.py` | Prepare and verify an owned wheel installation, keep research separate, generate shortcuts and offer Terminal/Wind Tunnel/Both. Both supervises two application children with readiness checks and owned-process cleanup. |
| Offline labs | `gex_terminal/replay_lab.py`, `gex_terminal/demo_lab.py`, `gex_terminal/provider_fixture_lab.py`, `gex_terminal/batch_comparison.py` | Produce replay, demo, provider-fixture, and multi-session model-comparison reports without live credentials. |
| Portable research receipt | `gex_terminal/demo_lab_receipt.py` | Bind authorized copied replay, model/runtime identity, exact inventory and semantic content; reject unsupported or changed packs before reproduction. |
| Research/export tools | `gex_terminal/snapshot_formats.py`, `gex_terminal/overlays.py`, `gex_terminal/sensitivity.py`, `gex_terminal/research_journal.py`, `gex_terminal/session_store.py` | Save snapshots, overlays, model-sensitivity reports, journal entries, and historical records from normalized state. |
| Packaged data | `gex_terminal/data/`, `gex_terminal/package_data.py` | Resolve bundled replay and provider-shaped resources independently of the current working directory. |

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

Optional OI reference-date and update-action provenance distinguishes a later
publication from a later trading-date observation. The consumer orders such OI
first by reference date, then publication time; deletion retains zero state as a
tombstone so a delayed older observation cannot restore it. Added zero,
withdrawn data and unavailable data remain distinct states. OI revision handling
does not replace the separate positive trade-volume state. Provider units and
sentinel validation belong to the adapter; configured multiplier fallback and
selected-position calculation belong to the consumer/model boundary.

Provider-scoped futures identity is also consumer-owned. The Databento adapter
emits the quote contract ID and each option's underlying link; quote acceptance
advances the current identity. Retained rows for another futures contract are
quarantined from projections, pricing and current certification coverage.
Retired mappings and delayed quote frames cannot restore old exposure within
the same session. A reset clears the identity session together with market
state. Historic raw quantities and deletion tombstones remain inspectable.

Schema v1 remains a legacy replay path; schema v2 is the contract-aware path.
Validation, filtering, pricing-model routing, IV provenance, and direction rules
belong to the adapter and model topic guides rather than this component map.

## First-Run Flow

The default first-run path is designed to be useful without credentials. The
wheel installation, offline doctor and full user journey are owned by
[First Run](first-run.md). A fresh reviewed setup with the unified starter routes
the user to the two components:

```text
Install.command -> verified application environment -> Start GEX.command chooser
        |
        +-> Terminal -> its own replay consumer -> Textual dashboard
        |
        +-> Wind Tunnel -> local Python service -> browser controls and plots
        |
        +-> Both -> supervised Wind Tunnel service becomes ready
                       -> request browser window -> start Terminal child
                       -> Terminal exit stops this session's Wind Tunnel service
```

The setup launcher's Terminal path selects `zero-gamma-flip`; the direct
`gex-terminal --demo` CLI path starts seeded data. Wind Tunnel independently
selects its own bundled source and checkpoint. Its **Open local session** flow
lets the operator select capture bytes, verify integrity, inspect source/time,
quality and model assumptions, choose an event prefix, then open the resulting
frozen checkpoint. Saving and exporting a scenario receipt makes that selected
input reproducible after the original file and service are gone. The detailed
workflow belongs in [Wind Tunnel](wind-tunnel.md).

Both changes launch and shutdown coordination, not either component's source or
model state. Terminal's explicit `w` action opens a separate frozen-checkpoint
service and does not change the independent Both service. Its internal terminal
flow is:

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
press x/d/m/i to adjust expiry/model controls, press e to export,
press w to freeze an eligible checkpoint in Wind Tunnel, or use CLI reports
```

In demo mode, the in-terminal replay browser starts with `zero-gamma-flip`
because that session shows a clear regime transition. The selector uses the
same normalized message contract as the replay adapter, so UI polish remains
covered by the same consumer and engine path as offline regression tests.

Picker navigation has conditional keyboard priority: while the browser is open
on the current dashboard, its Up/Down/Enter actions run before the focused
strike table's bindings. Closing or loading releases those keys to the table;
a pushed screen retains its own bindings even if the browser remains open
behind it. Real Textual key-event regressions must exercise this routing, not
only invoke action methods. User controls belong in [First Run](first-run.md).

The selector is intentionally limited to demo and replay mode. Live provider
tasks may be running in the background, so live mode keeps replay loading out of
the active session. Active capture also blocks replacement; keyboard routing
does not bypass the loading or writer-settlement gates.

At 140×42 and above the compact layout preserves metrics, strike rows, quality
and controls, with scrolling for explanatory cards. Below the declared minimum,
an explicit message replaces the clipped dashboard; resizing restores it
without resetting market state. The large layout exposes the additional sidebar.

The dashboard screen owns its periodic and initial refresh callbacks. Refresh
work captures that owner and checks it again after snapshot and expiry awaits;
quit, teardown or another current screen prevents cache/UI publication. Resize
updates the captured dashboard even behind an overlay. Genuine render errors
on the current mounted dashboard still propagate; replay-writer ownership is
a separate boundary.

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

The raw Tradovate collector uses the same policy-identity gate with a separate
explicit network acknowledgement, then writes a new private evidence directory
without entering this normalized consumer/capture path. It invokes allowlisted
read-only contract requests, including `contract/getoptionschain`, and observes
market-data frames. Authentication payloads, headers and outgoing frames are not
retained. Limits and safety omissions remain part of the run's interpretation.
Raw evidence requires reviewed permitted derivatives and production-path mapping
tests before it can supply actual-payload evidence for issue #4.

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

Databento requests use a declared universe of distinct ES/NQ option-product
parents alongside the selected futures parent and continuous quote. The adapter
normalizes product families to the intended futures underlying while retaining
the definition `underlying_id` guard against another contract month for trades
and OI additions. Before a usable matching future quote, OI additions are counted
and dropped without buffering; deletes can invalidate known OI without that
quote because they create no exposure. Configured
parents and observed families are separate diagnostic evidence; neither a
subscription request nor synthetic family fixtures prove live universe
completeness. Dollar multipliers come only from validated point-value metadata,
not Databento's deliverable-count `contract_multiplier`.

The offline `live_population_contract` module is a preparation boundary around
future recurring observation, not another adapter or runner. It validates a
complete 12-slot ES plan, hashes the registered certification policy and every
normalized plan field, and cross-checks a later hand-authored redacted result
manifest against that frozen population. It has no credential, scheduling,
capture, or network integration. Report digests are declared identities only;
the validator does not read or authenticate report bytes. See
[Live Population Preparation](live-population-prep.md).

The adapter requests the SDK reconnect policy and registers a reconnect
callback. Diagnostics count callback boundaries and the first frame observed
after each boundary. A post-callback frame is useful resumption evidence, but it
does not acknowledge each schema or prove provider-side resubscription. No
reconnect event is required to pass a window that did not disconnect.

Trade records carry venue sequence values even though `trades` is only a subset
of the venue event stream. Nonconsecutive and repeated values are therefore
reported descriptively. Distinct incremental Databento fills may share one
sequence; native fingerprints distinguish them from retransmissions. The
consumer retains a bounded fingerprint group for the current contract sequence,
and guided capture intake preserves the identity before replay. Checkpoints
retain aggregate quantities without this internal cache. See the
[normalized contract](adapters.md#normalized-messages).
The certification integrity gate uses the provider's
maybe-bad-book flag and observed out-of-order records; it does not reinterpret
every numeric discontinuity as feed loss.

Shutdown is bounded around the pinned SDK's nonblocking `stop()` contract and
its awaitable `wait_for_close()`. Awaitable stop implementations are also
bounded. Closure must complete within the time limit for `clean_stop=true`; a
timeout triggers the termination fallback and records a stop error. The outer
certification task also has a bounded cancellation grace period.

Tradovate is still a scaffold. Its official-protocol implementation waits for
raw-token authorization and subscription acknowledgements. Each wait processes
the successful response's full event frame before reporting success: market
data retains wire order, while a matching failed response or an `error`/`md/error`
event prevents success even after an earlier acknowledgement.
Connection/subscription state gates remain owned by the existing lifecycle.
Only the explicit, redacted
`tradovate-certify --ack-live-network` workflow can measure a
credential/environment/run window for the normalized adapter's diagnostic
gates. The separate `tradovate-capture` workflow records raw shape evidence
without running those certification gates. Fixture success cannot promote registry
status or establish native-IV availability.

Its discovery implementation uses `product/find`, maturity and contract
dependencies, and bounded suggestions. Nested quotes join by registered
contract identity to the metadata supplied by that path; cumulative trade
volume and OI remain separate consumer sources. The extra strike, option-side,
IV and expiry aliases accepted by the implementation are not established
ES/NQ provider fields merely because synthetic tests populate them. The
documented `contract/getoptionschain` grouped response is not consumed by this
adapter. [Market-Data Adapters](adapters.md#implemented-mapping-and-evidence-boundaries)
owns the current mapping and evidence limits.

Bounded synthetic chain and scripted lifecycle tests use these same production
adapter boundaries without acquiring credentials or adding another ingestion
owner. They can verify discovery decisions, malformed-input quarantine,
cumulative-state semantics, retry and cancellation paths, and fail-closed
report outcomes. [Issue #4](https://github.com/zrack/gex-terminal/issues/4)
still requires actual sanitized demo or live ES/NQ payloads, field mappings
including IV availability or absence, and entitlement notes. That mapping
requirement is separate from broader real-provider coverage and reconnect
qualification.

Only `databento-certify --ack-live-network` can measure one credential,
entitlement set, symbol, and bounded run window. The ES and NQ policies are
separate and enforce their canonical multipliers. Their thresholds are
repository-owned fail-closed choices, not an empirical definition of sufficient
market coverage. Open interest is separately reported as observed, unavailable,
unsupported, entitlement-denied, or not requested; it is never replaced by or
summed with trade volume. Detailed mapping and policy values live in
[Databento Fixture Mapping](databento-fixtures.md).

## Offline Research Flow

Offline tools reuse the same adapter, consumer, and engine code boundaries
through eight paths, with consumer instances owned by the invoking workflow:

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
- **Terminal checkpoint handoff:** explicit `w` or checkpoint export copies
  eligible demo/replay state under the consumer lock, validates the versioned
  artifact and freezes its exact source time and assumptions. An owned loopback
  service or the checkpoint CLI opens the detached copy without following
  subsequent Terminal updates.
- **Guided captured-session intake:** the browser uploads bounded selected
  bytes for complete-capture verification. The ephemeral allowlisted registry
  exposes source/time, quality, model inputs and event choices. A selected prefix
  enters a fresh production consumer and becomes an opaque checkpoint; neither
  arbitrary server paths nor raw captures enter receipt storage.
- **Wind Tunnel scenarios:** each request reconstructs a bundled synthetic
  checkpoint or validates an embedded frozen artifact, copies its rows and
  applies explicit spot, IV, time and expiry assumptions. Browser comparisons,
  surfaces and sampled searches use those copied inputs; they neither consume
  Terminal's active replay nor fabricate a future market path. Saved receipts
  embed a selected frozen source when needed and retain the normalized request
  and exact source, calculation and result identities for reproduction.
- **Governed research:** model profiles, experiment manifests, append-only
  corpus registration, and batch comparison bind source identity, assumptions,
  splits, outcomes, costs, and semantic results.
- **Presentation and local storage:** replay/demo labs, journals, session stores,
  snapshots, and overlays present or retain derived state without becoming the
  canonical input authority.

The [documentation map](README.md) routes each workflow to its command and
artifact reference.

### Portable identity and local authority

Demo Lab v2 extends the existing pack rather than introducing a second research
format. Its receipt binds the copied authorized synthetic input, catalog
instrument/multiplier, model profile, explicit runtime compatibility and exact
file inventory. Reproduction reads that copied source and compares five decision
artifacts after removing only declared volatile timing fields. Different
instruments are grouped separately; ES/NQ differences are not model deltas.
The [Demo Lab contract](demo-lab.md) owns schema and command details.

Experiment manifests independently bind full specification and profile identity,
input, implementation, evidence policy and semantic result. Legacy v1 verification
is explicitly partial. Corpus verification checks membership and content
integrity, not point-in-time evaluation eligibility; it never promotes a stored
input merely because a hash matches. [Research Governance](research-governance.md)
owns these identity and cutoff contracts. Unkeyed hashes provide internal
consistency, not signatures or independent historical authenticity.

Bundled replay catalog entries own instrument identity (symbol and fallback
multiplier); a shared configuration resolver carries it into each offline
workflow. The legacy seeded demonstration is ES-only. Consumer calculations
attach selected-row multiplier provenance to snapshots, keeping effective
inputs distinct from the compatibility fallback field; see
[Export Formats](exports.md#snapshot-json) for the additive snapshot contract.

Generated output stays local by default under ignored folders such as
`demo_lab/`, `demo_pack/`, `research_journal/`, and `historical_sessions/`.

![Offline research authority and evidence flow](../assets/offline-research-architecture.svg)

This SVG is a derived summary of this section and
[Research Governance](research-governance.md). Experiment/receipt orchestration
owns result identity; the consumer and engine do not create manifests or semantic
digests. Corpus registration is an independently verified registry, not an
automatic prerequisite or selector for every experiment.

Provider readiness is not runtime connection status. The readiness vocabulary
is `offline-certified`, `delayed`, `scaffold`, `live-uncertified`, and
`live-certified`. Runtime state includes `SIM`, `REPLAY`, `CONNECTED`, `LIVE`,
`STALE`, and `DISCONNECTED`; a live connection never promotes readiness by itself.
Provider-shaped injection is `REPLAY` with a disconnected transport and explicit
offline/no-network origin. Scripted fault tests may model live transitions, but
remain marked as simulations. Frozen `GexConfig` validates numeric values at
construction/replacement; UI updates validate before publishing state changes.

## State Ownership

Each `StatefulGexConsumer` instance owns its invocation's mutable market state.
The class defines the state-owner boundary; it is not a global object shared by
Terminal, Wind Tunnel and research commands. An instance owns:

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

Wind Tunnel creates its own consumer when reconstructing a bundled replay prefix
or freezing a guided intake prefix. A request using an embedded frozen artifact
validates that artifact directly. Scenario pricing always uses copied rows,
preserving the source checkpoint. `SessionIntake` owns only its bounded
allowlisted input registry; each fresh consumer owns the reconstructed mutable
market state. Browser control state and calculated responses belong to that
browser view; they do not replace Terminal's consumer, replay task or selected
model. Terminal's handoff owns a listener and detached artifact, not a second
writer to its active consumer. The Both supervisor owns process lifetime only
and provides no shared-memory or replay-synchronization channel.

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
- Keep terminal presentation changes in `tui.py`, `tui_views.py` and `gex_terminal.tcss`.
- Keep Wind Tunnel browser presentation in `wind_tunnel_web/`, request/receipt
  boundaries in `wind_tunnel_server.py`, and synthetic scenario orchestration in
  `wind_tunnel.py`. Reuse engine pricing rather than duplicating it in JavaScript.
- Keep capture-byte verification in `session_capture.py`, ephemeral intake and
  allowlisted prefix projection in `session_intake.py`, and immutable checkpoint
  validation and listener ownership in the checkpoint/handoff modules. Browser
  requests must not introduce arbitrary filesystem paths or raw-capture storage.
- Keep setup, chooser and owned-process supervision in `scripts/install_app.py`;
  do not use the starter to transfer market state between the two interfaces.
- Keep artifact format changes in the relevant export/report module.
- Update README only for user-facing workflows; put implementation detail in
  docs like this one.
- Keep these C4 views, the component inventory, and derived architecture assets
  consistent in the same change whenever a source or ownership boundary changes.
  Record architectural decisions in `docs/decisions/`; record future sequencing
  in the roadmap and completed delivery in the changelog or closed packet.

## Verification Map

| Change area | Suggested tests |
| --- | --- |
| Consumer lifecycle or feed quality | `tests/test_gex_consumer.py`, `tests/test_feed_quality.py` |
| Model math or structural levels | `tests/test_gex_engine.py`, `tests/test_engine_structure.py`, `tests/test_regime.py` |
| TUI table or first-run behavior | `tests/test_tui_table.py`, `tests/test_tui_first_run.py`, `tests/test_demo_lab.py` |
| Wind Tunnel numerical, service or CLI behavior | `tests/test_wind_tunnel.py`, `tests/test_wind_tunnel_server.py`, `tests/test_wind_tunnel_cli.py`; inspect the browser against computed results |
| Immutable Terminal checkpoint and owned handoff | `tests/test_wind_tunnel_checkpoint.py`, `tests/test_wind_tunnel_handoff.py`, `tests/test_wind_tunnel_assets.py`; inspect demo/replay isolation and fresh-service receipt reproduction |
| Guided local capture intake | `tests/test_session_intake.py`, `tests/test_session_intake_server.py`, `tests/test_wind_tunnel_intake_assets.py`; inspect selected-byte upload, source review, chosen prefix, cancellation and portable receipt reproduction |
| Replay/lab/report behavior | `tests/test_replay_lab.py`, `tests/test_demo_lab.py`, `tests/test_research_journal.py`, `tests/test_session_store.py` |
| Capture integrity, policy, or event clocks | `tests/test_session_capture.py`, `tests/test_capture_governance.py`, `tests/test_replay_adapter.py` |
| Provider mapping | `tests/test_provider_injector.py`, `tests/test_provider_fixture_lab.py`, provider-specific adapter tests |
| Tradovate synthetic discovery, quote mapping and parameter boundaries | `tests/test_tradovate_option_chain.py`, `tests/test_tradovate_parameters.py`, `tests/test_tradovate_adapter.py`, `tests/test_tradovate_protocol.py`; constructed metadata does not establish actual ES/NQ fields |
| Tradovate frame, lifecycle and negative certification gates | `tests/test_tradovate_ack_frames.py`, `tests/test_tradovate_lifecycle.py`, `tests/test_tradovate_certification.py`; scripted sessions do not establish service-side reconnect behavior |
| Tradovate raw evidence collection | `tests/test_tradovate_capture.py`, `tests/test_tradovate_capture_cli.py`, `tests/test_tradovate_capture_safety.py`; mocked preservation, private output, omissions, refusal gates, auth/redirect/heartbeat bounds and cleanup do not supply actual ES/NQ payloads |
| Provider certification, policy, lifecycle, or readiness | `tests/test_tradovate_certification.py`, `tests/test_databento_certification.py`, `tests/test_databento_certification_policy.py`, `tests/test_databento_live.py`, `tests/test_provider_readiness.py` |
| Prospective live-population preparation | `tests/test_live_population_contract.py` |
| Offline Databento or outcome evaluation | `tests/test_databento_offline.py`, `tests/test_position_model_comparison.py`, `tests/test_price_action_validation.py` |
| Snapshot/overlay exports | `tests/test_snapshot_formats.py`, `tests/test_overlays.py` |
| Model evidence or sensitivity parity | `tests/test_model_evidence.py`, `tests/test_sensitivity.py` |
| Experiment/corpus contracts | `tests/test_model_profiles.py`, `tests/test_experiment_manifest.py`, `tests/test_research_corpus.py` |
| Logging and recursive redaction | `tests/test_safety_controls.py` |
| Batch/property/fault/performance gates | `tests/test_batch_comparison.py`, `tests/test_offline_certification_extensions.py` |
| Wheel resources and release metadata | `tests/test_release_contract.py`, CI installed-wheel smoke workflow |
| Reviewed-wheel setup and launch handoff | `tests/test_install_app.py`, `tests/test_app_bundle.py`, `tests/test_starter.py`; fresh-folder installation, reuse and managed-child lifecycle checks |
| Maintainer preview automation | `tests/test_refresh_previews.py`; staged synthetic previews and local provenance manifest |
| Retained CI evidence | `tests/test_ci_evidence.py`; bounded synthetic inventory and explicit failed/missing outputs |
| Frozen study kit preparation | `tests/test_study_kit.py`; verify exact source/build identity, synthetic fixture hashes and retained rehearsal evidence without inferring participant outcomes |
| Participant delivery packaging | `tests/test_participant_delivery.py`; exact public/material boundaries, preserved frozen inputs, complete inventories, safe paths, no overwrite and remaining local links; PDF visual/form checks remain separate |
| Documentation paths and heading destinations | `tests/test_release_contract.py` (`DocumentationLinkContractTests`) |

The [offline CI workflow](offline-ci.md) exercises source, installed-wheel and
recovery paths on Linux/macOS and Python 3.11/3.12. Maintainer scripts generate
preview and build-evidence artifacts outside runtime state ownership. These are
verification tools; the C4 application/deployment boundaries are unchanged.

For diagrams, also inspect the rendered Mermaid and SVG layout. A passing link
check cannot establish that an architectural relationship matches source code.

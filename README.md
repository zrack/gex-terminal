# gex-terminal

Intraday Gamma Exposure (GEX) imbalance tracking in a terminal UI.

An asynchronous, high-performance command-line dashboard for tracking real-time
dealer options hedging pressure in index futures such as **ES** and **NQ**. The
terminal uses cumulative intraday session volume as a proxy for changing open
interest, then translates live option-chain activity into strike-level gamma
exposure, imbalance, and structural market zones.

The goal is to isolate hidden institutional support, resistance, and volatility
acceleration boundaries at terminal speed, without the overhead of a browser UI.

![Color replay demo lab preview](assets/gex-terminal-demo-lab.svg)

First-run replay browser:

![Replay browser onboarding preview](assets/gex-terminal-onboarding.svg)

Design target:

![GEX Imbalance Terminal mockup](assets/gex-terminal-mockup.png)

> This project is intended for market research and engineering experimentation.
> It is not financial advice.

## Why This Project Exists

`gex-terminal` is an open-source GEX research terminal for traders and developers
who want a local, explainable workflow instead of a closed market-structure
dashboard. The project is designed around:

- **Open-source model development**: contributors can inspect the assumptions,
  improve the math, and compare results against replayable sessions.
- **Local-first credential handling**: API keys and market-data credentials stay
  in local environment files, not in source code or hosted dashboards.
- **Transparent calculations**: the current model documents its practical
  assumptions, including intraday volume as an open-interest proxy.
- **Provider-agnostic ingestion**: market data flows through adapters so the app
  can grow beyond any single broker or feed.
- **Replayable research datasets**: normalized fixtures make it possible to
  learn, test, and reproduce behavior without paid data access.
- **Fast ES/NQ intraday workflow**: the terminal is built for traders who already
  have data access and want quick structural reads without browser overhead.

That openness is the invitation: contributors can improve the model, add
providers, submit normalized payload fixtures, and build export or visualization
tools without needing to join a closed commercial platform.

## Looking For Contributors

Helpful contributions include provider adapters, normalized market-data fixtures,
math/model improvements, terminal UI experiments, replay datasets, data-quality
checks, and docs that make GEX research easier to understand.

Good starting points:

- Pick an issue labeled `good first issue` or `help wanted`, or start from
  [docs/good-first-issues.md](docs/good-first-issues.md).
- Submit sanitized replay or provider payload fixtures.
- Improve the assumptions documentation around GEX calculations.
- Prototype one of the signature capabilities in the roadmap.
- Help validate provider-specific option-chain payload shapes.

## Project Layout

```text
.
|-- .env.example        # Template for local provider credentials
|-- .gitignore          # Keeps secrets, virtualenvs, and caches out of Git
|-- .github/workflows/  # GitHub Actions smoke-test workflow
|-- .github/ISSUE_TEMPLATE/ # Bug, feature, adapter, and good-first issue templates
|-- CHANGELOG.md        # Notable project changes and public-prep milestones
|-- CODE_OF_CONDUCT.md  # Community participation expectations
|-- LICENSE             # MIT License
|-- CONTRIBUTING.md     # Contribution guidelines and verification notes
|-- README.md           # Project overview and setup notes
|-- ROADMAP.md          # Planned project phases and future work
|-- SECURITY.md         # Credential handling and vulnerability reporting
|-- requirements.txt    # Runtime Python dependencies
|-- pyproject.toml      # Package metadata and console entry point
|-- main.py             # Backward-compatible CLI wrapper
|-- assets/             # Screenshots, mockups, and social preview assets
|-- docs/               # Adapter and contributor-facing technical notes
|-- gex_terminal/       # Application package
|   |-- cli.py          # Console command and orchestration
|   |-- config.py       # Environment-driven runtime configuration
|   |-- engine.py       # Vectorized Black-Scholes and GEX calculation matrix
|   |-- consumer.py     # Stateful asynchronous market-data aggregator
|   |-- demo_lab.py     # Offline demo pack generator for screenshots and reports
|   |-- replay_lab.py   # Offline replay reports, alerts, and session comparisons
|   |-- research_journal.py # Local replay-session journal and comparisons
|   |-- session_store.py # Local historical snapshot records and reports
|   |-- screenshot.py   # Color-aware Textual SVG screenshot exports
|   |-- provider_fixture_lab.py # Offline provider fixture scorecards
|   |-- tui.py          # Textual reactive terminal user interface
|   |-- gex_terminal.tcss # Terminal dashboard theme and layout styles
|   |-- market_data_adapter.py # Shared provider adapter contract
|   `-- adapters/       # Replay, Tradovate, Databento, IBKR, and yfinance adapters
|-- sample_data/        # Normalized replay data for local demos
|-- tests/              # Regression tests and sanitized provider fixtures
```

## Core Features

- **Vectorized mathematical engine**: calculates Black-Scholes Greeks across the
  option chain with NumPy, avoiding slow per-contract Python loops.
- **Thread-safe state architecture**: uses asynchronous queues and guarded state
  updates to ingest high-frequency WebSocket ticks without race conditions.
- **Low-overhead terminal interface**: renders a live matrix in a Textual UI,
  keeping the workflow fast and local.
- **First-run offline workflow**: starts with useful demo state, explains how
  to proceed without credentials, and lets users browse bundled replay sessions
  from inside the terminal with `p`.
- **Terminal assumption controls**: cycle expiry, risk-free rate, and contract
  multiplier from the running terminal to see model sensitivity immediately.
- **Intraday open-interest proxy**: treats cumulative session volume as the
  active positioning input when official open interest is stale or delayed.
- **Strike-level structural mapping**: identifies the gamma wall, zero-gamma
  node, net exposure bands, and call/put imbalance zones.
- **Replay Research Lab**: runs bundled synthetic sessions offline, then exports
  session comparisons, replay alerts, and saved snapshot baselines.
- **Historical Research Journal**: saves local replay-session studies, lists
  prior entries, compares level changes, and exports Markdown/CSV/JSON reports.
- **Historical Session Store**: saves computed snapshot records locally, lists
  prior records, and exports Markdown/CSV/JSON summaries for later review.
- **Demo Lab pack**: generates a GitHub-ready offline preview folder with color
  SVG visuals, a theme-matched Textual terminal capture, snapshots, overlays,
  and lab reports.
- **Provider Fixture Workbench**: runs bundled provider-shaped fixtures offline,
  then exports health scorecards and adapter snapshots for contributor review.
- **Credential isolation**: keeps API keys and production market-data credentials
  outside the execution logic through environment variables.

## Mathematical Foundation

The engine estimates dealer hedging pressure by calculating option gamma and
scaling it into **net intraday dollar gamma exposure per 1% underlying move**.

For each option contract, the Black-Scholes gamma is:

$$
\Gamma = \frac{N'(d_1)}{S \cdot \sigma \sqrt{t}}
$$

where:

$$
d_1 =
\frac{\ln(\frac{S}{K}) + (r + \frac{1}{2}\sigma^2)t}
{\sigma\sqrt{t}}
$$

and:

$$
N'(d_1) = \frac{1}{\sqrt{2\pi}}e^{-\frac{d_1^2}{2}}
$$

| Symbol | Meaning |
| --- | --- |
| $\Gamma$ | Option gamma |
| $N'(d_1)$ | Standard normal probability density function |
| $S$ | Current underlying spot or futures price |
| $K$ | Option strike price |
| $\sigma$ | Implied volatility |
| $t$ | Time to expiration, expressed as a fraction of a 365-day year |
| $r$ | Risk-free rate |

## Intraday Dollar GEX

Raw gamma is converted into dollar gamma exposure by scaling it with cumulative
transaction volume and contract multiplier.

Call exposure is treated as positive:

$$
\text{Call GEX} =
\text{Call Volume} \times \Gamma \times S \times
\left(\frac{S}{100}\right) \times \text{Multiplier}
$$

Put exposure is treated as negative:

$$
\text{Put GEX} =
\text{Put Volume} \times \Gamma \times S \times
\left(\frac{S}{100}\right) \times \text{Multiplier} \times (-1)
$$

Strike-level net gamma exposure is:

$$
\text{Net GEX}_K =
\text{Call GEX}_K + \text{Put GEX}_K
$$

Total session net gamma exposure is:

$$
\text{Total Net GEX} =
\sum_{K} \text{Net GEX}_K
$$

The call/put imbalance ratio can be represented as:

$$
\text{GEX Imbalance} =
\frac{\sum_K \text{Call GEX}_K}
{\left|\sum_K \text{Put GEX}_K\right|}
$$

Values above `1.0` indicate call-side gamma dominance; values below `1.0`
indicate put-side gamma dominance.

## Market Structure Metrics

The terminal derives key market zones from the strike-level GEX matrix:

- **Gamma Wall**: the strike with the largest absolute concentration of net
  dealer exposure. This level often behaves like a price magnet or overhead
  resistance/support zone.
- **Zero-Gamma Node**: the strike or interpolated price where net positioning
  flips sign from positive to negative. This marks the transition between a
  lower-volatility, mean-reverting regime and a higher-volatility, trend-prone
  regime.
- **Positive Gamma Zone**: a region where dealer hedging may dampen volatility as
  hedging flows lean against price movement.
- **Negative Gamma Zone**: a region where dealer hedging may amplify volatility
  as hedging flows move with price direction.
- **Imbalance Boundary**: the area where call-side and put-side dollar gamma
  exposure materially diverge, highlighting asymmetric hedging pressure.

## Runtime Architecture

```text
gex_terminal/cli.py
  - loads environment configuration
  - selects demo, replay, live, or export workflow
  - starts adapter and calculation tasks

        |
        v

gex_terminal/adapters/*
  - translates provider or replay payloads
  - emits normalized underlying and option-volume messages

        |
        v

gex_terminal/consumer.py
  - owns async state mutation behind a lock
  - tracks spot, option volumes, expiries, and feed quality
  - exposes reset_state for clean offline session switching

        |
        v

gex_terminal/engine.py
  - vectorizes Black-Scholes gamma inputs
  - converts volume proxy into dollar GEX
  - computes gamma wall, zero gamma, call/put walls, and concentration

        |
        v

gex_terminal/tui.py
  - renders the terminal matrix, structure panels, and feed health
  - guides first-run users toward offline replay and export workflows
  - browses bundled replay sessions in-app with the same consumer/engine path
  - lets users cycle DTE, rate, and multiplier assumptions while studying output

        |
        v

exports and reports
  - snapshot JSON/CSV/Markdown
  - TradingView overlay JSON/CSV
  - Replay Lab, Provider Fixture Lab, Demo Lab, Research Journal, and Session
    Store artifacts
```

See [docs/architecture.md](docs/architecture.md) for the fuller component map,
runtime paths, and contributor boundaries.

## Installation

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -e .
```

## Quick Start

Run the terminal with seeded demo data:

```bash
gex-terminal --demo
```

Inside the terminal, press `p` to open the bundled replay browser without
leaving the app. Demo mode starts by offering `zero-gamma-flip` because it shows
the most useful market-structure transition. Use Up/Down to choose a replay,
Enter to load it, and Escape to close the browser.

Run live mode for ES:

```bash
gex-terminal --mode live --provider tradovate --symbol ES
```

Run NQ with its futures multiplier:

```bash
gex-terminal --demo --symbol NQ --multiplier 20
```

Export a color-themed Textual terminal screenshot for GitHub:

```bash
gex-terminal --demo --screenshot assets/gex-terminal-actual.svg
gex-terminal --demo --screenshot assets/gex-terminal-onboarding.svg --screenshot-view replay-browser
```

## Configuration

Copy the example environment file and fill in your local Tradovate credentials:

```bash
cp .env.example .env
```

```bash
GEX_SYMBOL=ES
GEX_SYMBOLS=ES,NQ,SPX,QQQ
GEX_DATA_MODE=demo
GEX_DATA_PROVIDER=tradovate
GEX_CONTRACT_MULTIPLIER=50
GEX_RISK_FREE_RATE=0.045
GEX_DAYS_TO_EXPIRY=0.25
GEX_REFRESH_INTERVAL_SECONDS=1.0
GEX_STALE_AFTER_SECONDS=10.0
GEX_REPLAY_PATH=sample_data/demo_replay.jsonl
GEX_REPLAY_DELAY_SECONDS=0.05

TRADOVATE_ENV=demo
TRADOVATE_NAME=your_username
TRADOVATE_PASSWORD=your_password
TRADOVATE_APP_ID=your_app_id
TRADOVATE_APP_VERSION=1.0
TRADOVATE_CID=your_client_id
TRADOVATE_SEC=your_client_secret

DATABENTO_API_KEY=your_databento_api_key
DATABENTO_DATASET=GLBX.MDP3

IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=17
```

Suggested futures multipliers:

| Product | Symbol | Multiplier |
| --- | --- | ---: |
| E-mini S&P 500 | ES | 50 |
| Micro E-mini S&P 500 | MES | 5 |
| E-mini Nasdaq-100 | NQ | 20 |
| Micro E-mini Nasdaq-100 | MNQ | 2 |

## Usage

Launch the terminal:

```bash
gex-terminal
```

Run with seeded demo data:

```bash
gex-terminal --demo
```

Run with normalized replay data:

```bash
gex-terminal --replay sample_data/demo_replay.jsonl
gex-terminal --replay sample_data/es_synthetic_full_session.jsonl
gex-terminal list-replays
gex-terminal --replay-session trend-day
gex-terminal --replay-session gap-fade
gex-terminal --replay-session call-wall-breakout
gex-terminal --replay-session zero-gamma-flip
```

`demo_replay.jsonl` is the shortest local fixture. `es_synthetic_full_session.jsonl`
is a synthetic ES 0DTE replay that walks through open, mid-session, and
late-session activity without requiring live credentials. Additional bundled
sessions cover trend, chop, volatility-spike, zero-gamma-flip, expiration
compression, gap-fade, call-wall-breakout, and provider-quality stress cases.

Run the offline Replay Research Lab across bundled sessions:

```bash
gex-terminal replay-lab replay_lab.md
gex-terminal replay-lab replay_lab.json
gex-terminal replay-lab gap_fade_lab.csv --replay-session gap-fade
```

Create a local Historical Research Journal from replay sessions:

```bash
gex-terminal journal add --replay-session trend-day
gex-terminal journal add --replay-session zero-gamma-flip
gex-terminal journal list
gex-terminal journal compare
gex-terminal journal report research_journal/journal.md
```

Journal entries are written to `research_journal/entries/`, which is ignored by
Git. Use the journal to compare gamma wall, zero-gamma, call/put wall, net-GEX,
and alert changes while keeping live credentials and generated research output
local. See [docs/research-journal.md](docs/research-journal.md) for the
workflow.

Save computed snapshots in the Historical Session Store:

```bash
gex-terminal session-store save --replay-session zero-gamma-flip
gex-terminal session-store list
gex-terminal session-store report historical_sessions/session_store.md
```

Session records are written to `historical_sessions/sessions/`, which is ignored
by Git. Use the store for snapshot archives, later day-over-day review, and
issue-friendly Markdown/CSV summaries. See
[docs/historical-sessions.md](docs/historical-sessions.md) for details.

Generate a complete offline demo pack for screenshots, GitHub issues, or
contributor onboarding:

```bash
gex-terminal demo-lab demo_lab
gex-terminal demo-lab demo_lab --replay-session gap-fade
```

The demo pack writes a color preview SVG, theme-matched Textual screenshot,
snapshot exports, TradingView overlay exports, Replay Lab reports, Provider
Fixture Lab reports, and a local manifest. See [docs/demo-lab.md](docs/demo-lab.md)
for the artifact list.

Inject raw provider-shaped sample data without live credentials:

```bash
gex-terminal inject-provider tests/fixtures/tradovate_live_sample.jsonl --provider tradovate --symbol ES
gex-terminal inject-provider tests/fixtures/databento_trade_records.json --provider databento --symbol ES --metadata tests/fixtures/databento_definition_records.json --underlying-fixture tests/fixtures/databento_underlying_mbp1_record.json
gex-terminal inject-provider tests/fixtures/yfinance_option_chain_records.json --provider yfinance --symbol SPY
gex-terminal inject-provider tests/fixtures/cboe_option_quotes_sample.csv --fixture-format cboe-option-quotes --symbol SPY
```

Provider injection replays raw or provider-shaped samples through adapter
parsing, consumer state, GEX math, snapshot export, and Provider Health
counters. It validates the software path offline; live auth, entitlements,
field drift, and reconnect behavior still require a credentialed provider
session.

Run every bundled provider-shaped fixture as an offline workbench report:

```bash
gex-terminal fixture-lab provider_fixture_lab.md
gex-terminal fixture-lab provider_fixture_lab.json
gex-terminal fixture-lab provider_fixture_lab.csv
```

The workbench currently covers sanitized Tradovate, Databento, yfinance, and
Cboe-style samples. It is useful before opening provider-adapter issues because
it captures pass/fail state, feed-health counters, computed walls, and the
snapshot baseline without using live credentials.

Override `.env` settings from the command line:

```bash
gex-terminal --providers
gex-terminal --mode live --provider tradovate --symbol ES
gex-terminal --mode live --provider databento --symbol ES
gex-terminal --mode live --provider ibkr --symbol ES
gex-terminal --mode live --provider yfinance --symbol SPY
gex-terminal --demo --symbol NQ --multiplier 20
gex-terminal --demo --refresh 0.5
```

Export a color-themed Textual screenshot for GitHub:

```bash
gex-terminal --demo --screenshot assets/gex-terminal-actual.svg
gex-terminal --replay-session zero-gamma-flip --screenshot assets/gex-terminal-actual.svg
```

Export a JSON snapshot of the current GEX state (metrics, call/put walls,
concentration, expiry breakdown, and the full strike matrix). The extension
controls the format:

```bash
gex-terminal --demo --export gex_snapshot.json
gex-terminal --demo --export gex_snapshot.csv
gex-terminal --demo --export gex_snapshot.md
```

Export TradingView-friendly overlay levels and bands:

```bash
gex-terminal --demo --tradingview-overlay gex_levels.json
gex-terminal --demo --tradingview-overlay gex_levels.csv
```

Validate a normalized replay or provider fixture before submitting it:

```bash
gex-terminal validate-fixture sample_data/es_trend_day.jsonl
```

Compare model sensitivity to multiplier, expiry, rate, IV, and volume/OI proxy
assumptions:

```bash
gex-terminal --demo --sensitivity sensitivity.md
gex-terminal --replay-session trend-day --sensitivity sensitivity.csv
```

Simulate provider-health states without live data:

```bash
gex-terminal --demo --quality-scenario all
```

While the terminal is running, these keys are available:

| Key | Action |
| --- | --- |
| `r` | Refresh the snapshot now |
| `s` | Cycle strike sort (strike / \|net\| / volume) |
| `f` | Cycle strike filter (all / near-money / active) |
| `p` | Open or close the bundled replay browser in demo/replay mode |
| `up` / `down` | Move through replay sessions while the browser is open |
| `enter` | Load the selected replay session |
| `escape` | Close the replay browser |
| `d` | Cycle DTE assumptions |
| `m` | Cycle contract multiplier assumptions |
| `i` | Cycle risk-free rate assumptions |
| `e` | Export the current snapshot to a timestamped JSON file |
| `q` | Quit |

The dashboard is designed to update continuously as new option-chain and trade
events arrive. During a live session, the matrix should surface:

- strike-level call GEX
- strike-level put GEX
- net GEX by strike
- aggregate session GEX
- gamma wall
- zero-gamma node
- call/put imbalance
- positive and negative gamma zones
- Live Gamma Regime Map state with spot, zero-gamma, gamma wall, and next trigger
- Provider Health panel with connection state, stale checks, latency, dropped
  payloads, malformed payloads, provider frame counts, parse errors,
  subscription status, reconnect counts, and entitlement placeholders

The terminal surfaces runtime lifecycle state as `LIVE`, `SIM`, `STALE`,
`CONNECTED`, or `DISCONNECTED` so the UI distinguishes real-time data from demo
and stale sessions.

Tradovate live-mode parsing is also covered by sanitized fixtures. The
`tests/fixtures/tradovate_live_sample.jsonl` sample feeds captured-style frames
through the same adapter, consumer, and engine path used by live data, then
asserts spot, option volumes, IV handling, gamma wall, zero-gamma output, and
provider health counters.

If live mode is missing credentials or market-data dependencies, the app exits
with an install/configuration hint instead of a Python traceback:

```bash
pip install -e .
```

## Development Notes

- Keep `.env` out of version control.
- Keep market-data adapters isolated from calculation logic.
- Prefer vectorized NumPy operations inside `gex_terminal/engine.py`.
- Treat consumer state as shared mutable data and update it through explicit
  locks or queue ownership.
- Use deterministic fixtures for engine tests so the math can be regression
  tested independently from live data.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
- See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.
- See [CHANGELOG.md](CHANGELOG.md) for notable project changes.
- See [docs/adapters.md](docs/adapters.md) for the provider adapter contract.
- See [docs/architecture.md](docs/architecture.md) for runtime architecture,
  first-run flow, state ownership, and contributor boundaries.
- See [docs/databento-fixtures.md](docs/databento-fixtures.md) for Databento
  fixture mapping and GLBX.MDP3 schema notes.
- See [docs/demo-lab.md](docs/demo-lab.md) for the no-credential demo pack,
  color preview, screenshots, snapshots, overlays, and lab report bundle.
- See [docs/exports.md](docs/exports.md) for snapshot and TradingView overlay
  export formats.
- See [docs/model-assumptions.md](docs/model-assumptions.md) for GEX model
  assumptions and limitations.
- See [docs/provider-injection.md](docs/provider-injection.md) for raw
  provider-shaped fixture injection without live credentials.
- See [docs/product-vision.md](docs/product-vision.md) for signature capability
  concepts and mockups.
- See [docs/replay-lab.md](docs/replay-lab.md) for offline replay reports,
  alerts, saved snapshot comparisons, and screenshot workflow.
- See [docs/replay-research.md](docs/replay-research.md) for bundled replay
  sessions, fixture validation, quality simulations, and sensitivity reports.
- See [docs/research-journal.md](docs/research-journal.md) for local historical
  replay journals, entry comparisons, and report exports.
- See [ROADMAP.md](ROADMAP.md) for planned phases and future work.
- See [SECURITY.md](SECURITY.md) for credential-handling guidance.

## Testing Targets

Recommended early test coverage:

- Black-Scholes gamma values against known reference cases.
- Dollar GEX conversion for calls and puts.
- Net GEX aggregation by strike.
- Zero-gamma interpolation across sign changes.
- Runtime lifecycle states for demo, live, stale, and disconnected sessions.
- Provider health summaries for simulated, stale, degraded, disconnected, and
  entitlement-error states.
- First-run terminal guidance, in-app replay selection, and consumer reset
  behavior for offline session switching.
- TradingView overlay export rows for levels and exposure bands.
- Live Gamma Regime Map classification for positive, negative, transition, and
  pinned states.
- Replay Lab reports for alerts, session comparison, and saved snapshot
  baselines.
- Historical Research Journal entries, entry comparisons, and Markdown/CSV/JSON
  report exports.
- Demo Lab packs for color previews, color-themed terminal screenshots,
  snapshots, overlays, and offline lab reports.
- Fixture validation for replay/provider JSONL submissions.
- Databento fixture mapping for definitions, trades, underlying quotes, and
  statistics-style open interest.
- Provider Fixture Workbench reports for bundled provider-shaped samples.
- Model sensitivity reports across multiplier, expiry, rate, IV, and volume/OI
  assumptions.
- Delayed yfinance ETF option-chain normalization with mocked adapter tests.
- Async consumer state updates under bursty tick delivery.
- Terminal rendering with empty, partial, and live-like snapshots.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

# gex-terminal

`gex-terminal` is an open, local-first terminal workbench for inspecting gamma
exposure (GEX) proxies in ES, NQ, and related options markets. It normalizes
provider or replay data, makes model assumptions visible, and produces
replayable research artifacts without presenting proxy calculations as observed
dealer inventory.

![Color replay demo lab preview](assets/gex-terminal-demo-lab.svg)

> This project is for market research and engineering experimentation. It is
> not financial advice.

## What It Does

- Prices futures-option rows with Black-76 and equity/index-option rows with
  Black-Scholes before strike aggregation.
- Keeps open interest, raw trade volume, and directionalized volume as separate
  position models instead of blending unlike quantities.
- Runs a Textual terminal with strike-level exposure, walls, a documented
  strike-profile flip, feed health, replay selection, and assumption controls.
- Replays bundled sessions and provider-shaped fixtures without credentials.
- Captures normalized sessions and exports snapshots, overlays, comparisons,
  experiment manifests, and bounded certification reports.
- Keeps provider readiness, runtime connection state, model verification, and
  predictive validity as separate claims.

The intended users are quant/model researchers, Python/data engineers, and
advanced traders who want an inspectable local workflow. The model definitions
and limitations are documented in
[Model Assumptions](docs/model-assumptions.md).

## Current Status

The source/package version is `0.4.0`, **Pre-Live Certification Hardening**.
The annotated `v0.4.0` tag identifies the reviewed closeout merge after clean
branch and merged-tree verification. The release is not published to PyPI and
does not have a hosted GitHub Release.

Provider readiness is intentionally explicit:

| Provider path | Readiness | Meaning |
| --- | --- | --- |
| Bundled demo and replay | `offline-certified` | Deterministic software and fixture path; no live-market claim. |
| Databento | `live-uncertified` | Live SDK path and bounded certification command exist; no successful credentialed run is claimed. |
| Tradovate | `scaffold` | Protocol and fixture coverage exist; credentialed chain certification is still required. |
| yfinance | `delayed` | Delayed ETF-options research path. |
| IBKR | `scaffold` | Registry and adapter boundary exist; production readiness is not claimed. |

`predictive_validity` remains `unmeasured`. Offline tests and fixtures verify
software behavior. A credentialed certification report can establish bounded
transport and input evidence for its exact run, but neither form of evidence
establishes a forecasting edge, durable provider-wide reliability, execution
quality, or profitability.

## Install

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
gex-terminal --version
```

Install the optional Databento SDK for live use, credentialed certification, or
offline DBN/DBN.ZST record replay. JSON and JSONL offline workflows use the base
installation:

```bash
pip install -e ".[databento]"
```

The broader `.[providers]` extra installs all optional provider clients.

## Quick Start

Start with seeded offline data:

```bash
gex-terminal --demo
```

Press `p` to open the replay browser, use Up/Down to choose a session, and press
Enter to load it. Press `x`, `d`, `m`, or `i` to change the expiry filter,
fallback DTE, multiplier, or risk-free rate. Press `e` to export the current
snapshot and `q` to quit.

Run a named replay or list the packaged catalog:

```bash
gex-terminal list-replays
gex-terminal --replay-session zero-gamma-flip
```

Copy `.env.example` only when you need provider configuration:

```bash
cp .env.example .env
```

Credentials belong in the local environment and must never be committed. See
[Security](SECURITY.md) before using a live provider.

## Common Workflows

The README is the front door, not the command reference. Each workflow has one
canonical guide:

| Goal | Starting command | Guide |
| --- | --- | --- |
| Explore bundled market days | `gex-terminal --replay-session trend-day` | [Replay Research](docs/replay-research.md) |
| Generate a shareable offline pack | `gex-terminal demo-lab demo_lab` | [Demo Lab](docs/demo-lab.md) |
| Exercise provider-shaped fixtures | `gex-terminal fixture-lab report.md` | [Provider Injection](docs/provider-injection.md) |
| Record and replay normalized events | `gex-terminal --replay-session trend-day --record-session` | [Captured Sessions](docs/captured-sessions.md) |
| Validate model math | `gex-terminal model-evidence report.json` | [Model Validation](docs/model-validation.md) |
| Compare position models | `gex-terminal position-model-compare INPUT.json OUTPUT.json` | [Offline Validation](docs/offline-validation.md) |
| Run reproducible governed research | `gex-terminal experiment-run SPEC.json OUTPUT_DIR` | [Research Governance](docs/research-governance.md) |
| Export snapshots and overlays | `gex-terminal --demo --export snapshot.json` | [Export Formats](docs/exports.md) |

Use `gex-terminal --help` for the complete command surface.

## Architecture And Model Boundaries

The runtime path is:

```text
CLI -> provider/replay adapter -> state consumer -> GEX engine -> TUI or report
```

The consumer is the sole owner of mutable market state. Adapters normalize
provider payloads; the engine calculates contract-aware proxy exposure; the TUI
and report modules only present derived state. See
[Architecture](docs/architecture.md) for the repository map, component
responsibilities, runtime flows, state ownership, and verification map.

The normalized message contract belongs in
[Market-Data Adapters](docs/adapters.md). Mathematical definitions belong in
[Model Assumptions](docs/model-assumptions.md), and the evidence ceiling belongs
in [Model Validation](docs/model-validation.md).

## Documentation

[Documentation Map](docs/README.md) lists the canonical owner for each topic and
routes readers to the detailed guides.

- [Roadmap](ROADMAP.md) — planned and deferred work, including the next gate.
- [Changelog](CHANGELOG.md) — shipped history.
- [Product Vision](docs/product-vision.md) — durable product direction.
- [Competitive Analysis](docs/market-analysis.md) — dated market evidence and
  positioning.
- [Contributing](CONTRIBUTING.md) — setup, verification, and pull-request rules.
- [Security](SECURITY.md) — credential handling and vulnerability reporting.

## Contributing

Start with [Contributing](CONTRIBUTING.md) and the scoped
[Good First Issues](docs/good-first-issues.md). Material model, provider, live
data, or research-authority changes must follow the repository's
[SAED adoption profile](docs/SAED_ADOPTION_PROFILE.md).

## License

Licensed under the MIT License. See [LICENSE](LICENSE).

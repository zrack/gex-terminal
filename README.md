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
- Builds portable packs with authorized input, separated model comparisons and
  verifiable review receipts; supports safe diagnosis and private local recovery.
- Keeps provider readiness, runtime connection state, model verification, and
  predictive validity as separate claims.

The intended users are quant/model researchers, Python/data engineers, and
advanced traders who want an inspectable local workflow. The model definitions
and limitations are documented in
[Model Assumptions](docs/model-assumptions.md).

## Current Status

Version **0.5.0 — Offline Research Foundation** is a research alpha. The
repository and reviewed Git tag are the release record; no PyPI publication or
hosted GitHub Release is claimed.

Bundled demo/replay is `offline-certified`. Databento is `live-uncertified`;
Tradovate and IBKR remain scaffolds; yfinance is delayed. Details belong in
[Market-Data Adapters](docs/adapters.md) and the dated
[Application Review](docs/application-review.md).

`predictive_validity` remains `unmeasured`. Offline tests and fixtures verify
software behavior. A credentialed certification report can establish bounded
transport and input evidence for its exact run, but neither form of evidence
establishes a forecasting edge, durable provider-wide reliability, execution
quality, or profitability.

## Install

Use Python 3.11/3.12 and a reviewed wheel supplied by your maintainer. Replace
the example path with the actual wheel location:

```bash
python3 -m venv gex-app
source gex-app/bin/activate
python -m pip install /path/to/gex_terminal-0.5.0-py3-none-any.whl
gex-terminal --version
gex-terminal doctor
```

No credentials or optional provider extras are needed for offline use. Follow
[First Run](docs/first-run.md) for the guided journey, update and uninstall.
Developers start with [Contributing](CONTRIBUTING.md).

## Quick Start

Start with seeded offline data:

```bash
gex-terminal --demo
```

Press `p` to open the replay browser, use Up/Down to choose a session, and press
Enter to load it. Press `q` to quit. The terminal needs at least 140×42 cells;
180×54 provides more room. See First Run for model controls and interpretation.

Run a named replay or list the packaged catalog:

```bash
gex-terminal list-replays
gex-terminal --replay-session zero-gamma-flip
```

Credentials belong in the local environment and must never be committed. See
[Security](SECURITY.md) before using a live provider.

## Common Workflows

The README is the front door, not the command reference. Each workflow has one
canonical guide:

| Goal | Starting command | Guide |
| --- | --- | --- |
| Diagnose a local installation | `gex-terminal doctor` | [Offline Doctor](docs/doctor.md) |
| Explore bundled market days | `gex-terminal --replay-session trend-day` | [Replay Research](docs/replay-research.md) |
| Generate a shareable offline pack | `gex-terminal demo-lab demo_lab` | [Demo Lab](docs/demo-lab.md) |
| Exercise provider-shaped fixtures | `gex-terminal fixture-lab report.md` | [Provider Injection](docs/provider-injection.md) |
| Record and replay normalized events | `gex-terminal --replay-session trend-day --record-session` | [Captured Sessions](docs/captured-sessions.md) |
| Validate model math | `gex-terminal model-evidence report.json` | [Model Validation](docs/model-validation.md) |
| Compare position models | `gex-terminal position-model-compare INPUT.json OUTPUT.json` | [Offline Validation](docs/offline-validation.md) |
| Run reproducible governed research | `gex-terminal experiment-run SPEC.json OUTPUT_DIR` | [Research Governance](docs/research-governance.md) |
| Export snapshots and overlays | `gex-terminal --demo --export snapshot.json` | [Export Formats](docs/exports.md) |

Private backup/recovery and safe support output belong in
[Local Support](docs/local-support.md).

Use `gex-terminal --help` for the complete command surface.

## Documentation

[Documentation Map](docs/README.md) lists the canonical owner for each topic and
routes readers to the detailed guides.

- [Architecture](docs/architecture.md) — current structure and state ownership.
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

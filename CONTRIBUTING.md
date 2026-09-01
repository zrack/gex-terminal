# Contributing

Thanks for your interest in improving `gex-terminal`. This project is early, so
thoughtful bug reports, tests, docs, mock data, and data adapter work are all
useful.

This project is intended for market research and engineering experimentation. It
is not financial advice.

## Ways to Contribute

- Review the project roadmap and pick a focused item from `ROADMAP.md`.
- Pick a scoped starter from `docs/good-first-issues.md`.
- Add deterministic tests for the GEX engine and consumer state handling.
- Improve the Textual terminal interface and empty/error states.
- Add replay or captured-session evidence that runs without live credentials.
- Validate the Tradovate scaffold with redacted, explicit certification evidence.
- Extend provider adapters without weakening the normalized schema-v2 contract.
- Improve documentation around assumptions, formulas, and limitations.
- Report bugs with reproducible inputs and expected behavior.

## Local Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -e .
```

Demo and replay work needs no provider credentials. Create a local environment
file only when testing provider configuration:

```bash
cp .env.example .env
```

Fill only the provider fields required for the path you are testing.

Never commit `.env`, broker credentials, API tokens, account IDs, or market-data
entitlements. The `.gitignore` is set up to keep local secrets out of Git, but
please check your changes before opening a pull request.

## Running the App

Launch the configured terminal (the example environment defaults to demo):

```bash
gex-terminal
```

You can also run the terminal with normalized replay data:

```bash
gex-terminal list-replays
gex-terminal --replay-session demo
gex-terminal --replay-session full-session
```

Demo and replay modes are useful for UI and engine work that should not require
live market-data credentials.

For offline research workflow work, you can also exercise the local session
store:

```bash
gex-terminal session-store save --replay-session zero-gamma-flip --session-store-dir /tmp/gex-store
gex-terminal session-store list --session-store-dir /tmp/gex-store
gex-terminal session-store report /tmp/gex-store/session_store.md --session-store-dir /tmp/gex-store
```

## Verification

Run a source compile smoke check before opening a pull request:

```bash
python -m compileall main.py gex_terminal tests
python -m unittest discover -s tests -v
```

For model changes, also run the bounded evidence gate:

```bash
gex-terminal model-evidence /tmp/model_evidence.json
```

For research-contract, provider-normalization, or performance changes, run the
applicable offline certification gates:

```bash
gex-terminal model-property-certify /tmp/model-properties.json
gex-terminal provider-fault-certify /tmp/provider-faults.json
gex-terminal performance-certify /tmp/performance.json
```

Changes to model profiles, experiment manifests, corpus registration, or batch
comparison must include their focused tests and an example run/reproduction.
See [docs/research-governance.md](docs/research-governance.md).

For package/resource changes, reproduce the CI release contract:

```bash
python -m pip install build twine
python -m build --outdir /tmp/gex-terminal-dist
python -m twine check /tmp/gex-terminal-dist/*
```

Install the wheel into a temporary virtual environment, change to a directory
outside the checkout, and exercise `gex-terminal --version`, a named replay,
and `fixture-lab`. Bundled data must resolve from package resources rather than
the repository working directory.

## Development Guidelines

This repository follows the local SAED 1.3 adoption profile in
[docs/SAED_ADOPTION_PROFILE.md](docs/SAED_ADOPTION_PROFILE.md). Route material
changes before implementation, name a work packet for L2/L3 work, preserve its
baseline and evidence ceiling, and close technical shipment separately from
external outcome validation. Use a `codex/` feature branch, focused named-file
commits, a pull request, hosted checks, merge, and a clean post-merge test for a
release slice. The closed
[GEX-ORC-001 packet](docs/work-packets/GEX-ORC-001.md) is a structural example;
no packet is currently active, and a new routed packet is required for the next
L2/L3 change.

- Keep market-data adapters separate from calculation logic.
- Keep GEX math deterministic and covered by focused tests where possible.
- Prefer vectorized NumPy operations in `gex_terminal/engine.py`.
- Price schema-v2 rows with their contract-specific model, DTE, and multiplier
  before aggregating equal strikes.
- Preserve the historical schema-v1 behavior unless a documented migration
  explicitly replaces it.
- Avoid committing generated files, local virtual environments, logs, or caches.
- Keep credentials and user-specific settings in environment variables.
- Use small, focused pull requests when changing calculation behavior.
- Document any financial-market assumptions that affect displayed metrics.
- Keep provider readiness (`offline-certified`, `delayed`, `scaffold`,
  `live-uncertified`, `live-certified`) separate from runtime connection state.

## Market-Data Adapter Guidelines

Provider adapters should normalize incoming data before it reaches
`StatefulGexConsumer`. [docs/adapters.md](docs/adapters.md) is the canonical
normalized-message contract and contains the current schema-v2 examples,
allowed IV sources, timing rules, and provider implementation notes. Do not copy
that schema into contribution guides or provider-specific docs; link to it and
document only the provider's mapping differences.

Preserve provider-scoped contract identity, event time, quantity semantics,
position-source separation, multiplier, instrument class, IV provenance, and
expiry authority. Never add open interest and trade volume together or hide a
configured fallback IV.

If you add a provider, please document:

- Required credentials and permissions.
- Whether data is live, delayed, demo, or replayed.
- How option symbols map to strike, expiration, and call/put fields.
- Contract ID stability, event-time timezone, quantity semantics, position
  source, multiplier, and instrument class.
- Known limitations or provider-specific assumptions.

If adding captured-session fixtures, never include raw authentication frames,
tokens, account identifiers, or data that cannot be redistributed. See
[docs/captured-sessions.md](docs/captured-sessions.md).

## Pull Request Checklist

Before opening a pull request, please confirm:

- The app still imports and compiles.
- No secrets or local-only files are included.
- New behavior is documented in its canonical topic guide. Update the README
  only when the front-door install, quick-start, status, or workflow routing
  changes.
- Calculation changes include tests or clearly described manual verification.
- Model evidence still reports predictive market validity as `unmeasured`
  unless a separate, reviewable validation design proves a narrower claim.
- Generated local output such as `demo_lab/`, `research_journal/`, and
  `historical_sessions/` is not included.
- UI changes can be exercised with mock data or documented sample input.
- Experiment manifests reproduce semantically and corpus verification passes
  without committing private or licensed source data.
- Generated performance reports retain the exact budgets and environment used.

## Reporting Issues

When reporting a bug, include:

- Your operating system and Python version.
- The command you ran.
- The expected behavior.
- The actual behavior, including tracebacks or logs.
- Whether you were using live data, demo data, or mock data.

Please remove credentials, account identifiers, and private market-data details
from logs before sharing them.

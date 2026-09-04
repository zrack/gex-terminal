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
pip install -e . build twine packaging
```

For an end-user installation use the reviewed wheel in [First Run](docs/first-run.md).
`gex-terminal doctor` checks local configuration/resources without a provider
connection. If an editable launcher cannot import the package, try the source
module invocation and inspect doctor output; on macOS, hidden editable `.pth`
flags can recur. A regular wheel in a dedicated environment avoids that editable
path dependency. Do not clear flags on broad filesystem trees.

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

For Databento certification, lifecycle, or capture-safety changes, also run the
focused policy and redaction suite:

```bash
python -m unittest -v \
  tests.test_databento_live \
  tests.test_databento_certification \
  tests.test_databento_certification_policy \
  tests.test_safety_controls \
  tests.test_capture_governance \
  tests.test_research_corpus
```

Changes to model profiles, experiment manifests, corpus registration, or batch
comparison must include their focused tests and an example run/reproduction.
See [docs/research-governance.md](docs/research-governance.md).

For package/resource changes, reproduce the CI release contract:

```bash
python -m pip install build twine packaging
python -m build --outdir /tmp/gex-terminal-dist
python -m twine check /tmp/gex-terminal-dist/*
```

Release verification also compares the retained 0.4.0 wheel with the candidate
using `scripts/verify_distribution_lifecycle.py --previous-wheel OLD.whl
--candidate-wheel NEW.whl --output NEW_REPORT.json`. The script uses the
`packaging` library installed with these maintainer build tools, and creates its
own temporary environment and synthetic research; it must never target a
developer or customer installation. The first dependency install may use the
network, but application commands are offline. CI exercises this lifecycle on
Python 3.11/3.12 and runs the portable pack, doctor and research checks from a
fresh wheel outside the checkout. Preserve the exact wheel hashes and report.

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
[GEX-LIVE-001 packet](docs/work-packets/GEX-LIVE-001.md) records that complete
workflow for the `0.4.0` pre-live hardening slice. The earlier
[GEX-ORC-001 packet](docs/work-packets/GEX-ORC-001.md) remains a structural
example. A new routed packet is required for any unrelated L2/L3 change. A
credentialed certification run is external observation, not permission to
change readiness or retain data without its own authority.

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

For Databento work, treat SDK subscription return values as local request IDs,
not provider acknowledgements. Preserve provider maybe-bad-book flags and
observed ordering; do not classify every discontinuity in a trade-only venue
sequence as feed loss. Keep reconnect callback, post-reconnect frame, and
per-schema record/error evidence distinct; do not infer acknowledgements the
SDK does not expose.

If you add a provider, please document:

- Required credentials and permissions.
- Whether data is live, delayed, demo, or replayed.
- How option symbols map to strike, expiration, and call/put fields.
- Contract ID stability, event-time timezone, quantity semantics, position
  source, multiplier, and instrument class.
- Known limitations or provider-specific assumptions.

If adding captured-session fixtures, never include raw authentication frames,
tokens, account identifiers, or data that cannot be redistributed. See
[docs/captured-sessions.md](docs/captured-sessions.md). Live capture requires a
validated policy before connection, and captured-session corpus registration
requires its exact matching approved policy plus verified redaction. The full
gate is in [docs/capture-governance.md](docs/capture-governance.md).

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

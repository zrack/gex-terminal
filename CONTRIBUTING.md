# Contributing

Thanks for your interest in improving `gex-terminal`. This project is early, so
thoughtful bug reports, tests, docs, mock data, and data adapter work are all
useful.

This project is intended for market research and engineering experimentation. It
is not financial advice.

## Ways to Contribute

- Review the project roadmap and pick a focused item from `ROADMAP.md`.
- Add deterministic tests for the GEX engine and consumer state handling.
- Improve the Textual terminal interface and empty/error states.
- Add mock data and replay mode so the app can run without live credentials.
- Harden the Tradovate adapter and document required market-data permissions.
- Help design a provider adapter interface for future data sources.
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

Create a local environment file:

```bash
cp .env.example .env
```

Then fill in your local Tradovate credentials in `.env`.

Never commit `.env`, broker credentials, API tokens, account IDs, or market-data
entitlements. The `.gitignore` is set up to keep local secrets out of Git, but
please check your changes before opening a pull request.

## Running the App

Launch the live terminal:

```bash
gex-terminal
```

You can also run the terminal with normalized replay data:

```bash
gex-terminal --replay sample_data/demo_replay.jsonl
```

Demo and replay modes are useful for UI and engine work that should not require
live market-data credentials.

## Verification

Run a source compile smoke check before opening a pull request:

```bash
python -m compileall main.py gex_terminal tests
```

Once a test suite is established, contributors will be expected to run `pytest`.
Until then, please include the manual verification you performed in your pull
request description.

## Development Guidelines

- Keep market-data adapters separate from calculation logic.
- Keep GEX math deterministic and covered by focused tests where possible.
- Prefer vectorized NumPy operations in `gex_terminal/engine.py`.
- Avoid committing generated files, local virtual environments, logs, or caches.
- Keep credentials and user-specific settings in environment variables.
- Use small, focused pull requests when changing calculation behavior.
- Document any financial-market assumptions that affect displayed metrics.

## Market-Data Adapter Guidelines

Provider adapters should normalize incoming data before it reaches
`StatefulGexConsumer`. The consumer expects JSON messages shaped like:

See [docs/adapters.md](docs/adapters.md) for the current adapter contract and
provider implementation notes.

```json
{
  "type": "options_volume_tick",
  "strike": 5000,
  "option_type": "C",
  "volume": 100,
  "iv": 0.15
}
```

Underlying ticks should be shaped like:

```json
{
  "type": "underlying_tick",
  "symbol": "ES",
  "price": 5000.25
}
```

If you add a provider, please document:

- Required credentials and permissions.
- Whether data is live, delayed, demo, or replayed.
- How option symbols map to strike, expiration, and call/put fields.
- Known limitations or provider-specific assumptions.

## Pull Request Checklist

Before opening a pull request, please confirm:

- The app still imports and compiles.
- No secrets or local-only files are included.
- New behavior is documented in the README or comments where appropriate.
- Calculation changes include tests or clearly described manual verification.
- UI changes can be exercised with mock data or documented sample input.

## Reporting Issues

When reporting a bug, include:

- Your operating system and Python version.
- The command you ran.
- The expected behavior.
- The actual behavior, including tracebacks or logs.
- Whether you were using live data, demo data, or mock data.

Please remove credentials, account identifiers, and private market-data details
from logs before sharing them.

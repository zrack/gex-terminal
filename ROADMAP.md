# Roadmap

This roadmap captures the major directions for `gex-terminal`. The project is
still early, so priorities may shift as the data model, provider integrations,
and terminal workflow become clearer.

## Phase 1: Prototype Hardening

- [x] Add a local mock-data and replay mode that can run without live Tradovate
  credentials.
- [x] Add deterministic tests for the math engine, consumer state updates, and
  malformed market-data messages.
- [x] Move runtime settings into a typed configuration layer for symbol, multiplier,
  risk-free rate, expiry target, provider, and update interval.
- [x] Improve startup validation so missing credentials or unsupported provider
  settings fail with clear messages.
- [ ] Document the current volume-as-open-interest proxy and its limitations.

## Phase 2: Live Data Reliability

- [ ] Complete real options-chain discovery for active ES/NQ contracts.
  Initial Tradovate discovery scaffolding exists; the next step is validating
  the exact option-chain payload shape against live/demo API access.
- Harden Tradovate reconnect, backoff, heartbeat, and shutdown behavior.
- [x] Normalize provider payloads through a stable adapter contract before they
  reach the state consumer.
- Track provider connection status, last message time, and data freshness in the
  terminal UI.
- Add logging controls suitable for live, demo, and debug sessions.

## Phase 3: Market Structure Metrics

- Add call wall, put wall, gamma concentration bands, and dealer positioning
  bias metrics.
- Improve zero-gamma detection with interpolation across strike-level sign
  changes.
- Track intraday changes in total net GEX, gamma wall, and zero-gamma levels.
- Support exposure breakdowns by expiry once chain discovery is available.
- Add exportable snapshot summaries for later review.

## Phase 4: Terminal Experience

- Add color-coded positive and negative GEX rows.
- Improve empty, loading, disconnected, and error states.
- Add sorting or filtering for strikes, expirations, and high-concentration
  levels.
- Add a compact status bar for provider, symbol, update cadence, and last refresh
  time.
- [x] Include a README screenshot or GIF once mock replay mode can render a stable
  demo.

## Phase 5: Contributor-Friendly Architecture

- [x] Define a provider adapter interface and document how to add new data sources.
- [x] Keep Tradovate as the first adapter, then add replay/CSV as a no-credential
  reference adapter.
- [x] Add provider registry scaffolds for Databento, IBKR, and yfinance.
- [x] Add issue templates for bugs, feature requests, and provider adapters.
- [x] Add a security policy for credential-handling issues.
- Add a small set of labeled good-first issues after the first public push.

## Phase 6: Packaging and Distribution

- [x] Add `pyproject.toml` project metadata and tool configuration.
- [x] Make the app installable with a console command such as `gex-terminal`.
- Add release notes and versioning once the data model stabilizes.
- Consider `pipx` installation support for users who want the terminal as a
  standalone tool.

## Good First Contributions

- Add tests for `IntradayGexEngine.calculate_gamma`.
- Add tests for malformed JSON and missing fields in `StatefulGexConsumer`.
- Add a small sample replay dataset.
- Improve terminal empty states before live data arrives.
- Document a known Tradovate options-chain payload shape.
- Add README screenshots once replay mode exists.

## Future Ideas

- Session persistence for replaying prior market days.
- CSV and JSON export for calculated GEX snapshots.
- Multiple symbol support for ES, MES, NQ, and MNQ.
- Optional historical comparison against prior sessions.
- Configurable risk-free rate and expiry selection from the terminal.
- Provider adapters for additional broker or market-data APIs.

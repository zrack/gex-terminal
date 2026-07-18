# Changelog

All notable project changes should be recorded here so the README and roadmap
can stay focused on current usage and future direction.

This project does not have tagged releases yet. Until then, entries are grouped
by date and public-prep milestone.

## Unreleased

### Added

- Provider Health panel with simulated/demo-ready feed-quality summaries,
  stale checks, latency, malformed/dropped payload counters, and entitlement
  placeholders.
- TradingView overlay exports in JSON or CSV via `--tradingview-overlay PATH`.
- Replay Research Mode catalog with trend-day, chop-day, volatility-spike,
  zero-gamma-flip, expiration-compression, and quality-stress JSONL fixtures.
- Replay Research Lab reports with offline replay alerts, session comparisons,
  leaderboards, saved snapshot baselines, and Markdown/JSON/CSV output.
- Gap-fade and call-wall-breakout synthetic ES replay sessions.
- Fixture validation command for normalized JSONL submissions.
- Model sensitivity reports for multiplier, expiry, rate, IV, and volume/OI
  proxy assumptions.
- Snapshot sharing exports in CSV and Markdown in addition to JSON.
- Snapshot Markdown/CSV sections for replay alerts and feed-quality metadata
  when those fields are present.
- Offline provider-health scenarios for stale, partial-chain, dropped-message,
  latency, and combined stress cases.
- Delayed yfinance adapter path for SPY/QQQ-style ETF option-chain research.
- Databento fixture mapping helpers, sanitized synthetic GLBX.MDP3 fixtures, and
  contributor documentation for definitions, trades, `mbp-1` quotes, and
  statistics-style open interest.
- Additional sanitized Tradovate contract-discovery and yfinance option-chain
  fixture examples.
- Live Gamma Regime Map prototype showing current regime, spot, zero-gamma,
  gamma wall, next trigger, and positive/negative/transition/pinned states.
- Code of Conduct for community participation expectations.
- GitHub social-preview source asset for sharing the project.
- Model assumptions documentation covering volume-as-open-interest proxy, sign
  convention, zero-gamma behavior, and known limitations.
- Product vision notes for signature capabilities and contributor-facing ideas.
- Synthetic ES 0DTE full-session replay dataset for no-credential testing.
- Zero-gamma interpolation edge-case tests.

## 2026-06-12

### Added

- High-impact roadmap concepts for the Live Gamma Regime Map, replayable market
  days, TradingView overlay export, GEX alert engine, and multi-symbol scanner.
- Live Gamma Regime Map mockup asset.
- README positioning for `gex-terminal` as an open-source, local-first,
  explainable GEX research terminal.
- Provider registry with Tradovate, replay, Databento, IBKR, and yfinance
  adapter scaffolds.
- Provider selection CLI support with `--provider` and `--providers`.

### Changed

- Roadmap now separates shipped work, near-term reliability items, and
  longer-horizon research workflow ideas.
- Repository metadata and docs now emphasize provider-agnostic market-data
  ingestion and replayable research.

## 2026-05-30

### Added

- Installable package metadata and `gex-terminal` console entry point.
- Contributor guidelines, security policy, issue templates, and CI smoke test.
- Replay mode and normalized market-data adapter contract.
- Initial Textual terminal UI, GEX engine, consumer state model, and sample data.

# Changelog

All notable project changes should be recorded here so the README and roadmap
can stay focused on current usage and future direction.

This project does not have tagged releases yet. Until then, entries are grouped
by date and public-prep milestone.

## Unreleased

### Added

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

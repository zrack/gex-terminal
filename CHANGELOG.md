# Changelog

All notable project changes should be recorded here so the README and roadmap
can stay focused on current usage and future direction.

The source/package version is `0.4.0`. The release candidate is prepared for
merged-tree verification; this changelog does not yet claim an annotated tag,
PyPI publication, or hosted GitHub Release.

## Unreleased

No changes yet.

## 0.4.0 - 2026-08-31 — Pre-Live Certification Hardening

### Added

- Versioned, fail-closed ES and NQ Databento certification policies with
  canonical multipliers, explicit chain/freshness/sequence/IV thresholds, and
  observed-versus-required report checks.
- Databento certification report schema v2 with distinct transport,
  target-identity, chain-ingestion, quantitative-input, and open-interest
  results plus an explicit evidence ceiling.
- Optional live `statistics` request and open-interest normalization with
  observed, unavailable, unsupported, entitlement-denied, and not-requested
  states that remain separate from trade volume.
- Scripted Databento lifecycle coverage for request failures, provider errors,
  malformed records, reconnect callbacks, post-reconnect frames, cancellation,
  disconnect completion, and bounded shutdown.
- Warning-level default process logging, configurable validated log levels, and
  central recursive redaction for secrets, sensitive identifiers, and labeled
  private payload fields.
- Versioned live-capture policy validation for rights, retention, redaction, and
  research use. Captures retain only policy identity; captured-session corpus
  registration requires an exact matching approved policy, matching rights and
  redistribution metadata, and verified redaction.

### Changed

- Reorganized documentation ownership: the README is now a concise user front
  door, architecture owns system structure, the roadmap contains only planned
  work, and `docs/README.md` routes each technical and research topic.
- Completed the repository-owned implementation in the release-ready work
  packet and narrowed the immediate roadmap to credentialed exact-run evidence
  and predeclared recurrence; no credentialed run or readiness promotion is
  claimed.
- Databento subscription diagnostics now call SDK return values local request
  IDs rather than provider acknowledgements and use actual records/errors for
  observation evidence.
- Trade-schema venue sequence discontinuities and duplicates are descriptive;
  the certification integrity gate uses provider maybe-bad-book flags and
  observed out-of-order values.
- Databento shutdown now bounds awaitable stop implementations and
  `wait_for_close`, records failures, and uses a termination fallback without
  claiming a clean stop.

### Security

- Live capture now fails before provider connection when no valid capture
  policy is supplied.
- Log and certification paths sanitize configured credentials, bearer tokens,
  account/subscription identifiers, and recursively labeled sensitive values.

## 0.3.0 - 2026-08-19 — Offline Research Certification Workbench

### Added

- Offline Databento JSON/JSONL/DBN record replay through the live record handler,
  plus a twelve-case adversarial software certification matrix.
- Descriptive saved-price-action evaluation with chronological data splits and a
  point-in-time OI/raw-volume/directionalized model comparison.
- Versioned model-profile and experiment-spec contracts, reproducible manifests
  with input/profile/semantic-result digests, and fail-closed reproduction.
- Append-only hash-chained research-corpus registration with source integrity,
  immutable dataset/split identity, rights, redaction, outcome, and cost fields.
- Batch day/expiry/DTE-layer comparisons that preserve position-source
  separation and leave low-coverage directional results unscored.
- Model-property, provider-fault, and generated-chain performance certification
  reports with explicit budgets and offline evidence ceilings.
- Canonical provider-readiness states separate from runtime connection state.
- SAED 1.3 repository adoption profile, routed work packet, research governance
  guide, decision record, and current architecture diagram.

- Optional schema-v2 aggressor-side and direction-source provenance for
  incremental trade volume, including Databento trade-side fixture mapping.
- A parallel aggressor-directionalized volume GEX model with explicit coverage,
  unknown-volume, participant/open-close limitations, and unchanged default
  model behavior.
- JSON, CSV, and Markdown model-comparison reports with regime/strike sign
  agreement, wall distances, strike rank correlation, normalized profile
  distance, and an explicit `unmeasured` predictive-validity ceiling.
- A bounded Black-76 implied-volatility inversion with no-arbitrage checks,
  deterministic bisection, and per-tick price, futures-midpoint, time, rate,
  convergence, and error provenance.
- Mixed-schema Databento live ingestion for ES/NQ definitions, option trades,
  and continuous-futures `mbp-1` quotes, plus a redacted, fail-closed
  `databento-certify` transport/chain/model-input report.

### Changed

- Black-76 IV inversion now requires an aligned futures midpoint and records its
  age and maximum permitted age. Stale, future-dated, crossed, incomplete, and
  wrong-contract inputs fail closed; Databento trade sequences are preserved.

- Schema-v2 `iv_source` now distinguishes provider IV, Black-76-inverted IV,
  and configured fallback IV. Only configured fallback values degrade IV
  quality accounting.
- Live Databento documentation now distinguishes the optional SDK from the base
  install, states ES/NQ multiplier requirements, and documents the fail-closed
  certification exit status.
- Terminal and documentation semantics now say `GEX Proxy Regime` and
  `live-uncertified`; neither a runtime `LIVE` state nor a proxy calculation is
  presented as provider certification or observed dealer inventory.

## 0.2.0 - 2026-08-04

### Added

- Normalized message schema v2 with provider-scoped contract identity, strict
  timezone-bearing event time, expiry and instrument class, incremental versus
  cumulative volume semantics, position source, and optional per-contract
  multiplier; schema v1 remains supported.
- First-class `all`, `0dte`, and exact-expiry filtering in configuration, CLI,
  consumer state, exports, and the terminal `x` control.
- Black-76 gamma for futures options, Black-Scholes with carry support for
  equity/index options, and per-contract DTE/multiplier pricing before
  same-strike aggregation.
- Separate strike-profile flip and nearest-neutral outputs, with the historical
  `zero_gamma` field retained as a documented compatibility alias/fallback.
- Append-only captured-session schema with header/event/footer records,
  per-message and aggregate unkeyed SHA-256 consistency checks, crash-visible
  `.partial` files, atomic finalization, event-time replay, speed/gap controls,
  session-store inventory, and journal ingestion.
- Bounded `model-evidence` JSON/Markdown reports with independent
  Black-Scholes/Black-76 oracles, ES dollar-GEX scaling, deterministic checks,
  and predictive market validity explicitly reported as `unmeasured`.
- Explicit `tradovate-certify` read-only network probe with mandatory user
  acknowledgement, redacted evidence, failed-closed exit status, and separate
  transport versus quantitative-GEX results.
- Package-resource helpers and installed-wheel tests for bundled replay sessions
  and provider fixtures from an arbitrary working directory, with stable public
  resource identities instead of installation-specific absolute paths.
- Python 3.11/3.12 CI coverage with build, metadata validation, wheel install,
  CWD `.env` loading, `--version`, named replay, demo-lab, provider injection,
  and fixture-lab smoke tests.

### Changed

- Tradovate transport now uses raw-token WebSocket authorization, waits for
  authorization/subscription acknowledgements, maps nested official quote
  entries, handles cumulative total-volume/open-interest values, renews tokens,
  backs off on retryable failures, and unsubscribes during shutdown. Registry
  status remains `scaffold` pending a successful credentialed certification.
- Model sensitivity keeps its base scenario aligned with the contract-aware
  snapshot instead of silently falling back to scalar legacy assumptions.
- Snapshot schema v2 records model version, normalized schema versions, pricing
  models, position sources/conflicts, contract counts, expiry filter, units,
  day count, aggregation, as-of time, and strike-profile semantics.
- Bundled data moved from the former repository-root replay/fixture directories
  into `gex_terminal/data/` so offline workflows survive wheel installation.

### Earlier baseline additions

- Provider Health panel with simulated/demo-ready feed-quality summaries,
  stale checks, latency, malformed/dropped payload counters, and entitlement
  placeholders.
- TradingView overlay exports in JSON or CSV via `--tradingview-overlay PATH`.
- Replay Research Mode catalog with trend-day, chop-day, volatility-spike,
  zero-gamma-flip, expiration-compression, and quality-stress JSONL fixtures.
- Replay Research Lab reports with offline replay alerts, session comparisons,
  leaderboards, saved snapshot baselines, and Markdown/JSON/CSV output.
- Demo Lab command that generates a no-credential demo pack with a color SVG
  preview, color-themed Textual screenshot, snapshot exports, TradingView
  overlays, Replay Lab reports, Provider Fixture Lab reports, and a manifest.
- Historical Research Journal command for local replay-session entries,
  entry-to-entry comparisons, and Markdown/CSV/JSON report exports.
- Color-aware Textual SVG screenshot export helper so actual terminal captures
  match the public README preview palette more closely.
- First-run terminal guide with an in-app replay session browser for demo/replay
  workflows, plus consumer state reset support for clean offline session loads.
- Terminal-side DTE, contract multiplier, and risk-free rate controls for quick
  model-assumption checks while studying offline sessions.
- Historical Session Store command for local snapshot records, record lists, and
  Markdown/CSV/JSON report exports.
- Good-first issue template and issue-ready contributor starter list.
- Replay-browser README onboarding screenshot generated from the actual Textual
  terminal.
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
- Tradovate live-frame diagnostics, malformed quote quarantine, stricter
  normalized schema validation, and a sanitized live-sample fixture that drives
  the adapter, consumer, and engine path in regression tests.
- Offline provider injection command for Tradovate raw frames, Databento fixture
  joins, yfinance option-chain samples, and Cboe-style option quote CSV samples.
- Offline Provider Fixture Workbench command for bundled provider-shaped fixture
  scorecards, feed-health counters, and Markdown/JSON/CSV report exports.
- Live Gamma Regime Map prototype showing current regime, spot, zero-gamma,
  gamma wall, next trigger, and positive/negative/transition/pinned states.
- Code of Conduct for community participation expectations.
- GitHub social-preview source asset for sharing the project.
- Model assumptions documentation covering position proxies, sign convention,
  strike-profile compatibility behavior, and known limitations.
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

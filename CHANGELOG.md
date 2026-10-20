# Changelog

All notable project changes should be recorded here so the README and roadmap
can stay focused on current usage and future direction.

The source/package version is `0.6.0`. Release tags identify verified merged
trees; prior `v0.4.0` remains unchanged. No PyPI publication or hosted GitHub
Release is claimed.

## Unreleased — Documentation And Visual Refresh

- Reconcile setup, saved full sessions, pricing models, IV age, comparisons,
  private artifacts and contributor guidance with the current source.
- Refresh the actual synthetic Terminal, replay-picker and Wind Tunnel captures;
  add paired-model and focused-strike views. Refresh both architecture diagrams
  and the two-component social preview with file-level provenance.
- Preserve older visual captures and dated study/build records. Keep historical
  data validation separate from live readiness and observed participant evidence.
- Correct stale security/package and fixture-result examples. This refresh
  changes documentation and visuals, with no pricing or runtime changes.

## Unreleased — Wind Tunnel Model Comparisons

- Compare the default and aggressor-directionalized proxies side by side from
  one frozen checkpoint, with shared price, IV and time assumptions, matched
  strike axes and separate pricing coverage and exclusions.
- Add isolated-shock presets and an explicit, bounded 54-case sensitivity grid
  per market. Unavailable cases remain distinct from zero; sign and wall
  stability describe only evaluated points, not future market behavior.
- Keep model-comparison requests and results in portable, reproducible local
  receipts. All calculations and chart assets remain offline.
- Allow explicitly supplied saved ES/NQ checkpoints in one workbench. The saved
  starter offers the other registered checkpoint when it remains valid; source
  selection does not download data or request provider credentials.
- Separate captured source health from replay/demo mode. Show accepted-IV age
  beside pricing coverage, with original observation clocks for retained IV,
  explicit unknown ages and capture-precision ambiguity, and scenario model time.
  The five-minute age reference does not change IV validity or pricing selection.
- Add original/scenario futures-price markers and matched **Focused** / **Full
  range** strike charts. Focus changes only presentation; all strikes remain in
  totals and exact-values tables.
- Reuse exact gamma vectors within one bounded calculation request and omit
  redundant contribution rows/checkpoint echoes from browser model comparisons.
  Save full portable receipts from the original input, preserving deterministic
  reproduction and separate model cohorts without provider requests.

## Unreleased — Full Historical Sessions

- Stream and verify explicit local captures up to 1 GiB / 2 million events,
  replay only a detached verified disk copy, and keep browser intake bounded
  at 4 MiB / 5,000 events. Large-session cancellation releases its spool.
- Expand checkpoint transport to 8 MiB and JSON requests/receipts to 32 MiB
  for full-session detail, retaining 5,000 rows and separate 4 MiB browser intake.
- Load long saved sessions without source-time delays; retain 60× replay for
  short samples. Show the verified time span, event count and selected policy
  in the starter, with a final checkpoint for Wind Tunnel.
- Batch offline compatibility-summary refreshes while preserving every canonical
  event update. Publish a complete accepted prefix before yielding, snapshots
  and checkpoints, and flush on cancellation; ordinary per-event behavior remains.
- Open large frozen sources in Compare and calculate their labeled coarse
  landscape only on request. Preserve valid comparison/coverage on a surface
  failure, and yield between sampled cells for bounded cancellation.
- Add a metadata-quoted, $5-capped full-day ES/NQ acquisition helper with
  immutable plans, fresh cost checks, private progress receipts and no retries.
  Convert native data with a disk-backed causal merge and one consumer across
  midnight; validate raw quantities, identity, pricing and checkpoint receipts.
- Keep downloaded payloads, normalized captures and validation evidence private.
  [Full-day instructions](docs/databento-credit-trial.md#full-trading-day-es-and-nq)
  define the sampled BBO, matched-future and trade-volume scope.

## Unreleased — Saved Data Starter

- Add **Saved data — Both** to fresh reviewed setup choosers, with ES/NQ
  selection and explicit CLI launch or registration-only commands.
- Verify completed normalized captures, retain a private frozen source by symbol
  in the research folder, and reconstruct a fresh final checkpoint on each
  launch without modifying the original capture.
- Apply captured multiplier, rate and fallback DTE to both views, with explicit
  defaults only for missing values and refusal of supplied invalid assumptions.
- Open Wind Tunnel on the final checkpoint while Terminal replays at 60×;
  subsequent selections remain independent. Preserve unpriced exposure and
  use no provider requests or credits.
- Keep existing installed launchers unchanged; a fresh reviewed setup supplies
  the new saved-data choice. [First Run](docs/first-run.md#open-saved-es-or-nq-data)
  owns startup and source-registration instructions.

## Unreleased — Pricing Coverage Displays

- Add visible Terminal and Wind Tunnel coverage panels with priced/selected
  contract and quantity counts, percentages, and explicit complete, partial,
  all-unpriced, empty and unreported states.
- Explain unavailable IV using captured premium bounds and quote inputs in
  details. Preserve unavailable IV and raw quantity; scenario shifts do not
  rewrite the original failed-inversion evidence or fill its exposure.
- Add presentation and browser/Terminal regressions for pricing gaps, retained
  IV, empty selections, rounding and stale-source clearing. Pricing calculations
  and portable result formats are unchanged.

## Unreleased — IV Resolution And American Futures Pricing

- Replace new Databento 15% IV defaults with qualified earlier same-contract
  observations or explicit unavailable IV. Preserve raw quantity, exclude
  unpriced exposure, and show raw/priced/retained coverage across Terminal,
  exports, comparisons, sensitivity and Wind Tunnel.
- Price confirmed American futures options with a zero-drift early-exercise
  CRR lattice for both IV and call/put-specific gamma. Use adjacent trees and a
  European control variate; test against independent finite-difference values.
- Preserve new pricing provenance through capture/checkpoint/import workflows.
  Historical captures retain their selected model and strict receipt behavior;
  numerical discretization and empirical pricing accuracy remain qualified.

## Unreleased — Databento Trade Reconciliation

- Preserve a deterministic native trade fingerprint so distinct Databento fills
  sharing a venue sequence accumulate correctly. Continue suppressing exact
  retransmissions and older sequences with a bounded current-sequence cache.
- Preserve the validated identity through guided Wind Tunnel capture import;
  keep internal duplicate evidence out of frozen checkpoints and public
  snapshots. Legacy, cumulative and OI ordering remains unchanged.
- Add synthetic native-SDK and conversion/replay/import regressions. Broader
  private ES/NQ samples validate both sides across weekly, month-end and
  quarterly expirations; IV fallbacks and American pricing approximation remain
  explicitly qualified.

## Unreleased — Sparse-Side Displays And Pricing Assumptions

- Show calls-only, puts-only and empty selected quantities explicitly. Export an
  absent-side wall and an undefined call/put ratio as `null`; omit unavailable
  walls from overlays, and preserve absence in saved-session comparisons.
- Preserve Databento exercise style and CFI through normalized state and frozen
  checkpoints. Surface European-exercise pricing assumptions, configured rates
  and ACT/365 timing in Terminal details, exports and Wind Tunnel results.
  American early exercise remains unmodeled with unmeasured approximation error;
  older captures without style metadata remain explicitly unknown.
- Add sparse-data and model-provenance regressions. Saved ES/NQ validation now
  checks current displays, exports and raw-data re-normalization in addition to
  independent arithmetic and scenario reproduction, without provider requests.
- Keep exact historical Demo Lab reproduction strict when corrected sparse-side
  metrics change decision hashes. The prior-version gate verifies immutable old
  evidence, checks only documented corrections and metadata additions, and
  requires exact reproduction of the corrected current pack.

## Unreleased — Databento Historical Credit Trial

- Add checkout helpers for private key setup, bounded historical cost previews
  and explicitly acknowledged ES/NQ downloads within declared credits.
- Default historical underlying sampling to interval-end BBO-1s midpoints;
  preserve trade detail and stop safely on cost, record, input or provider errors.
- Convert saved DBN/JSON files to captured sessions for Terminal and Wind Tunnel,
  with offline budget, timing, privacy and capture round-trip regressions.
  See [the operator guide](docs/databento-credit-trial.md) and
  [GEX-DATABENTO-TRIAL-001](docs/work-packets/GEX-DATABENTO-TRIAL-001.md).

## Unreleased — Read-Only Tradovate Raw Collector

- Add `tradovate-capture` for bounded private contract REST and market-data
  WebSocket evidence before normalization. Require explicit network
  acknowledgement, a valid capture policy, and a new owner-only output directory.
- Exclude authentication and outgoing frames, account for safety omissions,
  retain policy identity and file hashes, bound requests/frames/bytes/time, and
  clean up owned network resources. No order operations are available.
- Disable HTTP redirects and verify the final WebSocket endpoint before sending
  a Tradovate token. Retrieve simultaneous receive/heartbeat failures so raw
  provider exceptions do not escape through orphan-task logs.
- Add offline mocked regressions and an operator guide for separate ES/NQ runs,
  access/rights decisions, private retention, and review before sharing.
  [GEX-TRADOVATE-CAPTURE-001](docs/work-packets/GEX-TRADOVATE-CAPTURE-001.md)
  owns acceptance. Issue #4 remains open until actual ES/NQ payloads are captured
  and validated; Tradovate readiness stays `scaffold`.

## Unreleased — Tradovate Offline Verification

- Rework PR #10 into explicitly synthetic ES/NQ discovery and quote coverage
  through the production adapter, consumer and engine. Replace fixture-only
  checks and add parameter, lifecycle and negative certification regressions.
- Reject malformed numeric parameters and quantities before lossy coercion;
  bound retry delays, preserve complete owned cleanup after background failures,
  and keep raw provider values out of rejection logs and probe errors.
- Tighten probe evidence gates and document implemented mappings, unverified
  aliases and access requirements. Actual sanitized ES/NQ demo or live payloads
  remain required by issue #4; Tradovate stays `scaffold`.
- [GEX-TRADOVATE-OFFLINE-010](docs/work-packets/GEX-TRADOVATE-OFFLINE-010.md)
  owns acceptance and integration of [PR #10](https://github.com/zrack/gex-terminal/pull/10).

## Unreleased — Documentation And Recruitment Source Closeout

- Reconcile architecture and component diagrams with guided capture intake and
  immutable Terminal handoff, including the Terminal-owned listener lifetime.
  Refresh current assessment, roadmap, study routing and dated design evidence.
- Track blank recruitment/consent sources and delivery-generation tools with
  packaging regressions. Record the participant-only delivery amendment while
  preserving frozen application, tasks, study kits and original delivery bytes.
  Actual participant sessions and issue #4's payload gate remain open.
- [GEX-DOC-CLOSEOUT-001](docs/work-packets/GEX-DOC-CLOSEOUT-001.md) owns acceptance.

## Unreleased — Guided Session Intake And Current-Build Study

- Open a local complete capture in Wind Tunnel, verify integrity, inspect source,
  time and model assumptions, and freeze a selected capture prefix. Use the
  production consumer and existing opaque portable checkpoint/receipt format.
- Bound uploads and in-memory retention; omit arbitrary private metadata and
  extensions from responses and artifacts. Preserve the previous valid source
  when an inspection fails or is canceled.
- Prepare a separately identified current-build study kit with synthetic ES/NQ
  captures, frozen task/scoring materials, exact wheel/source/dependency hashes
  and blank participant scorecards. Preserve the September study unchanged;
  automated rehearsal does not count as observed participant evidence.
- [GEX-INTAKE-STUDY-001](docs/work-packets/GEX-INTAKE-STUDY-001.md) owns acceptance.
  Issue #4 stays open for actual Tradovate payloads.

## Unreleased — Terminal Checkpoint Handoff

- Press `w` in Terminal to freeze demo/replay state and open Wind Tunnel on
  that exact checkpoint. Capture effective assumptions, the expiry filter,
  source quality and separated quantities without following later events.
- Preserve Terminal's trade-first/OI-fallback selection as an explicit model;
  keep volume, OI and directionalized comparison models independent. Export
  a checkpoint with `--wind-tunnel-checkpoint PATH` and open it with
  `wind-tunnel --checkpoint PATH`; scenario receipts embed the frozen input.
- Keep live capture and issue #4's actual Tradovate payload requirement open.
  [GEX-WIND-HANDOFF-001](docs/work-packets/GEX-WIND-HANDOFF-001.md) owns acceptance.
- Reconcile the roadmap's historical research and live delivery paths, refresh
  the current project/market assessments and retain observed-user gates.

## Unreleased — Tradovate Acknowledgement Frames

- Preserve market-data events after a successful acknowledgement in the same
  WebSocket frame; process the frame before reporting authorization or
  subscription success, and reject trailing explicit errors.
- Add synthetic frame/session regressions and document their reproduction and
  evidence limits. [GEX-TRADOVATE-ACK-001](docs/work-packets/GEX-TRADOVATE-ACK-001.md)
  owns the repair. Issue #4 remains open pending actual Tradovate ES/NQ payloads.

## Unreleased — Databento Correctness

- Replace Databento's deliverable multiplier with validated dollar contract
  units, retaining a visible configured fallback when metadata is unavailable.
- Subscribe to declared ES/NQ quarterly, daily, weekly and month-end option
  products and preserve their actual futures underlying identity.
- Reject undefined OI quantities, preserve reference dates and update actions,
  and invalidate deleted OI without replacing newer-reference observations or
  disturbing trade volume. Add offline regressions including real SDK records.
- [GEX-DATABENTO-035](docs/work-packets/GEX-DATABENTO-035.md) owns this change's
  verification and integration status. Databento remains `live-uncertified`.
- Preserve provider-scoped futures identity through rollover and reconnect,
  quarantining retained old-contract exposure. Reject undefined timestamps and
  preserve nanosecond ordering. Add independent parameter/state tests, fresh
  installed CLI/DBN/terminal verification and a measured provider-path load gate;
  [Offline Validation](docs/offline-validation.md) owns reproduction commands.
- Clear stale terminal metrics, expiry totals, selected quantities and flow
  when a rollover leaves no active contracts; stale snapshot export is blocked.
- Preserve saved identity-free research decision hashes by emitting feed-quality
  identity provenance only when contract, quarantine or rejection evidence exists.

## 2026-09-27 — Unified Starter

- Fresh setup folders offer **Terminal**, **Wind Tunnel** or **Both** through
  one starter, with direct shortcuts retained. Both owns the local Wind Tunnel
  process it starts and stops it when the terminal exits; the two interfaces
  retain independent research state.
- Existing installed launcher bytes, separate research, the original 0.6.0
  setup and the immutable `v0.6.0` tag are preserved. This is a setup-helper
  enhancement using the existing application wheel, without a version bump or
  new tag. [GEX-START-001](docs/work-packets/GEX-START-001.md) owns its acceptance
  and integration status; [First Run](docs/first-run.md) owns usage.

## 0.6.0 — 2026-09-27 — Market Wind Tunnel

### Added

- Packaged offline browser Wind Tunnel with calculated 3D/2D exposure, matched
  scenario comparison, sampled fragility maps, checkpoint selection and bounded
  search across spot, IV, time, expiry and separated position assumptions.
- Immutable experiment receipts with source and calculation identity, local
  save/reopen/export/reproduce workflows and three reproducible synthetic examples.
- A loopback-only service with capability-protected APIs, bounded research
  storage and bundled chart assets; fresh setup folders include a Wind Tunnel
  launcher. See [Wind Tunnel](docs/wind-tunnel.md) and
  [GEX-WIND-001](docs/work-packets/GEX-WIND-001.md) for acceptance status.

- A reviewed-wheel setup helper and local handoff bundle with reusable macOS/POSIX
  launchers, isolated offline configuration, separate research storage, exact
  payload verification and safe reuse/update selection. Python remains required;
  dependency wheels can be included for installation without downloads.
- A focused replay chooser, contextual keyboard help and source/assumption
  details, plus readable essential table columns from 100×32 cells.
- Fixture-specific replay expectations for alert meaning, event timing and
  structural levels, extending identity and report-format checks.
- Linux/macOS verification across Python 3.11/3.12 with retained, bounded
  synthetic reports and previews, build/runtime identity, file hashes and
  explicit failed or missing check outputs. See [Offline CI](docs/offline-ci.md).
- A repeatable maintainer preview-refresh command using explicit synthetic
  inputs and a local provenance manifest. See [Demo Lab](docs/demo-lab.md#contributor-preview).
  [GEX-OFFLINE-002](docs/work-packets/GEX-OFFLINE-002.md) owns verification;
  frozen study materials and external evidence gates are unchanged.

### Fixed

- Table selection now follows the chosen strike through ordinary refreshes.
  Replay choices stay visible while browsing. Saved snapshots have collision-
  resistant filenames and visible destination feedback.
- Generated demo-preview table headings and regime-label layout; the onboarding
  preview uses enough rows to expose its replay choices.
- Replay-picker keyboard routing repair and real-keyboard regression coverage
  for selection/loading from a focused strike table, with normal table and
  overlay controls preserved. [GEX-UX-001](docs/work-packets/GEX-UX-001.md) owns
  acceptance evidence. Live/capture restrictions and replay-writer settlement
  remain unchanged; this is not part of the original `v0.5.0` tag or wheel.

### Changed

- Terminal hierarchy emphasizes four research metrics, instrument/source and
  primary actions with a restrained amber/cyan palette. Compatibility-level and
  quantity labels preserve their proxy meaning; unchanged samples are labeled
  rather than rendered as a misleading full-height trend strip.
  [GEX-UX-002](docs/work-packets/GEX-UX-002.md) owns review and verification.
- Prepared an exact offline study-build handoff with frozen source, wheel,
  runtime, synthetic fixtures and scoring materials; automated rehearsal remains
  separate from observed participant acceptance. [GEX-STUDY-001](docs/work-packets/GEX-STUDY-001.md)
  owns verification and [Study Build](docs/study-build.md) owns the procedure.
- Extended local documentation checks to heading fragments and clarified
  architecture/diagram maintenance and canonical documentation ownership in the
  contributor workflow. Detailed study/build records stay outside the README.
- First-run controls and architecture document conditional picker key ownership;
  the roadmap prioritizes observed offline use on an exact repaired build.
  Automated keyboard checks do not establish unaided customer acceptance.

## 0.5.0 - 2026-09-04 — Offline Research Foundation

### Added

- Offline privacy-safe doctor with text/JSON diagnostics, meaningful exit codes,
  installed-resource checks and a lightweight missing-dependency fallback.
- Dedicated synthetic NQ ×20 schema-v2 replay and a portable 20-artifact Demo
  Lab loop with copied input, separated position models, explicit runtime
  compatibility and verifiable/reproducible review receipts.
- Guided wheel installation and a repeatable disposable install/upgrade/
  failed-upgrade/rollback/uninstall check that preserves research byte identity.
- Redacted local support bundles and private whole-artifact backup, verification
  and restore. Retention requires a matching verified backup, exact plan
  confirmation, staged revalidation and bounded recovery; no real user data was
  deleted during verification.
- Offline prospective live-population plan/result validation with canonical
  policy identity and complete failed/missed-attempt accounting. The supplied
  template intentionally fails until approved declarations are supplied; no
  live execution or readiness promotion is added.
- Prepared customer interview/task kit, comparable paper concepts, rights
  questions and assumption-based first-year economics; no collected customer
  or pricing evidence is implied.

### Fixed

- Terminal refresh callbacks now belong to the dashboard screen and revalidate
  ownership after asynchronous work, preventing render/cache publication after
  shutdown, quit or screen replacement. Resize remains dashboard-bound behind
  overlays. Six deterministic regressions raise the full suite to 425 tests;
  genuine mounted rendering errors remain visible.
- Compact terminal rendering at 140×42 and above, clear guidance below the
  supported minimum, and state-preserving resize coverage.
- Experiment v2 manifests now bind complete specification, profile, input,
  implementation and result identities. Reproduction rejects inconsistent or
  unsupported metadata and nonempty output targets; legacy v1 verification is
  explicitly partial rather than silently promoted.

- Numeric configuration now fails closed across environment, direct construction
  and CLI/UI replacement, with secret-safe errors and stale-threshold guards.
  Offline injection/fixture reports now label replay origin and no-network
  evidence instead of live connection health.

- Replay reports now create analytical transitions only for accepted consumer
  updates, align snapshot time with model as-of, and separate raw input audit
  timestamps from accepted-state chronology. Untimed input is explicitly
  processing-time evidence, not observed market time.

- Replay selection now settles the previous CLI writer before resetting state;
  active fixed-delay/event-clock streams cannot contaminate a replacement
  session. Failed writers block replacement and remain visible at shutdown.

- Bound bundled replay workflows to catalog instrument identity and rejected
  unsupported symbol labels on the seeded ES demo. Snapshot exports now
  distinguish the configured fallback multiplier from actual selected-contract
  multipliers, including heterogeneous inputs.

### Changed

- Accepted offline engineering through PR #25 after independent review, four
  hosted checks and 419 tests on clean merged main. Closed contributor packets
  while keeping customer activation, rights and live observations open.
- Reprioritized the roadmap around application correctness, offline preflight,
  reuse of existing research packs, and one usable installation path; corrected
  phase dependencies and separated commercial and empirical research tracks.
- Refreshed the application health review with repair evidence and remaining
  customer/live boundaries. Shipped work is removed from the roadmap's active
  implementation checklist; README links to canonical guides and architecture.
- Corpus verification explicitly labels point-in-time evaluation eligibility
  not assessed; registration integrity is not empirical-research approval.
- Source distributions include canonical docs, maintainer lifecycle checks and
  referenced assets, without local credentials or generated research packs.
- Refreshed the September 2026 competitive landscape with Nightglass,
  GammaTape, FlashAlpha, current industry evidence, a narrower native-futures
  positioning, and a gated path from research kernel to commercial product.
- Expanded the product vision and roadmap around a bring-your-own-data desktop
  hypothesis, a comparable hosted-cockpit alternative, customer validation,
  distributable offline workflows, bounded live certification, design-partner
  evidence, governed outcome research, and commercial exit criteria.
- Updated GitHub CI to the Node 24-based `actions/checkout@v7` and
  `actions/setup-python@v7` releases after the hosted runner reported the older
  Node 20 action runtimes as deprecated.

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
- Closed the repository-owned implementation work packet after contributor and
  closeout pull requests, branch and merged-tree gates, and release tagging.
  The immediate roadmap is now limited to credentialed exact-run evidence and
  predeclared recurrence; no credentialed run or readiness promotion is
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

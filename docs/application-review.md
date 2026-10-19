# Application State And Health Review

Updated October 18, 2026 against the current `0.6.0` source, including Market
Wind Tunnel, the unified starter, provider repairs, checkpoint handoff and
guided captured-session intake. This document
owns the dated state assessment and verification limits; earlier release
evidence is retained below rather than presented as verification of later changes.
[Architecture](architecture.md) owns implementation structure;
[Roadmap](../ROADMAP.md) owns remaining work. Earlier assessments remain in Git.

## Assessment

The application is a substantial offline research workbench: contract-aware
structural calculations, separate quantity models, terminal/replay workflows,
browser scenarios and fragility searches, journals/experiments/corpus tooling,
portable receipts, installation helpers and local recovery are available.
The recent Databento fixes and Tradovate ACK-frame repair strengthen the
offline provider implementation without certifying real provider operation.

The checkpoint handoff now connects current demo/replay Terminal state to an
immutable Wind Tunnel baseline. Press `w` in Terminal, or export with
`--wind-tunnel-checkpoint PATH` and launch `wind-tunnel --checkpoint PATH`.
The explicit `terminal_selected` model preserves Terminal's per-contract
positive-trade-volume preference with OI fallback; separate raw/OI/directional
choices retain their meanings. Source/cutoff, rows and effective assumptions
are detached from later events, and saved receipts carry the frozen inputs for
fresh-process reproduction without the original checkpoint/server.
[Wind Tunnel](wind-tunnel.md) owns the supported user/receipt contract;
[GEX-WIND-HANDOFF-001](work-packets/GEX-WIND-HANDOFF-001.md) owns final integration
and verification status. This handoff accepts demo/replay state only.

Guided intake now verifies a complete native `*.gex-session.jsonl` capture,
shows bounded source/time/assumption and quality information, then reconstructs
only the explicitly selected prefix through the production consumer. It reuses
the immutable checkpoint and portable-receipt path. The loopback service accepts
uploaded bytes, not server paths; it retains allowlisted state in bounded
memory and removes unknown labels/extensions after integrity verification.
[Captured Sessions](captured-sessions.md) and [Wind Tunnel](wind-tunnel.md)
own the supported format and workflow;
[GEX-INTAKE-STUDY-001](work-packets/GEX-INTAKE-STUDY-001.md) owns acceptance.
This does not supply a general CSV/provider importer, source rights, live-state
capture, continuous synchronization or observed participant acceptance.

Three remaining technical priorities affect trustworthy functionality:

- The current Databento option path derives IV from trades without requesting
  option bid/ask quotes. Stream freshness and per-option model-input freshness
  need separate quality reporting; quote bootstrap is further provider work.
- Exercise style, exact expiry timezone, calendars/session rules and supported
  approximations need an explicit contract-domain policy. Uniform IV shocks
  remain sensitivity tests, not a general skew/term-structure risk engine.
- An old receipt needs its authorized inputs and compatible executable
  environment. Original-model reproduction and deliberate current-model
  restatement must have separate identities.

No recorded participant activation, real-user retention, tested pricing,
credentialed recurring ES/NQ operating envelope or predictive validity is
established by these engineering checks. Databento remains `live-uncertified`;
Tradovate/IBKR remain `scaffold`; `predictive_validity` remains `unmeasured`.
Issue #4 stays open for actual sanitized Tradovate demo/live payloads.

The [October market review](market-analysis.md) supports testing a complete
historical-research workflow separately from a live tactical cockpit. The
former needs authorized inputs and observed repeat use; the latter additionally
needs recurring live scope. [Roadmap](../ROADMAP.md) owns both branch gates.
The separate [October guided-intake cohort](studies/guided-intake-2026-10-18.md)
now freezes the current workflow, exact build and synthetic inputs; the
September study remains unchanged. A separately identified
[participant delivery](studies/participant-delivery-2026-10-18.md) and
[recruitment procedure](study-recruitment.md) are prepared. Zero participant
sessions have been observed; six consented observations remain the next gate.

## Historical Acceptance Through September 26

The repaired `0.5.0` foundation provided corrected result identity,
fail-closed configuration, isolated replay replacement and verifiable portable
research packs. All five P1 correctness repairs, compact-terminal support and
the offline product foundation are accepted. Final hosted verification exposed
a terminal shutdown race, now corrected through `GEX-HEALTH-006` with six
deterministic lifecycle regressions and 425 passing tests. The release evidence and remaining
external gates are recorded in [GEX-OFFLINE-001](work-packets/GEX-OFFLINE-001.md).

The September 13 follow-up confirmed that a focused strike table consumes
`Down` and `Enter` after `p` opens the replay picker. Existing direct-action
tests did not cover this keyboard-routing failure. The bounded repair and
real-keyboard acceptance are tracked in [GEX-UX-001](work-packets/GEX-UX-001.md).
The repair is merged and accepted: six keyboard regressions, independent
installed-wheel verification, four hosted checks and 431 tests on clean merged
main. This resolves the interaction defect, not real-user acceptance.

No credentialed provider observation, real-user activation study, customer
commitment or commercial pilot was performed. Databento remains
`live-uncertified`; predictive validity remains `unmeasured`. The next product
evidence remained observed use of the offline loop; these results did not
authorize broad feature expansion.

The [September 20 study build](studies/offline-first-use-2026-09-20.md) now freezes
the repaired wheel, runtime, synthetic inputs and scoring materials. Its
fresh-environment rehearsal and 435 source tests passed. Heading-link checks
protect documentation navigation; architecture/C4 and contributor guidance now
make diagram and document ownership explicit. These are preparation and
maintenance results, with participant acceptance still unmeasured.

The September 26 maintenance slice adds independently reasoned replay checks,
Linux/macOS build verification, bounded synthetic CI evidence and a preview
refresh tool. Visual review also corrects generated demo SVG layout and exposes
the onboarding picker's existing viewport in a taller capture.
[GEX-OFFLINE-002](work-packets/GEX-OFFLINE-002.md) owns the final test, package,
visual and hosted-check results. The September 20 study artifacts retain their
original identities; these changes do not re-identify that frozen build.

The follow-up [deployment and terminal review](deployment-ux-review.md) found
avoidable setup friction, a hidden replay selection and refresh-driven cursor
resets. [GEX-UX-002](work-packets/GEX-UX-002.md) implements a reviewed-wheel setup
bundle, persistent isolated offline launcher, smaller-window layout, focused
replay chooser and contextual help/details. The slice passed 479 local tests,
fresh offline installation, 18 installed-UI checks, and the four hosted
Ubuntu/macOS × Python 3.11/3.12 jobs. The packet and
[PR #31](https://github.com/zrack/gex-terminal/pull/31) own final checked-source
and merge evidence. These changes are separate from the prior version tag and
frozen study; participant acceptance remains unmeasured.

## Current state

| Area | Observed state | Limit |
| --- | --- | --- |
| Model and state | Contract-aware Black-76/Black-Scholes with separate OI, raw-volume and directionalized-volume paths | Numerical correctness does not establish dealer inventory or forecasting value |
| Replay and identity | Eleven bundled scenarios including NQ ×20 schema-v2; catalog identity, actual/fallback multipliers and accepted-event chronology are explicit | Synthetic fixtures do not establish provider support for ES or NQ |
| Research loop | Demo Lab, captured sessions, journals, experiments, model profiles, corpus registration, batch comparison and portable receipts | Strict identity/runtime compatibility and source-specific point-in-time gates; unkeyed hashes are not signatures |
| Wind Tunnel | Packaged browser surfaces, scenarios, expiry removal, comparison and fragility; explicit immutable demo/replay Terminal checkpoint; guided native captured-session inspection and prefix selection; self-contained save/open/export/reproduce receipts | Intake supports complete native captures within declared bounds; source rights and real-user input qualification remain external; no general CSV/provider import, live capture or synchronization; shocks freeze quantities and do not forecast future positions |
| Terminal | Essential columns at 100×32+, full-table view at 140×42; focused picker/help/details and strike selection retained across refresh | Not a mobile interface, screen-reader certification or unaided usability study |
| Preflight | Offline doctor checks package, resources, config, provider structure and temporary storage with text/JSON exit status | No live authentication, entitlements, SDK behavior or market-quality check |
| Distribution | Reviewed wheel, local setup handoff, optional platform-specific wheelhouse and disposable lifecycle checks | Python remains required; no signed native installer or customer-selected channel |
| Local launcher | Unified Terminal/Wind/Both starter, managed child-process lifetime, exact payload checks and separate research directory; `w` performs explicit checkpoint transfer | Combined launch alone coordinates processes, not market state; checkpoint services belong to their Terminal owner and stop with it; observed activation is still open |
| Local interfaces | Snapshot exports, static TradingView overlay and capability-protected Wind loopback HTTP service | No supported public SDK/REST/MCP contract, continuous chart synchronization or hosted platform |
| Support and lifecycle | Redacted diagnostics; verified owner-only backup/restore; whole-group retention bound to a verified backup and exact confirmation | POSIX safety support only; no general database, automatic migration or licensed-capture lifecycle claim |
| Product preparation | September study preserved; October guided-intake cohort freezes exact source/wheel/runtime/materials, with a separate participant-only delivery and blank recruitment templates | Zero observed participants; no activation, demand, price, margin, license or conversion measurement; personal records stay outside Git and shared kits |
| Live preparation | Strict local plan/result contracts bind a declared 12-slot ES population, policy/runtime identity and failed/missed attempts | No execution, report-byte authentication, complete-history proof or external authority |
| Live readiness | Databento uncertified; Tradovate/IBKR scaffolded; yfinance delayed | No supported recurring live operating envelope |

## Findings and repair evidence

The original reproductions and implementation evidence belong to the named
packets rather than being duplicated here.

| Finding | Status and acceptance evidence | Owner |
| --- | --- | --- |
| H1 — Instrument identity/multiplier provenance | Resolved: reject mislabeled legacy demos; bind catalog identity; expose actual versus configured fallback multipliers, including heterogeneous rows | [GEX-HEALTH-001](work-packets/GEX-HEALTH-001.md) |
| H2 — Invalid config/offline health | Resolved: finite/domain validation across config/CLI/UI and stale guards; injection explicitly replay/disconnected/simulated | [GEX-HEALTH-002](work-packets/GEX-HEALTH-002.md) |
| H3 — Replay writer contamination | Resolved: cancel and await prior writer before reset; full interactive CLI regressions for fixed/event clocks and failure | [GEX-HEALTH-003](work-packets/GEX-HEALTH-003.md) |
| H4 — Experiment metadata relabeling | Resolved: complete v2 identity before reproduction; legacy partial status; reject unknown/inconsistent fields and nonempty targets | [GEX-HEALTH-004](work-packets/GEX-HEALTH-004.md) |
| H5 — Rejected-input chronology | Resolved: analytical points follow accepted updates; raw input audit separated; snapshot/model time agree | [GEX-HEALTH-005](work-packets/GEX-HEALTH-005.md) |
| H6 — Clipped small terminal | Resolved: visibility checks at supported sizes, explicit minimum message below them and state-preserving resize | [GEX-INSTALL-001](work-packets/GEX-INSTALL-001.md) |
| H7 — Refresh after screen teardown | Resolved: screen-owned callbacks, exact-owner checks after both awaits, no cache/UI publication after quit/teardown; resize remains owner-bound behind overlays | [GEX-HEALTH-006](work-packets/GEX-HEALTH-006.md) |
| H8 — Replay picker keyboard routing | Resolved: dashboard-scoped priority keys, footer/table ownership and real-keyboard coverage for ES/NQ, overlays, cancellation, retries and source safeguards | [GEX-UX-001](work-packets/GEX-UX-001.md) |

These are scoped regression results, not a claim that the application has no
other defects. Source and tests were inspected together; runtime boundaries
remain explicit.

## Compatibility and remaining limits

- **Portable versus private:** Demo Lab copies its authorized synthetic source.
  Standalone experiments can still reference external private inputs; backing
  up their output directory does not preserve those external inputs or make
  the experiment shareable.
- **Runtime:** receipt compatibility is an explicit allowlist and also binds
  Python major/minor and dependency versions. Same-version hashes alone do not
  guarantee parity after a correctness change; reproduction compares results.
- **Repair identity:** the original `v0.5.0` tag/wheel does not include the later
  keyboard repair. Use the exact [study build record](studies/offline-first-use-2026-09-20.md);
  package version `0.5.0` alone is not its identity.
- **Corpus:** omitted `as_of` can be valid registration metadata, but corpus
  verification reports evaluation eligibility `not_assessed`. Empirical use
  requires the source-specific cutoff/availability gates in
  [Research Governance](research-governance.md).
- **Provider queue:** Databento #5 and #35 are closed after the merged offline
  repairs. Tradovate PR #10 remains unaccepted; its fixture assertion and
  unsupported access claims require contributor changes. Issue #4 remains
  open until actual sanitized demo/live Tradovate ES/NQ payloads establish
  mapping and availability; the ACK-frame repair does not satisfy that gate.
- **Customer/live gates:** prepared protocols are not observations. The
  [Product Validation](product-validation.md) kit and prepared
  [GEX-LIVE-002](work-packets/GEX-LIVE-002.md) packet do not authorize external
  commitments, credentials, retention or readiness promotion.

## Verification record

Each row identifies its own historical scope. The October assessment's focused
checks do not rerun or supersede a prior full-suite result, and neither is
evidence that a participant used the product successfully.

Local environment: macOS ARM64, CPython 3.12.13. Generated inputs and artifacts
are synthetic and retained in disposable directories outside the repository.
Package dependency downloads are not market-data connections.

| Check | Verified result | Boundary |
| --- | --- | --- |
| Correctness merged main | PRs #20–#24; clean main `2029f29` passed 344 tests and compilation; four hosted Python 3.11/3.12 checks passed per PR | Historical correctness baseline, not final release total |
| Portable-loop integration | Contributor passed 349 tests, numerical/offline-provider gates and fresh-wheel copied-pack reproduction | Twenty artifacts and five decision hashes; synthetic only |
| Cross-version pack | Actual 0.4.0 contributor receipt verified/reproduced under 0.5.0 with matching source/model/content | Same Python 3.12 and NumPy/Textual runtime; original tagged 0.4.0 legacy packs are not upgraded |
| Doctor contribution | 52 focused / 335 branch tests, distributions/Twine, isolated normal/invalid/missing-base checks | Branch baseline differs; final integrated total below |
| Compact terminal | Screenshots inspected at 140×42 and 80×24; visibility/resize regressions passed | Not a user study |
| Integrated release | PR #25 merged as `830d6a7`; clean pulled main passed 419 tests, compilation and 206 documentation links; numerical, property, offline-provider, fault and 500-contract performance gates passed | Offline implementation evidence only |
| Distribution lifecycle | Complete feature wheel passed build/Twine and 0.4.0 → 0.5.0 install/upgrade/corrupt-update/rollback/uninstall; all 14 research-file byte identities preserved | macOS ARM64/Python 3.12.13; no arbitrary interrupted-install guarantee |
| Hosted release checks | All four PR #25 Python 3.11/3.12 Linux checks passed, including full tests, fresh-wheel commands and recovery lifecycle | Hosted software verification, not live operation |
| Final lifecycle repair | PR #26 initially exposed the shutdown race on 3.12; 3.11 was fail-fast-cancelled. Independently reviewed repair and root integration each passed 425 tests | Initial green checkpoints do not erase the observed failure; final tag requires repaired-tree hosted/package checks |
| Independent installed wheel | Full command matrix passed in a fresh Python 3.14.4 environment; NQ identities, redacted support and private backup/restore verified | Additional command smoke only; full-suite baseline remains 3.11/3.12 |
| September 13 keyboard repair | PR #27 merged as `b5ecfb1`; 431 tests, compilation and documentation links passed on clean pulled main, after four hosted 3.11/3.12 checks and independent installed-wheel keyboard smoke | Exact repair evidence in GEX-UX-001; no new release tag, native-terminal accessibility or real-user study |
| Market Wind Tunnel and unified starter | Accepted browser scenario/reproduction and managed combined-launch slices; exact source, packaging and hosted gates are owned by [GEX-WIND-001](work-packets/GEX-WIND-001.md) and [GEX-START-001](work-packets/GEX-START-001.md) | Offline technical acceptance; unchanged version alone does not identify later source or establish observed use |
| Databento issue #35 | PR #36 merged; clean merged main passed 603 source tests after installed-wheel functional, parameter/state-machine and load verification; final hosted jobs passed | Exact environment, populations and software-only ceiling in [GEX-DATABENTO-035](work-packets/GEX-DATABENTO-035.md); no live readiness promotion |
| Tradovate ACK-frame repair | PR #38 merged as `a959272`; 614 source tests passed on clean merged main, with focused ACK/Tradovate regressions, model/offline-provider/fault and candidate-wheel checks; all eight final hosted jobs passed | [GEX-TRADOVATE-ACK-001](work-packets/GEX-TRADOVATE-ACK-001.md) owns exact evidence; #4 remains open and actual payload access is unverified |
| October 18 assessment | Main `6b5af41502e26351a70180d3144aeeec2b6023d6`, package `0.6.0`; 35 focused tests and seven public CLI smoke checks passed | Dated review of the pre-handoff tree, not a fresh full-suite run or verification of subsequent changes |
| Terminal checkpoint handoff | PR #40 merged as `cd81cc7`; 637 tests passed on clean merged main, including 23 new regressions, with installed-wheel/browser reproduction and all eight final hosted jobs | Exact immutable demo/replay capture only; [GEX-WIND-HANDOFF-001](work-packets/GEX-WIND-HANDOFF-001.md) owns acceptance; no live readiness or participant evidence |
| Guided intake and study preparation | PR #41 merged as `0dab6bb`; 673 tests passed on clean merged main, including 36 new regressions; all eight final hosted jobs passed; the separately frozen October kit has 86 verified files, reproducible wheel bytes, 23 preparation checks and 16 independent installed-wheel checks | [GEX-INTAKE-STUDY-001](work-packets/GEX-INTAKE-STUDY-001.md) and the [dated cohort record](studies/guided-intake-2026-10-18.md) bind exact identities; zero observed participants; #4 remains open |

The historical release closeout and annotated tag identify their released tree;
later PR and study records identify subsequent builds.
[GEX-OFFLINE-001](work-packets/GEX-OFFLINE-001.md) records its acceptance without
promoting the external gates. Follow [Contributing](../CONTRIBUTING.md) for repeatable commands,
[First Run](first-run.md) for installation, and the individual guides for
artifact contracts. Run review commands in new scratch directories so existing
research cannot be overwritten. No dependency vulnerability audit or external
penetration test is claimed.

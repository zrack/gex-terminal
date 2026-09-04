# Application State And Health Review

Reviewed September 4, 2026 for `0.5.0 — Offline Research Foundation`. This
document owns the dated state assessment and verification limits.
[Architecture](architecture.md) owns implementation structure;
[Roadmap](../ROADMAP.md) owns remaining work. Earlier assessments remain in Git.

## Assessment

The application is an offline research alpha with corrected result identity,
fail-closed configuration, isolated replay replacement and verifiable portable
research packs. All five P1 correctness repairs are merged. Compact-terminal
support and the offline product foundation are undergoing final integrated
release verification under [GEX-OFFLINE-001](work-packets/GEX-OFFLINE-001.md).

No credentialed provider observation, real-user activation study, customer
commitment or commercial pilot was performed. Databento remains
`live-uncertified`; predictive validity remains `unmeasured`. The next product
evidence is observed use of the offline loop, not another broad feature layer.

## Current state

| Area | Observed state | Limit |
| --- | --- | --- |
| Model and state | Contract-aware Black-76/Black-Scholes with separate OI, raw-volume and directionalized-volume paths | Numerical correctness does not establish dealer inventory or forecasting value |
| Replay and identity | Eleven bundled scenarios including NQ ×20 schema-v2; catalog identity, actual/fallback multipliers and accepted-event chronology are explicit | Synthetic fixtures do not establish provider support for ES or NQ |
| Research loop | Existing Demo Lab extended to a 20-file portable pack, input copy, three-model ladder and versioned receipt | Strict inventory/runtime compatibility; unkeyed hashes are not signatures |
| Terminal | Compact layout at 140×42+, larger view at 180×54; smaller sizes show guidance; resize preserves state | Not a mobile interface or unaided usability study |
| Preflight | Offline doctor checks package, resources, config, provider structure and temporary storage with text/JSON exit status | No live authentication, entitlements, SDK behavior or market-quality check |
| Distribution | Reviewed wheel path, cross-version pack check, lifecycle harness and guided journey | Customer distribution choice and observed activation remain open |
| Local launcher | Regular 0.5.0 wheel replaces the faulty editable install; version and doctor succeed | The original macOS hidden `.pth` condition is diagnosed, not claimed permanently fixed for editable installs |
| Support and lifecycle | Redacted diagnostics; verified owner-only backup/restore; whole-group retention bound to a verified backup and exact confirmation | POSIX safety support only; no general database, automatic migration or licensed-capture lifecycle claim |
| Product preparation | Study kit, matched paper concepts, scorecard, rights questions and scenario worksheet prepared | No demand, price, margin, license or conversion measurement |
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
| H6 — Clipped small terminal | Implemented: visibility checks at supported sizes, explicit minimum message below them and state-preserving resize | [GEX-INSTALL-001](work-packets/GEX-INSTALL-001.md) |

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
- **Corpus:** omitted `as_of` can be valid registration metadata, but corpus
  verification reports evaluation eligibility `not_assessed`. Empirical use
  requires the source-specific cutoff/availability gates in
  [Research Governance](research-governance.md).
- **Provider queue:** [Good First Issues](good-first-issues.md) records the
  September 4 issue/PR reconciliation. Tradovate PR #10 remains unaccepted; its
  fixture assertion and unsupported access claims require contributor changes.
- **Customer/live gates:** prepared protocols are not observations. The
  [Product Validation](product-validation.md) kit and prepared
  [GEX-LIVE-002](work-packets/GEX-LIVE-002.md) packet do not authorize external
  commitments, credentials, retention or readiness promotion.

## Verification record

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
| Integrated release branch | 419 tests, compilation and 202 local documentation links passed; numerical, property, offline-provider, fault and 500-contract performance gates passed | Offline implementation evidence only; hosted/merged-main closeout pending |
| Distribution lifecycle | Complete feature wheel passed build/Twine and 0.4.0 → 0.5.0 install/upgrade/corrupt-update/rollback/uninstall; all 14 research-file byte identities preserved | macOS ARM64/Python 3.12.13; no arbitrary interrupted-install guarantee |

The complete final release gate and clean merged-tree evidence must be recorded
before tagging. Follow [Contributing](../CONTRIBUTING.md) for repeatable commands,
[First Run](first-run.md) for installation, and the individual guides for
artifact contracts. Run review commands in new scratch directories so existing
research cannot be overwritten. No dependency vulnerability audit or external
penetration test is claimed.

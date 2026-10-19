# GEX-DATABENTO-TRIAL-001 — Historical Credit Trial Setup

Status: implemented and locally validated. ES and corrected NQ historical
acquisition and app replay have been observed. Follow-up raw-data reconciliation,
independent math, sparse-side displays, pricing disclosures and scenario
reproduction pass. The complete regression suite passes all 836 tests.

Authority: the maintainer asked to try Databento's free credits and be walked
through setting up ES/NQ options in the app. This authorizes private historical
testing within available credits, not a live subscription or paid overage.

Rigor: L3 for credential and licensed-data handling. Acquisition/conversion lives
in checkout setup scripts; a small adapter extension preserves the observed
underlying quote source in IV provenance. Follow-up fixes preserve exercise
classification and distinguish unavailable side metrics in the existing model
and display paths. Normalized schema versions, live subscriptions, provider
readiness, pricing formulas, frozen study artifacts, release identity and corpus
membership are unchanged.

Scope:

- Hidden local key entry in an ignored owner-only file; no credentials in chat,
  shell arguments, reports, fixtures or logs.
- A completed 60-second ES/NQ quarterly-parent sample, historical API only,
  cost preview before data I/O, explicit download acknowledgement and declared
  remaining credits; refuse estimates exceeding the configured ceiling.
- Underlying sampling defaults to one-second interval-end BBO midpoints; option
  trades retain full detail. Raw last-sale timestamps cannot backdate a BBO
  snapshot into an earlier option trade.
- Private raw files and accurate subset/quantity provenance; no retries,
  overwrites, OI claims, redistribution or live certification.
- Local multi-schema bridge to the existing adapter/consumer/model and complete
  captured-session format, usable in Terminal and Wind Tunnel.

Acceptance evidence: focused synthetic privacy/budget/order/mapping and capture
round-trip tests; existing Databento/capture contracts; compile and documentation
checks. Credentialed acquisition is recorded separately from synthetic offline
verification and does not certify the live streaming service.

Observed local verification on October 19, 2026:

- All 17 new setup/replay test methods passed, including ES/NQ production snapshot
  and Wind Tunnel checkpoint round trips, binary DBN/ZSTD input, limits,
  privacy, exact quote/download request parity and refusal paths.
- The documented source CLI replay/export produced ES with multiplier 50 and
  NQ with multiplier 20 from synthetic inputs.
- The 12-case Databento offline certification passed with
  `live_transport_certified=false`; documentation-link and compile checks passed.
- The initial broad run could not bind localhost sockets in the sandbox. The
  subsequent run with local loopback permission passed all 793 tests in 106.124
  seconds. Its local log is `/tmp/gex-databento-trial-tests-localhost.log`.

Subsequent NQ correction and actual historical evidence on October 19, 2026:

- The operator's NQ command stopped at 60,000 MBP-1 records. A metadata-only
  count reported 704,323 underlying records for the 62-second quote window.
  The previous partial files were preserved.
- The revised helper quoted $0.006505 for its BBO-based NQ plan and completed
  acquisition within the operator's $1 ceiling and declared credit balance.
  That number is a request estimate, not a verified provider billing receipt.
- The actual download contains 6,615 definitions, 62 BBO snapshots and two
  option trades. The replay retained 728 matching definition records and both
  trades, with no fallback IV, stale/future quote, or underlying-ID mismatch.
- The resulting 64-event normalized capture passed integrity verification,
  source CLI snapshot export with NQ multiplier 20, immutable Wind Tunnel
  checkpoint export, and guided local-session intake/checkpoint validation.
- New failures report safe request stage/schema/status and retain private stop
  manifests. A new `-bbo-1s` output directory avoids deleting or overwriting
  the original sample. Focused privacy, BBO timing and adapter checks passed;
  the full corrected-tree suite passed all 804 tests in 105.946 seconds with
  local loopback permission. Its local log is `/tmp/gex-nq-bbo-full.log`.

Actual payloads and derivatives are private in ignored `historical_sessions/`.
This small quarterly/trade-volume sample does not establish a full options
chain, OI, wire-arrival reconstruction, live certification or predictive validity.

Follow-up data validation and corrections on October 19, 2026:

- Reconciled raw identities, timestamps, quantities, multipliers and captured
  events. An independent scalar oracle matches the current IV, gamma and GEX
  calculations, including Wind Tunnel zero-shock and scenario reproduction.
- Corrected calls-only/puts-only labels, nullable absent-side walls and undefined
  ratios across Terminal, exports, overlays, saved sessions and comparisons.
- Preserved native Databento CFI exercise metadata through state and checkpoints.
  American contracts show the European-formula approximation and unmeasured
  error; original captures without the metadata remain explicitly unknown.
  Pricing formulas, configured rates and timing assumptions are visible.
- All 836 regression tests passed, including 32 new sparse-side and pricing
  provenance tests. Actual saved ES/NQ validation and 17 browser checks passed
  without provider requests or credits. Original captures remain unchanged.
- Local pre-PR compilation, numerical evidence, model properties, provider-fault
  certification, bounded performance, wheel/sdist build and Twine checks passed.
  Hosted CI and merge state are recorded on the pull request.

Recovery: remove these checkout scripts/docs or revert their patch. Local keys,
raw data and captures remain ignored private operator files and are never
deleted automatically. This slice creates no tag or release and does not merge
itself into protected main.

Operator guide: [Databento Credit Trial](../databento-credit-trial.md).

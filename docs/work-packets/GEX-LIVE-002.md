# GEX-LIVE-002 — Prospective Recurring ES Observation

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: prepared_awaiting_external_authority
packet_owner: project maintainer
created: 2026-09-04
execution_authorized: false
provider_readiness: live-uncertified
```

## Purpose and evidence ceiling

Prepare the Phase 2 recurrence gate before examining live results. This packet
does not authorize credentials, paid access, network observations, licensed
retention or registry promotion. The proposed population and thresholds below
are repository choices, not statistically established reliability guarantees.
An owner must accept and freeze them before the first observation; amendments
after inspection create a new population identity with an explained reason.

## Required owner decisions before execution

- Named operator/reviewer and read-only observation authority.
- Exact account entitlement scope, provider/SDK/application/Python versions,
  environment and symbol mapping, recorded without secret/account values.
- ES canonical multiplier 50 and policy ID `databento-es-prelive-v1`
  (`ES_PRELIVE_V1`) selected from the canonical
  [certification policy](../../gex_terminal/databento_certification_policy.py).
  Preserve that policy's full thresholds/digest beside every observation;
  this packet does not replace or weaken its quantitative gates. The offline
  plan contract in `GEX-LIVE-PREP-001` owns canonical policy/population hashing
  and the exact-run evidence envelope; freeze its validated plan before I/O.
- Authorized dates/windows, clock/timezone source and stale-response procedure.
- Approved rights, storage, report retention and deletion decisions. Raw capture
  is off unless a separate valid capture policy expressly authorizes it.
  Capture authority and research eligibility remain separate.

No execution should be scheduled until every decision is recorded. An unset
field is a blocker, not permission to use environment defaults.

## Proposed population and coverage

Predeclare 12 bounded 20-minute observations across at least four distinct
trading dates: three regular-session open windows, three midday, three close,
and three Globex windows. The operator supplies exact dates and UTC start/end
times from the applicable current exchange calendar before freezing the plan.
Include both an ordinary date and a scheduled-event date if rights and operator
availability allow; otherwise narrow the accepted envelope and disclose the gap.
No event/volatility regime is claimed from its calendar label alone.

Each attempt gets a stable run ID, planned window, actual start/stop, source
versions, policy identity, redacted outcome and report digest. A missed window,
authentication/entitlement failure, empty chain or operator interruption remains
in the planned population. A replacement run is linked to the failed attempt,
not substituted for it. Keep a population manifest and hashes outside the
public repo if even timing/diagnostics have restricted use.

## Failure and restart rules

- Any wrong symbol/multiplier, silent fallback, unexplained sequence loss,
  stale-as-live state or cross-contract contamination stops the run and blocks
  promotion. Retain the redacted failure and repair evidence.
  Numeric gaps in trade-schema venue sequences alone are descriptive, not
  proof of loss: apply the canonical policy's flag/order semantics and retain
  the evidence for an actual integrity failure.
- Authentication, entitlement, policy, payload/coverage, temporal, lifecycle,
  operator and environment failures are distinct categories. An infrastructure
  cause does not turn a failure into a success.
- All 12 planned observations must pass their exact-run policy; zero failures
  is required for this initial narrow promotion proposal. A failed population
  remains failed. After a documented repair and review, preregister a fresh
  complete population rather than restarting a success counter silently.
  Every later population and promotion record must retain immutable lineage
  and disclose all prior populations/failures, not just the successful one.
- On two distinct dates, perform a separately authorized clean stop/restart
  observation. Confirm bounded shutdown, fresh resubscription, a new accepted
  state and no stale carryover. Retain both process lifetimes.
- Do not intentionally disrupt a provider/network without separate authority.
  Unobserved disconnect/reconnect behavior remains unclaimed; scripted fault
  evidence cannot replace it. Limit the supported operator procedure accordingly.

## Promotion review

The reviewer checks the full planned population, including failed/missed
attempts, the quantitative policy results, restart evidence, rights/retention
compliance, and any unsupported session/regime. OI availability and IV source
coverage must remain explicit; no OI may be inferred from trades. If the desired
job needs OI and the authorized feed does not establish it, narrow the job or
stop; do not relabel the evidence.

A prospective promotion decision must bind population identity, exact accepted
application/provider/SDK versions, ES scope, entitlement assumptions, session
windows, fallback policy, operator response and limitations. Route registry,
documentation and regression-test changes together as a separate reviewed L3
change. A report or connection cannot promote itself. Twelve zero-failure
windows cannot establish a general failure rate or reliability guarantee;
promotion names only the observed envelope, and all earlier failures remain
part of the disclosure.

NQ requires a separate population and its own canonical policy/multiplier.
Neither an ES pass nor a synthetic NQ fixture certifies NQ. No result from this
packet establishes model predictiveness, execution quality or profitability.

## Current evidence

Preparation only. Zero live observations executed under this packet. Provider
readiness remains `live-uncertified`; predictive validity remains `unmeasured`.

# Roadmap

This file contains planned and deferred work only. Shipped work belongs in
[CHANGELOG.md](CHANGELOG.md), the current system belongs in
[Architecture](docs/architecture.md), durable outcomes belong in
[Product Vision](docs/product-vision.md), and the evidence behind the strategy
belongs in [Competitive Landscape](docs/market-analysis.md).

Priorities reviewed October 18, 2026 against the current `0.6.0` source and
the refreshed [Competitive Landscape](docs/market-analysis.md) and
[Application Review](docs/application-review.md). The maintainer authorized
the checkpoint handoff into Wind Tunnel, followed by guided local-session
intake and a separately frozen current-build study kit, with regression coverage,
documentation and commit/merge. The implemented demo/replay handoff and its
integration gates belong to [GEX-WIND-HANDOFF-001](docs/work-packets/GEX-WIND-HANDOFF-001.md);
it is not repeated as future feature work here. [Wind Tunnel](docs/wind-tunnel.md)
owns its user contract. [GEX-INTAKE-STUDY-001](docs/work-packets/GEX-INTAKE-STUDY-001.md)
owns intake and study preparation. Broader features below remain demand-gated;
[Changelog](CHANGELOG.md) and the routed work packet own shipped acceptance.

## Current Work Order

Defer broad feature expansion until the chosen research job has been observed
with real users. Correctness regressions still interrupt product work. Permit
bounded engineering that removes a concrete obstacle to testing that job. The
authorized guided intake and current-build study preparation remove that testing
obstacle; broader feature candidates still need their own owner decision.

Prepared protocols are ready to use, but preparation is not a passed gate.
Preserve the exact repaired build and frozen September 20 materials identified
through [Study Build](docs/study-build.md). A study of the current starter,
terminal, Wind Tunnel and checkpoint workflow needs a new exact build,
materials and cohort identity. Neither the old tag nor an unchanged package
version identifies the current implementation; never rewrite historical
results to imply that the newer experience was observed.

| Order | Work | Why now | Completion evidence |
| --- | --- | --- | --- |
| 1 — Observe the current workflow | Run six observed offline task sessions on the new guided-intake study kit, including local session intake and the explicit checkpoint handoff | Tests cannot establish whether a non-developer understands or trusts the result | Unaided outcomes, timing, non-starts, intervention log, recurring job and reproduced trust defects |
| 2 — Qualify user input and the offer | Test one rights-authorized historical/capture path, recruit design partners, compare concepts and obtain price/cost evidence | The research job and commercial path can be tested without recurring live operation | Phase 0 gates plus input lineage, quality limits, repeat use and a lawful historical research offer |
| 3 — Choose the narrow beta | Enter the historical-research branch of Phase 3 when its gates pass; run live ES only under separately accepted authority | Historical research and a live cockpit have different operating obligations | Branch-specific activation, use, replacement, trust and product-path decision |

Two tracks can progress alongside that order:

- **Customer evidence — Phase 0:** adapt the prepared [Product Validation](docs/product-validation.md)
  protocol to the named current-build study while retaining the old materials;
  use comparable paper concepts, scorecard, rights questions and cost worksheet. Recruitment,
  interviews, commitments, and provider answers require real participants or
  owners; a written protocol does not complete those gates.
- **Live evidence — Phase 2:** review the prepared [GEX-LIVE-002](docs/work-packets/GEX-LIVE-002.md)
  recurrence criteria and run
  bounded ES observations when credentials, entitlements, and data-use authority
  are available. NQ needs independent evidence.

Keep each engineering slice reviewable and mergeable on its own. Dependent
slices land in order; independent work may proceed in isolated contributor
branches, with integration checks before each merge. This bounded parallelism
implements the maintainer's September 4 authorization to complete all offline
priorities. A confirmed correctness issue can interrupt feature work; an
unvalidated feature request needs an explicit owner decision.

Provider queue reconciliation is recorded in [Good First Issues](docs/good-first-issues.md).
Databento issues #5 and #35 are closed after the merged fixture/provider
repairs. Tradovate PR #10 remains unaccepted and needs contributor changes and
observed provenance. **Keep issue #4 open until actual sanitized demo/live
Tradovate ES/NQ payloads establish its mapping and availability claims.** The
merged ACK-frame repair is offline behavior evidence and does not close that
payload gate. Do not duplicate completed work or treat an open contribution as
accepted/live evidence.

## Product Destination

Build the auditable, local-first ES/NQ market-structure instrument: a user can
preflight a source, inspect a current structural proxy, trace it to contracts
and assumptions, compare credible position models on identical inputs, save the
receipt, and replay the later outcome.

The roadmap does not assume that GEX predicts price. It separates seven claims:

1. the software path behaves as specified;
2. a provider supplied usable data in a declared window;
3. that behavior recurs within a defined operating envelope;
4. a structural proxy is descriptively stable or informative;
5. an alert has out-of-sample predictive value;
6. an execution rule survives timing, fills, and costs; and
7. a commercial product retains customers at viable economics.

Evidence at one level does not promote the next.

## Strategic Choice

The working lead hypothesis is a packaged **bring-your-own-data professional
desktop** built around model provenance, dissent, replay, and evidence receipts.
It is not yet a chosen commercial product. The strongest recurring-job
hypothesis is: inspect what produced a structural read, identify assumptions
that change it, and reproduce the explanation later. Native futures coverage,
Black-76, scenario charts, APIs and receipts individually already have market
substitutes. The MIT research kernel remains useful and open; a paid layer, if
customer evidence supports one, sells a completed workflow, convenience,
supported inputs, automation, integrations, governed storage and support.

The strongest alternative is a **hosted ES/NQ tactical cockpit** with simple
levels, explanations, push alerts, and chart delivery. It has a clearer retail
promise but requires substantially stronger data licensing, uptime, support,
mobile UX, and unit economics. Phase 0 decides whether that alternative earns a
live comparator pilot. Phase 3 is the authoritative product-path decision for
the branch actually tested; an authorized historical-research beta can reach
that decision without passing a live certification gate. It cannot establish
that a live cockpit is supported or that an unrun alternative is inferior.

## Priority And Gate Map

Phases describe dependencies, not delivery dates. Phase 0 and bounded offline
work can overlap. Historical research follows 0 → 1 → 3 (research) → 5;
live delivery additionally requires Phase 2 before 3 (live). Phase 4 evidence
can progress alongside either branch when its source-specific rights and
point-in-time gates pass. A phase advances on its exit evidence.

| Phase | Outcome | Can proceed without live data? | Primary gate |
| --- | --- | ---: | --- |
| 0 — Now | Prove the customer wedge and qualify or retire the hosted alternative | Yes | Repeated user job, design partners, data-rights path, and paid-pilot intent |
| 1 — Acceptance remaining | Validate clean-machine use of the shipped offline foundation | Yes, with participants | Observed activation and evidence-backed distribution/support choice |
| 2 — Parallel external gate | Certify one narrow recurring ES/Databento operating envelope | No | Credential, entitlement, capture authority, exact-run evidence, and predeclared recurrence |
| 3 | Run a design-partner historical-research or certified-live beta | Yes for authorized historical research | Branch-specific activation, weekly use, workflow replacement, and no severe trust defects |
| 4 — Evidence track | Build the governed evidence moat | Yes with authorized point-in-time history | Licensed corpus, preregistered evaluation, reproducibility, and appropriately narrow claims |
| 5 — Commercial track | Establish a paid descriptive-tool beta for the accepted Phase 3 branch | Yes for the historical offer | Distribution/legal readiness, retention, support load, and positive unit economics; predictive success is not a prerequisite |
| 6 | Expand from proven demand | Depends | Independent symbol/provider evidence and demonstrated user demand |

The recommended counts and thresholds below are hypotheses to predeclare in a
work packet. They are not existing measurements and can be changed before data
collection with a recorded reason.

## Prioritized Feature Candidates

The checkpoint handoff is implemented in its bounded demo/replay scope; its
usage and evidence belong to the guide and work packet. The remaining items
below are hypotheses ordered by dependency and the inspected workflow gaps,
not measured demand, promised delivery dates, estimated returns or current
implementation authority. Reuse existing research, export and lifecycle
capabilities before adding parallel systems.

| Priority | Candidate | Acceptance or demand gate |
| --- | --- | --- |
| P1 | Bring your own session | One supported normalized capture/historical format, authorized local intake, source lineage, visible missing/fallback fields and a user completing the named investigation |
| P1 | Chain health and IV initialization | Distinguish stream health from per-option IV/quote age; expose coverage, spreads, fallback share and exclusions; route provider quote bootstrap and IV policy separately |
| P1 | Explain this change | Reconcile matched results to contract, expiry, quantity, IV/time/price and assumption changes; expose interactions and describe model-output effects without market-causation claims |
| P1 | Preserve and compare builds | Retain the executable environment for an old receipt; separately identify original-model reproduction and intentional current-model restatement; fail clearly if unavailable |
| P1 | Contract/session conventions | Declare exercise style, expiry timezone, session/holiday rules, futures linkage and supported approximations; validate authoritative metadata independently |
| P2 | Daily research review | Assemble existing journal/corpus tools into a repeated hypothesis → scenario → later review loop; retain null, failed-data and unresolved cases |
| P2 | Skew and term-structure stresses | Require usable IV inputs and an explicit surface policy; distinguish observed and assumed regions before moving beyond uniform IV shifts |
| P2 | Quality-aware alerts and one chart handoff | Require observed workflow demand and recurring live scope for live alerts; existing static TradingView export is not a new feature |
| P2/P3 | Small SDK/read-only API, then MCP | Demonstrated developer job and versioned domain semantics; the internal Wind loopback service is a starting point, not a supported public API |
| P3 | Native-versus-proxy comparison | Additional licensed chains, aligned cutoffs and visible basis/model differences; do not assume native inputs predict better |
| P3 | Selected higher Greeks or portfolio P&L | Repeated user task, reliable inputs, contract conventions and independent numerical gates; broad portfolio management requires a separate product choice |

Artifact-grounded assistance remains later work: exact-input citations,
abstention and evidence-ceiling enforcement must precede a natural-language
interface. Generalized AI trade calls, broad symbol/provider growth and
platform breadth do not advance merely because competitors advertise them.

## Phase 0 — Prove The Wedge

**Purpose:** determine whether a recurring job is valuable enough to build
around and whether the hosted alternative deserves a later live pilot. The
local research instrument remains the low-regret lead through Phase 1; this
phase does not make the final product-path decision.

### Questions to answer

- Does the strongest user want to interrogate and reproduce a structural model,
  or mainly want trusted ES/NQ levels delivered with minimal effort?
- Will that user connect an existing provider account, or do they require data
  bundled into the product?
- Which existing manual step or paid tool would the product replace?
- How much setup, model control, and uncertainty will the user tolerate?
- Is the buying unit an individual trader, a quantitative researcher, a small
  desk, or a developer team?
- Do provider terms permit the proposed display, retention, derived output,
  support, and commercial use?

### Work

Use [Product Validation](docs/product-validation.md) as the canonical study kit.
The following are collection and decision obligations, not another request to
rebuild its templates or concepts.

1. Recruit 12–15 interview candidates split between quantitative/developer
   users and advanced ES/NQ traders. Treat existing personas as hypotheses.
2. Freeze a separately identified current-build study and run at least six
   observed task sessions using authorized demo, replay or historical data.
   Ask users to reach a trusted view, explain one level, compare models, save a
   receipt, and replay the session without developer help.
3. Test the prepared comparable-fidelity product concepts:
   - professional local instrument: Today, Explain, Compare, Replay, Review;
   - hosted tactical cockpit: current levels, simple explanation, alert, and
     chart delivery.
4. Record task completion, time to insight, trust questions, install tolerance,
   existing data accounts, workflow replacement, and price reaction.
5. Obtain written answers for the prepared provider/data-rights matrix covering personal and professional
   use, non-display calculation, local retention, derived display, external
   distribution, support access, and termination obligations.
6. Populate and challenge the first-year economics worksheet for bring-your-own
   data, bundled data, and a developer/support product using real quotes and
   observed support effort. Keep exchange fees and support time explicit.

### Exit gate

- Five users commit to a design-partner beta with a named recurring job.
- At least three have legitimate access to the selected historical inputs or,
  for a live offer, will connect an entitled existing data account. Record the
  actual branch; historical access does not establish live entitlements.
- At least two accept a defined paid-pilot offer at a tested price, subject to
  the product and commercial terms becoming available.
- The common recurring job and initial buying-unit hypothesis are explicit;
  feature enthusiasm alone is insufficient.
- The bring-your-own-data lead has a written rights path and plausible unit
  economics.
- The hosted alternative is either retired or qualifies for the Phase 3
  comparator with named users, a rights-feasible delivery method, and explicit
  reasons it could outperform the lead.

### Redirect rules

- If traders want delivery but will not bring data, do not build the hosted
  comparator until commercial data rights and margin are known.
- If researchers value the engine but not a desktop workflow, redirect toward
  a stable SDK plus paid integration/certification support.
- If neither group identifies a recurring job or replacement, stop product
  expansion and keep the project an open research workbench.

## Phase 1 — Distributable Research Foundation

**Purpose:** make the existing offline capability installable, coherent, and
supportable before live beta risk is added. This foundation remains useful as
the user-facing local product or as the inspectable operator/research layer
behind a later hosted product.

The repository-owned 1A–1D work is recorded in the release packets and
[Changelog](CHANGELOG.md), not repeated as an open implementation checklist.
Current command and compatibility contracts live in [First Run](docs/first-run.md),
[Doctor](docs/doctor.md), [Demo Lab](docs/demo-lab.md) and
[Local Support](docs/local-support.md).

### Remaining acceptance

- Preserve the frozen [study build](docs/study-build.md) and create a new exact
  build/materials/cohort record for the current starter, terminal and Wind
  workflow using the [Product Validation](docs/product-validation.md) scoring
  approach. Record the actual participant environment, assistance, refusals
  and non-starts. Treat subsequent build changes as separately identified
  observations; regression tests are not unaided user acceptance.
- Observe a new user installing without a checkout, reaching a correct replay
  insight in under ten minutes, and completing the scoped loop in under fifteen
  minutes without developer help. These are proposed study thresholds, not
  existing measurements. Record failures and assisted attempts.
- Select the commercial distribution channel and supported customer platform
  from Phase 0 evidence. A tested wheel is the technical baseline, not that
  product decision. Additional installers, automatic updating or a desktop
  redesign require observed demand and a new packet.
- Confirm that the supported file-based lifecycle and environment-based
  credential procedure fit the selected beta. A platform credential-store
  implementation, licensed captures/session-store lifecycle, database or
  generalized migration framework is a separately routed need, not implied
  support for every local file.

Phase 1's engineering acceptance does not complete its real-user acceptance.
Close the phase only after those observations and the scoped distribution/
support decision; retain the external Phase 2 live gate independently.

## Phase 2 — Narrow Live ES Certification

**Purpose:** establish a bounded, recurring live operating envelope before
asking design partners to depend on the product.

This phase requires explicit credential, entitlement, data-owner, retention,
and research authority. It can run in parallel with Phase 1 but cannot be
declared complete from offline evidence.

### Work

1. Route the exact-run authority and select the canonical ES multiplier,
   versioned policy, credential/entitlement scope, and declared read-only
   observation window.
2. Before running or reviewing the first observation, accept and freeze the
   prepared [GEX-LIVE-002](docs/work-packets/GEX-LIVE-002.md) population, exact
   windows, failure tolerance, retention and promotion logic. Preparation does
   not supply execution authority.
3. Run the existing `databento-certify` path and retain redacted successes and
   failures. Classify authentication, entitlement, coverage, payload, temporal,
   lifecycle, and policy failures separately.
4. Measure actual chain breadth, freshness, event ordering, IV path, OI state,
   restart behavior, shutdown, and any observed disconnect/recovery behavior.
5. Add watchdog, restart recovery, state resynchronization, and visible degraded
   modes only where observed evidence identifies the need.
6. Define the exact supported symbol, session, provider version, configuration,
   entitlement scope, fallback policy, and operator response for the first beta.
7. Decide separately whether any live capture may be retained for research. A
   provider connection does not grant capture or redistribution rights.
8. After the recurrence gate passes, route a versioned readiness-promotion
   decision that binds the accepted observation population, policy identity,
   provider and SDK versions, environment, supported scope, and unresolved
   limitations. Update the provider registry, documentation, and regression
   tests together; a passing certification report cannot promote readiness by
   itself.

### Exit gate

- A redacted exact-run report passes the versioned ES policy for its declared
  environment and window.
- Recurring observations satisfy the predeclared promotion rule; failures are
  retained and explained rather than removed from the population.
- No silent fallback, stale state, wrong multiplier, cross-contract
  contamination, or unexplained loss is observed in the accepted envelope.
- Failure and restart behavior have bounded evidence. An unobserved reconnect
  remains unclaimed.
- A reviewed promotion record links the accepted recurrence evidence to the
  exact registry, documentation, and test changes that establish the new
  readiness state.
- `live-certified` names the exact scope and unresolved limitations. It does
  not imply provider-wide reliability, predictive value, execution quality, or
  profitability.

### Stop conditions

- If required OI, IV, or chain coverage cannot support the selected job, narrow
  the job or change the source; do not weaken the evidence label.
- If licensing prohibits the needed live use, retain offline certification and
  stop that live commercial path until a lawful alternative exists. A different
  authorized historical offer must satisfy its own rights and beta gates.
- If recurring reliability cannot be demonstrated, do not expose the path as a
  supported live beta.

## Phase 3 — Design-Partner Workflow Beta

**Purpose:** determine whether supported inputs become a repeated user
workflow. Select and declare one branch before recruiting or measuring the
beta. Both require Phase 0 and observed Phase 1 acceptance:

- **Historical research:** authorized historical inputs, explicit quality and
  point-in-time limits, a complete checkpoint → inspect → stress → reproduce →
  review workflow, and retained environment/input identity. Recurring live
  certification is not an entry requirement.
- **Live cockpit:** the accepted Phase 2 operating envelope in addition to
  the workflow, recovery and user commitments below. Historical beta success
  cannot waive that gate.

### Work

- Before onboarding a design partner, establish a signed beta agreement,
  privacy notice, explicit consent for any optional telemetry, data-handling promises,
  risk disclaimer, security/vulnerability path, support limits, and incident
  contact. Phase 5 can harden these for paid scale; it cannot introduce them
  after beta use begins.
- Deliver the branch's primary workflows: inspect/Today, Explain, Compare,
  Replay and Review. Historical research must accept the selected user input
  and preserve an immutable checkpoint; Review can begin with daily evidence
  packs. Bundled synthetic examples alone do not establish recurring value.
- Show OI, raw-volume, and directionalized-volume agreement or dissent without
  blending their quantities.
- For a live branch, add local rule-based alerts that carry provider, model, as-of, quality, and
  readiness provenance. A degraded feed suppresses or clearly downgrades an
  alert according to a predeclared rule.
- Build one integration only if Phase 0/observed use identifies it as necessary.
  Prefer a local file or webhook/chart bridge before another charting surface.
- For live delivery, add background operation, bounded recovery, user-visible
  incident state and redacted diagnostics. Historical research instead needs
  reliable local input, save/open and fresh-process reproduction paths.
- Measure activation and workflow use through observed sessions and weekly
  reviews first. If needed, add opt-in, privacy-safe product analytics;
  never collect raw market data, credentials, private research, or trade/account
  activity by default.
- If Phase 0 keeps the hosted alternative viable and written data rights permit
  it, run a parallel four-week concierge or simulated-delivery cockpit pilot
  with a comparable cohort and the same activation, repeated-use, replacement,
  and willingness-to-pay measures. Do not centralize raw licensed data merely
  to run the comparison.
- Run structured weekly reviews with design partners and preserve requested
  features separately from observed workflow failures.

### Exit gate

- Every participant has the applicable beta agreement; telemetry consent is
  required only when optional telemetry is enabled. Non-consenting users can
  participate with observed sessions and reviews. Support, incident, security,
  risk, and data-handling commitments were usable throughout the pilot.
- At least five design partners use the product weekly for four consecutive
  weeks.
- At least 80% install and reach the selected branch's supported source without
  developer intervention.
- Median launch-to-trusted-view is under five minutes after setup: a selected
  historical checkpoint for research, or a live view within accepted scope.
- At least three users say it replaced a named manual step or paid-tool
  workflow and demonstrate that replacement during observation.
- At least two users agree to a paid beta for the same defined product.
- No unresolved high-severity defect can misstate source, freshness, contract,
  model, or recovery state.

### Product decision

Record whether the accepted local offer is historical research or live
delivery. Its commercial offer cannot imply capabilities of the other branch.
If the hosted-cockpit pilot qualified and ran, compare its results with the
local beta while disclosing different data/operating scope. Choose the hosted
path only if its activation, four-week retention,
and willingness to pay are materially stronger and the data-rights economics
remain viable. Continue locally only when the local beta meets its own gates.
If Phase 0 retired the hosted alternative or its rights gate prevented a pilot,
decide between continuing the validated local product and narrowing/stopping;
do not assume evidence from an unrun comparison.

- **Local wins:** retain the current product vision and use the local-path
  commercial offer in Phase 5.
- **Hosted wins:** stop before commercial build-out, update the product vision
  and this roadmap, and route a hosted architecture/data-rights/privacy/support
  packet. The Phase 5 local offer does not apply until it is replaced by an
  accepted hosted plan.
- **Inconclusive:** extend or narrow the beta; do not start commercial scale
  work merely to force a decision.

## Phase 4 — Governed Evidence Moat

**Purpose:** learn what the models describe and whether any narrow outcome claim
survives point-in-time evaluation.

Rights-authorized historical research can begin without Phase 2 when the
source's retention, derived-use and point-in-time gates pass. Live collection
can begin during Phase 2 only after the applicable capture gate passes. This
evidence track can continue alongside Phase 5. A paid
descriptive research tool does not require a successful predictive study;
predictive or execution claims do require their corresponding evidence.

### Work

- Build a licensed corpus spanning volatility, expiry, event, overnight, trend,
  range, and data-quality regimes.
- Add an indexed catalog only if observed search or scale needs exceed the
  existing stores. Keep it rebuildable from canonical artifacts and test any
  required migrations, backup/restore, retention, and deletion separately.
- Register immutable train, calibration, and untouched test identities before
  evaluating outcomes.
- Apply the [Research Governance](docs/research-governance.md) distinction
  between source registration and point-in-time evaluation eligibility. Prove
  source-specific availability at the declared cutoff before empirical use;
  corpus integrity alone cannot establish that eligibility.
- Externally sign or anchor corpus and manifest identities. Existing unkeyed
  hashes establish internal consistency, not source authenticity or historical
  immutability.
- Compare OI, raw-volume, and directionalized-volume models on identical
  sessions. Add a licensed participant-attribution model only if its fields and
  rights establish the claimed semantics.
- Predeclare horizons, coverage floors, costs, missing-data treatment,
  multiplicity controls, and promotion criteria.
- Publish descriptive stability and disagreement first. Preserve null,
  negative, unresolved, and failed-data results.
- Distinguish best favorable excursion, adverse excursion, fixed-horizon move,
  rule-based execution, and account return.

### Exit gate

- A clean machine reproduces every published artifact from authorized inputs
  and registered profiles.
- The untouched test period remains untouched until the declared decision
  point; all model changes after inspection receive a new evaluation identity.
- Coverage and statistical adequacy are reported before interpretation.
- Claims are promoted only to the narrow level supported by the evidence.
- If no predictive edge survives, the product remains an explainable
  market-structure instrument and does not become a signal service.

## Phase 5 — Paid Commercial Beta

**Purpose:** test whether product value exceeds distribution, data, and support
costs without weakening the evidence contract.

Entry requires the accepted Phase 3 product decision, the supported inputs and
workflow for that branch, and the commercial requirements below. A historical
research or developer-support offer can enter without recurring live
certification; it must have an authorized input/rights path and cannot market
live support. A live offer additionally requires the accepted Phase 2 scope.
Phase 4 may still be in progress; its unmeasured outcomes remain unclaimed.

### Local-path offer hypothesis

This offer applies only if the Phase 3 decision selects the local professional
product. A hosted decision requires a replacement commercial plan before this
phase begins.

- Keep the MIT offline research kernel available.
- Test paid value in guided setup, supported historical investigation,
  automation/integration, governed local evidence storage, reproducibility,
  updates and support. Signed distribution or supported live operation/alerts
  enter the offer only when demand and their separate acceptance gates pass.
- Use bring-your-own credentials first. Treat bundled or hosted data as a
  separate business decision requiring written provider and exchange authority.
- Do not make previously MIT-licensed code scarce retroactively; any future
  proprietary module needs a deliberate boundary and user-visible value.

### Work

- Convert the beta agreement, privacy/telemetry notice, data-handling promises,
  support limits, incident process, and risk disclaimer into production-facing
  commercial terms; add refunds and vendor obligations and obtain the
  appropriate professional review.
- Add payment and entitlement only after Phase 0 and Phase 3 price evidence.
- Operate the release, update/rollback, support, and local-data lifecycle accepted
  in Phase 1; harden signing, channel access, vulnerability response, and incident
  operations for the selected commercial offer.
- Measure activation, active use, retention, cancellation reason, support time,
  infrastructure, vendor fees, payment costs, and refunds.
- Keep marketing claims linked to the live, empirical, and commercial evidence
  that actually supports them.

### Exit gate

- Ten paying pilots use the same supported offer.
- At least 60% remain active through eight weeks.
- Activation onto the offer's supported historical input or live provider is
  under fifteen minutes for the median new customer; report the branch and
  do not combine unlike activation populations.
- Support burden remains below thirty minutes per customer per week after the
  first two weeks.
- Gross contribution is positive after provider, distribution, payment,
  infrastructure, refund, and support costs.
- No commercial claim exceeds the declared provider, model, or outcome evidence.

These are pilot thresholds, not a forecast of market size or revenue.

## Phase 6 — Expand From Proven Demand

Expansion is a sequence of separate gates, not a bundle:

1. **NQ:** certify independently with its multiplier, contract family, chain
   coverage, sessions, and policy. ES evidence cannot certify NQ.
2. **Supported local service:** stabilize the domain contract around observed
   developer needs before promoting the existing private Wind loopback service
   into a public headless/WebSocket contract.
3. **REST or MCP:** add the interface users actually request while preserving
   the same provenance and rights controls. Do not expose raw licensed data by
   accident.
4. **Second integration:** choose from demonstrated user workflow, not vendor
   logo count.
5. **Multi-symbol scan:** rank structural change only across provider paths
   with comparable certified coverage and quality.
6. **Research teams:** share rights-cleared derived artifacts, manifests, and
   evaluation results; keep credentials and raw licensed inputs local unless a
   separate agreement permits central handling.
7. **Higher Greeks:** add vanna, charm, delta exposure, or scenario P/L only
   when the chosen user job requires them and independent numerical/evidence
   gates exist.
8. **Additional futures complexes:** evaluate rates, metals, or energy one
   contract family at a time. Liquidity, expiry, multiplier, exercise, and data
   semantics require their own policies.
9. **Evidence-aware assistance:** allow natural-language explanation over
   authorized local artifacts only after citations, abstention, and proof-ceiling
   enforcement are testable. Do not create automated trade calls.
10. **Hosted delivery:** centralize derived or raw data only after written
    rights, privacy, support, reliability, and unit economics justify it.

## Cross-Cutting Product Metrics

| Dimension | Measure | Why it matters |
| --- | --- | --- |
| Activation | Time to first replay insight or user checkpoint; time to trusted live view, reported separately | Separates feature completion from user access |
| Repeated value | Weekly completion of the chosen recurring job | A product needs habit or repeated workflow replacement |
| Trust | Provenance/staleness defects, suppressed alerts, unresolved data incidents | One silent wrong state can destroy the core promise |
| Research integrity | Reproducibility rate, corpus coverage, split violations, null-result retention | Measures whether the evidence moat is real |
| Reliability | Accepted-window success, freshness, recovery, and clean-stop evidence within exact scope | Prevents “connected once” from becoming a service claim |
| Commercial fit | Paid conversion, eight-week retention, replacement evidence, and cancellations | Tests actual value rather than compliments |
| Economics | Contribution after data, support, distribution, payment, and infrastructure costs | Prevents a popular workflow from becoming an unviable product |

Metric definitions, populations, and observation windows must be fixed before a
phase uses them as a gate.

## Principal Risks And Responses

| Risk | Early signal | Response |
| --- | --- | --- |
| Commodity feature trap | Users compare only walls and price | Lead with dissent, provenance, replay, and receipts; stop chasing panel parity |
| No recurring user job | Interviews produce feature lists but no repeated replacement | Remain a research project or narrow to the SDK/support path |
| Data-rights mismatch | Desired hosted/display use is not authorized or destroys margin | Keep bring-your-own credentials and local processing; narrow the offer |
| Live path instability | Recurrence failures or silent degradation | Do not promote readiness; repair from evidence or change provider |
| False causal certainty | Users interpret GEX as observed dealer inventory or guaranteed support | Make proxy, quality, alternative models, and disconfirmation visible |
| Research overfitting | Results change after test inspection or only wins are retained | Enforce registered splits, new identities, full populations, and null results |
| Support-heavy distribution | Setup and data issues consume the margin | Improve doctor/setup, narrow the supported envelope, or sell higher-touch B2B support |
| Open-core confusion | Paid value appears to hide previously open calculation | Keep the kernel useful and charge for operational layers with explicit boundaries |
| Premature breadth | Higher Greeks, flow, news, mobile, and AI delay the core loop | Require repeated user evidence and a phase gate for every expansion |

## Explicitly Not Now

- Broad equity-options flow or dark-pool aggregation
- Political, news, social, or community feeds
- Automated trade recommendations or brokerage execution
- A mobile-first application
- A centrally hosted raw market-data lake
- A proprietary composite score that hides model disagreement
- Multi-provider or multi-asset breadth before the selected ES input/workflow is supported
- Higher Greeks added solely for competitive checklist parity
- REST, MCP, or numerous chart integrations before the domain contract is stable
- Predictive, execution, or profitability marketing before corresponding evidence

## Immediate Continuation Point

Follow the [Current Work Order](#current-work-order): after the checkpoint
packet's integration gates, freeze a new current-build study that includes the
demo/replay handoff, preserving the September 20 study unchanged. Use the
[Product Validation](docs/product-validation.md)
approach with real participants and record assistance, non-starts, failed
attempts and trust defects. Route one supported user-input path from that
evidence; neither the rest of the candidate list nor a commercial launch is
implicitly authorized. Product selection remains in the applicable Phase 3
branch.

Separately, obtain owner approval for the prepared ES observation population
and use [Live Population Preparation](docs/live-population-prep.md) to validate
the frozen plan before any authorized live run. Offline product completion
does not supply credentials, data rights or live-readiness evidence.

Contributor-sized offline tasks remain in
[Good First Issues](docs/good-first-issues.md), not in this strategic roadmap.

# Roadmap

This file contains planned and deferred work only. Shipped work belongs in
[CHANGELOG.md](CHANGELOG.md), the current system belongs in
[Architecture](docs/architecture.md), durable outcomes belong in
[Product Vision](docs/product-vision.md), and the evidence behind the strategy
belongs in [Competitive Landscape](docs/market-analysis.md).

Priorities reviewed September 4, 2026 against application version `0.4.0`.
Remaining correctness work is H2 configuration/health and H4 experiment
identity, followed by offline preflight. The phases below remain
conditional plans. [Application Review](docs/application-review.md) owns the
dated health evidence and open findings.

## Current Work Order

Prioritize correctness of the user's result, then reliable first use, then the
research workflow. Customer discovery proceeds alongside these engineering
slices. A priority is a recommendation, not a claim that its work has started;
an accepted work packet owns implementation status.

| Order | Work | Why now | Completion evidence |
| --- | --- | --- | --- |
| 1 — Correctness | Close H2 and H4: configuration/health and experiment identity | A useful product must preserve the identity and validity of the result before adding delivery features | Each accepted finding has a minimal reproduction, a focused regression, and an explicit rejection or correct result through the public workflow |
| 2 — Offline preflight | Add an offline `doctor` command and repair any demonstrated install/configuration failures | Users and contributors need to distinguish a broken environment from an unsupported provider | Text/JSON diagnostics work from an installed wheel outside the checkout; invalid base configuration fails; absent optional providers are explained; no connection or secret disclosure occurs |
| 3 — Complete one research loop | Extend the existing Demo Lab with model comparison and a reproducible review receipt; add a synthetic NQ fixture where needed | Existing replay, export, journal, and experiment tools already provide most of the machinery | One authorized session yields a portable pack with source/model/quality identity, separated position models, and a reproducible result |
| 4 — Make it usable on a fresh machine | Deliver one guided install and replay journey for the first user segment | Observed activation matters more than another command or panel | One selected distribution path passes install/upgrade checks and users complete the scoped journey without developer help |
| 5 — Prepare a supported live beta | Finish required local support/lifecycle work and the separate recurring ES certification gate | This converts the validated offline job into a dependable live workflow | Phase 1 support gates, Phase 2 evidence, and Phase 3 entry requirements all pass within a declared scope |

Two tracks can progress alongside that order:

- **Customer evidence — Phase 0:** prepare the interview protocol, comparable
  concepts, observed tasks, rights questions, and cost model now. Recruitment,
  interviews, commitments, and provider answers require real participants or
  owners; a written protocol does not complete those gates.
- **Live evidence — Phase 2:** prepare the recurrence criteria now and run
  bounded ES observations when credentials, entitlements, and data-use authority
  are available. NQ needs independent evidence.

Keep each engineering slice reviewable and mergeable on its own. Dependent
slices land in order; independent work may proceed in isolated contributor
branches, with integration checks before each merge. This bounded parallelism
implements the maintainer's September 4 authorization to complete all offline
priorities. A confirmed correctness issue can interrupt feature work; an
unvalidated feature request cannot.

Before assigning additional provider fixtures, reconcile open
[Databento issue #5](https://github.com/zrack/gex-terminal/issues/5) with the
shipped fixture/certification tools and review the existing
[Tradovate contribution #10](https://github.com/zrack/gex-terminal/pull/10)
against its linked issue. Avoid a parallel implementation of that contributor's
scope. This queue cleanup does not outrank the correctness repairs above.

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
It is not yet a chosen commercial product. The MIT research kernel remains
useful and open; a paid layer, if customer evidence supports one, sells
convenience, certified workflows, automation, integrations, governed storage,
and support.

The strongest alternative is a **hosted ES/NQ tactical cockpit** with simple
levels, explanations, push alerts, and chart delivery. It has a clearer retail
promise but requires substantially stronger data licensing, uptime, support,
mobile UX, and unit economics. Phase 0 decides whether that alternative earns a
live comparator pilot. Phase 3 is the single authoritative product-path
decision.

## Priority And Gate Map

Phases describe dependencies, not delivery dates. Phase 0 and bounded offline
work can overlap; after Phase 3, research evidence and a descriptive paid beta
can progress in parallel. A phase advances on its exit evidence.

| Phase | Outcome | Can proceed without live data? | Primary gate |
| --- | --- | ---: | --- |
| 0 — Now | Prove the customer wedge and qualify or retire the hosted alternative | Yes | Repeated user job, design partners, data-rights path, and paid-pilot intent |
| 1 — Now/next | Correctness, offline preflight, one research loop, and usable distribution | Yes | Correct results, safe diagnostics, portable evidence, and clean-machine activation |
| 2 — Parallel external gate | Certify one narrow recurring ES/Databento operating envelope | No | Credential, entitlement, capture authority, exact-run evidence, and predeclared recurrence |
| 3 | Run a design-partner live beta | Partly | Weekly use, reliable activation, workflow replacement, and no severe trust defects |
| 4 — Evidence track | Build the governed evidence moat | No for real-session evidence | Licensed corpus, preregistered evaluation, reproducibility, and appropriately narrow claims |
| 5 — Commercial track | Establish a paid descriptive-tool beta after Phase 3 | Partly | Distribution/legal readiness, retention, support load, and positive unit economics; predictive success is not a prerequisite |
| 6 | Expand from proven demand | Depends | Independent symbol/provider evidence and demonstrated user demand |

The recommended counts and thresholds below are hypotheses to predeclare in a
work packet. They are not existing measurements and can be changed before data
collection with a recorded reason.

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

1. Recruit 12–15 interview candidates split between quantitative/developer
   users and advanced ES/NQ traders. Treat existing personas as hypotheses.
2. Run at least six observed task sessions using current demo and replay data.
   Ask users to reach a trusted view, explain one level, compare models, save a
   receipt, and replay the session without developer help.
3. Prototype both product stories at comparable fidelity:
   - professional local instrument: Today, Explain, Compare, Replay, Review;
   - hosted tactical cockpit: current levels, simple explanation, alert, and
     chart delivery.
4. Record task completion, time to insight, trust questions, install tolerance,
   existing data accounts, workflow replacement, and price reaction.
5. Produce a provider/data-rights matrix covering personal and professional
   use, non-display calculation, local retention, derived display, external
   distribution, support access, and termination obligations.
6. Model the first-year economics for bring-your-own data, bundled data, and a
   developer/support product. Keep exchange fees and support time explicit.

### Exit gate

- Five users commit to a design-partner beta with a named recurring job.
- At least three will connect a legitimate existing data account.
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

This phase is repository-owned and can proceed using synthetic, sanitized, and
rights-cleared inputs.

### Slice 1A — Correct results and offline preflight

Land correctness repairs in focused changes before building on affected output.
Use the [application review](docs/application-review.md) for reproductions and
acceptance targets, then add an independent `doctor` slice:

- Check package/Python identity, bundled resources, configuration validity,
  optional SDK presence, selected provider/readiness, and local storage access.
- Produce concise text and versioned JSON with useful exit codes. Distinguish
  broken base installation from an absent optional provider.
- Keep the command offline with no persistent application-state changes. A
  writable-storage probe may create and remove its own temporary file in the
  selected directory; it must not alter existing research or credentials.
  Report live authentication and entitlements as unverified; file or SDK
  presence cannot establish them.
- Reuse central redaction and exclude credentials, account IDs, and raw data.

Exit when corrected inputs preserve symbol/model/source identity, invalid
configuration fails visibly, and an installed wheel can run the preflight from
an arbitrary directory with no network calls or secret-bearing output.

### Slice 1B — One portable research loop

- Extend the existing `demo-lab` and experiment/report tools with separated
  model comparison and a review receipt; avoid creating a competing pack format.
- Add a dedicated synthetic schema-v2 NQ replay and ensure symbol/multiplier
  identity remains consistent across the chosen replay and generated pack.
- Bind the pack to authorized inputs, application/model version, assumptions,
  quality, and stable content identities. Carry evidence limits into every
  artifact that can leave the application.
- Expose only the read-only snapshot, quality, or comparison objects required
  by this workflow. Keep new Python interfaces experimental until their shape
  is exercised; declare support and compatibility for any exported schema.
- Preserve consumer state ownership and existing immutable research identities.

Exit when one action produces the scoped pack and another clean environment
reproduces its semantic results. Tests must reject incompatible versions,
changed inputs, and mislabeled symbol/model state. A broad public SDK is not
required to complete this slice.

### Slice 1C — Install and guided journey

- Select one installation path using Phase 0 user evidence; use the existing
  wheel as the technical baseline. Packaging correctness can be checked now.
- Verify install, upgrade, failed upgrade, rollback, and uninstall on the
  explicitly supported platform(s), preserving compatible local artifacts.
- Guide Today, Explain, Compare, Replay, and Review through existing tools,
  adding only the navigation and drill-down needed for the chosen job.
- Make model disagreement, input quality, and provenance visible. Test normal
  and small terminal sizes and declare a usable minimum size.

Technical packaging acceptance precedes observed user acceptance. Exit when a
new user installs without a checkout, reaches a replay insight in under ten
minutes, and completes the scoped loop in under fifteen minutes without
developer help. These times are proposed user-study thresholds, not existing
measurements. Full desktop redesign, multiple installers, and automatic
updating are separate demand-driven decisions.

### Slice 1D — Beta support and local lifecycle

- Add a redacted support bundle containing version, configuration shape,
  readiness, bounded diagnostics, and artifact identities.
- Define credential storage and removal for the selected provider/platform;
  route any credential-store implementation under the existing change profile.
- Verify recovery, backup/restore, retention, and deletion for the file-based
  artifacts actually supported by the beta. Preserve append-only identities.
- Specify what uninstall removes and what research data requires explicit
  deletion. Keep raw licensed data governed separately.

Exit when supported recovery/lifecycle paths pass and support output contains
no credential, account identifier, raw licensed payload, or configured sensitive
value. An indexed database/catalog and generalized migration framework move to
Phase 4 only if observed retrieval or scale needs justify them.

### Phase exit

Phase 1 completes after all four slices pass. Correctness repairs precede any
workflow that consumes affected results. Preflight and packaging investigation
can proceed independently; the guided journey consumes the accepted research
loop and a working installation path. Support/lifecycle work is required before
supported live beta use. Customer discovery runs alongside these slices.

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
2. Before running or reviewing the first observation, route a recurrence packet
   defining observation count, open/midday/close or Globex coverage, market
   conditions, failure tolerance, retention, and promotion logic.
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
- If licensing prohibits the needed use, retain offline certification and stop
  the commercial path until a lawful alternative exists.
- If recurring reliability cannot be demonstrated, do not expose the path as a
  supported live beta.

## Phase 3 — Design-Partner Live Beta

**Purpose:** determine whether a certified input becomes a repeated user
workflow rather than merely a technically successful connection.

### Work

- Before onboarding a design partner, establish a signed beta agreement,
  privacy notice, explicit consent for any optional telemetry, data-handling promises,
  risk disclaimer, security/vulnerability path, support limits, and incident
  contact. Phase 5 can harden these for paid scale; it cannot introduce them
  after live use begins.
- Deliver four primary live workflows: Today, Explain, Compare, and Replay;
  Review can begin with daily evidence packs.
- Show OI, raw-volume, and directionalized-volume agreement or dissent without
  blending their quantities.
- Add local rule-based alerts that carry provider, model, as-of, quality, and
  readiness provenance. A degraded feed suppresses or clearly downgrades an
  alert according to a predeclared rule.
- Build one integration selected by Phase 0 evidence. Prefer a local file or
  webhook/chart bridge before building another full charting surface.
- Add background operation, bounded recovery, user-visible incident state,
  and redacted diagnostics.
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
- At least 80% install and connect without developer intervention.
- Median launch-to-trusted-live-view is under five minutes after setup.
- At least three users say it replaced a named manual step or paid-tool
  workflow and demonstrate that replacement during observation.
- At least two users agree to a paid beta for the same defined product.
- No unresolved high-severity defect can misstate source, freshness, contract,
  model, or recovery state.

### Product decision

If the hosted-cockpit pilot qualified and ran, compare its results with the
local beta. Choose the hosted path only if its activation, four-week retention,
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

Rights-authorized collection can begin during Phase 2 once the applicable
capture gate passes. This evidence track can continue alongside Phase 5. A paid
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
- Define when corpus membership requires an `as_of` cutoff and distinguish
  source registration from eligibility for point-in-time evaluation. A passing
  corpus integrity check alone cannot establish evaluation eligibility.
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

Entry requires the accepted Phase 3 product decision, supported live scope and
beta workflow, and the commercial requirements below. Phase 4 may still be in
progress; its unmeasured outcomes must remain unclaimed.

### Local-path offer hypothesis

This offer applies only if the Phase 3 decision selects the local professional
product. A hosted decision requires a replacement commercial plan before this
phase begins.

- Keep the MIT offline research kernel available.
- Sell signed distribution, guided setup, supported live-provider operation,
  alerts and integrations, governed local evidence storage, updates, and
  support.
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
- Supported-provider activation is under fifteen minutes for the median new
  customer.
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
2. **Headless local service:** expose the stable domain contract through a
   bounded local process and WebSocket only after the Python contract is stable.
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
| Activation | Time to first replay insight; time to trusted live view | Separates feature completion from user access |
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
- Multi-provider or multi-asset breadth before one ES path is supported
- Higher Greeks added solely for competitive checklist parity
- REST, MCP, or numerous chart integrations before the domain contract is stable
- Predictive, execution, or profitability marketing before corresponding evidence

## Immediate Continuation Point

Finish H2 health/configuration and H4 experiment identity as separate
bounded repair slices with their own reproductions and regressions. Finish
this correctness sequence before extending the affected research workflows.

The subsequent `GEX-PREFLIGHT-001` proposal covers the offline diagnostic command
in Slice 1A. These proposals do not include a database, public API freeze, new
provider, or UI rewrite, and become active only when individually routed.

In parallel, a separate Phase 0 packet should own the interview protocol,
two comparable prototypes, acceptance tasks, data-rights questions, commercial
hypotheses, metric definitions, and qualification or retirement of the hosted
comparator. The final product-path decision remains in Phase 3. Prepare these
materials without treating customer commitments or provider answers as given.

The existing credentialed ES observation remains a separate external evidence
gate under Phase 2. Do not hold customer discovery or offline product design
hostage to live data, and do not let offline product progress imply live
readiness.

Contributor-sized offline tasks remain in
[Good First Issues](docs/good-first-issues.md), not in this strategic roadmap.

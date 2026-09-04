# Roadmap

This file contains planned and deferred work only. Shipped work belongs in
[CHANGELOG.md](CHANGELOG.md), the current system belongs in
[Architecture](docs/architecture.md), durable outcomes belong in
[Product Vision](docs/product-vision.md), and the evidence behind the strategy
belongs in [Competitive Landscape](docs/market-analysis.md).

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

Planning ranges describe likely sequence, not delivery commitments. A phase
advances on its exit evidence, not because a date elapsed.

| Phase | Outcome | Can proceed without live data? | Primary gate |
| --- | --- | ---: | --- |
| 0 — Now | Prove the customer wedge and qualify or retire the hosted alternative | Yes | Repeated user job, design partners, data-rights path, and paid-pilot intent |
| 1 — Next | Make the offline research kernel installable and usable as one product | Yes | Clean-machine activation, stable contracts, safe diagnostics, and reproducible evidence pack |
| 2 — Parallel external gate | Certify one narrow recurring ES/Databento operating envelope | No | Credential, entitlement, capture authority, exact-run evidence, and predeclared recurrence |
| 3 | Run a design-partner live beta | Partly | Weekly use, reliable activation, workflow replacement, and no severe trust defects |
| 4 | Build the governed evidence moat | No for real-session evidence | Licensed corpus, preregistered evaluation, reproducibility, and appropriately narrow claims |
| 5 | Establish a paid commercial beta | Partly | Distribution/legal readiness, retention, support load, and positive unit economics |
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

### Slice 1A — Stable contract and evidence pack

- Define supported read-only Python objects for normalized events, provider and
  quality state, model profiles, snapshots, comparisons, and experiment
  artifacts.
- Publish compatibility, schema-version, deprecation, and migration policies.
- Add golden contract tests that load artifacts across the declared supported
  version boundary.
- Keep mutable state ownership inside the existing consumer; public interfaces
  must not bypass validation or introduce alternate semantics.
- Generate one complete shareable evidence pack from a session without asking
  the user to assemble multiple command outputs.

Exit this slice when the public contract and artifact compatibility tests pass
across the declared version boundary and a second clean environment can verify
the one-action evidence pack.

### Slice 1B — Guided offline journey

- Reorganize the visible product around Today, Explain, Compare, Replay, and
  Review while preserving backward-compatible CLI entry points.
- Make model disagreement, input quality, and provenance primary surfaces.
- Let a user drill from a wall, flip, or profile change to the contributing
  contracts and assumptions.
- Add a guided first run and an offline `doctor` workflow for version, optional
  dependencies, configuration, storage, and local resource readiness.

Exit this slice when a clean user reaches the first replay insight in under ten
minutes and completes Today/Explain/Compare/Replay/Review in under fifteen
minutes without repository checkout or developer help.

### Slice 1C — Local lifecycle and supportability

- Extend `doctor` to cover credential-store availability, provider selection,
  and entitlement-readiness checks without opening an unauthorized connection.
- Use a platform credential-store abstraction where supported; never move
  secrets into an artifact or support bundle.
- Add a redacted support bundle with application version, configuration shape,
  readiness state, recent bounded diagnostics, and artifact identities.
- Define clean uninstall and local-data deletion behavior.

#### Indexed local data

- Add an indexed local catalog for derived sessions, experiment metadata,
  model versions, tags, and quality states; raw licensed data remains governed
  separately.
- Add explicit migrations, backup/restore, retention enforcement, and deletion
  tests.
- Preserve append-only experiment and corpus identity while allowing indexes
  and disposable derived views to be rebuilt.

Exit this slice when migrations, backup/restore, retention, and deletion pass
from supported prior states and a generated support bundle contains no
credential, account identifier, raw licensed payload, or configured sensitive
value.

### Slice 1D — Supported distribution

- Choose the smallest supported release path based on Phase 0 users: PyPI,
  Homebrew, a signed standalone application, or a limited combination.
- Produce checksummed/signed artifacts, a release channel, upgrade and rollback
  behavior, and clean-machine smoke tests.
- Test first install, upgrade with existing sessions, failed upgrade, rollback,
  and uninstall on every supported platform.

Exit this slice when a non-developer installs without repository checkout,
upgrade and rollback preserve compatible settings and research identities, and
the full clean-install matrix passes on every supported platform.

### Phase exit

Phase 1 completes only after slices 1A through 1D pass in order. Each slice is
independently reviewable and releasable; failure in a later slice does not erase
the evidence from an accepted earlier slice.

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
  privacy and telemetry notice with explicit consent, data-handling promises,
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
- Add opt-in, privacy-safe product analytics for activation and workflow use;
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

- Every participant has the applicable beta agreement and telemetry consent;
  support, incident, security, risk, and data-handling commitments were usable
  throughout the pilot.
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

Compare these results with the time-boxed hosted-cockpit pilot. Choose the hosted
path only if its activation, four-week retention, and willingness to pay are
materially stronger and the data-rights economics remain viable. Otherwise
continue with the local professional product.

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

### Work

- Build a licensed corpus spanning volatility, expiry, event, overnight, trend,
  range, and data-quality regimes.
- Register immutable train, calibration, and untouched test identities before
  evaluating outcomes.
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
- Operate signed release channels, auto-update or guided update, migrations,
  rollback, support bundles, and a vulnerability/incident process.
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

The next governed product packet should own Phase 0 only: interview protocol,
two comparable prototypes, acceptance tasks, data-rights matrix, commercial
hypotheses, metric definitions, and the product-path decision. Phase 1 can begin
with reversible contract and clean-install work, but should not choose a broad
distribution surface before Phase 0 identifies the first user and buying model.

The existing credentialed ES observation remains a separate external evidence
gate under Phase 2. Do not hold customer discovery or offline product design
hostage to live data, and do not let offline product progress imply live
readiness.

Contributor-sized offline tasks remain in
[Good First Issues](docs/good-first-issues.md), not in this strategic roadmap.

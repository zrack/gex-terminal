# Product Validation Protocol

Prepared September 4, 2026. This is the reusable Phase 0 study kit, not a study
result. No participants, commitments, measured activation times, provider
permissions or tested prices have been supplied. [Roadmap](../ROADMAP.md) owns
the decision gates; [Product Vision](product-vision.md) owns the lead hypothesis.

## Recruitment and consent

Recruit 12–15 candidates across quantitative/developer researchers and advanced
ES/NQ traders. Record role, recurring job, current tool/manual substitute, data
account availability, and whether they make the buying decision. Include both
people willing and unwilling to manage a local provider connection. Do not
filter for enthusiasm about GEX or count project contributors as independent
customers without labeling that relationship.

Ask for consent to observe tasks and retain de-identified notes. Recording is
optional and requires separate consent. Assign participant IDs; keep contact
details and consent records outside this repository in owner-controlled
storage. Never collect credentials, account IDs, positions, P&L or raw licensed
screens. The study owner must select a retention/deletion date before recruiting.
No invitation or offer is sent automatically by this kit.

## Interview (20 minutes)

1. “Walk me through the last time you needed to understand ES/NQ structure.
   What triggered it, what did you do, and what decision followed?”
2. “Show or describe the step that took the most effort. What do you use today?
   What happens when that source is stale or the models disagree?”
3. “When would you need to reconstruct what you saw? Who else needs the result?”
4. “Which data access do you already maintain? What installation or account
   setup would prevent you using another tool?” Do not request login details.
5. Present the two concepts below in alternating order. Ask what each replaces,
   when it would not help, and what evidence is missing. Separate observation
   from stated preference and hypothetical willingness to pay.

## Matched-fidelity paper prototypes

Read both as five screen cards with the same neutral synthetic session. Neither
is an implemented hosted/live service. Do not compare a polished live demo with
an unpolished alternative. First compare these paper flows; test the working
offline application separately.

| Card | Local research instrument | Hosted tactical cockpit |
| --- | --- | --- |
| Start | Choose synthetic ES or NQ; inspect source, time and quality before continuing | Choose synthetic ES or NQ; inspect source, time and quality before continuing |
| Inspect | Open a structural level and its contract/model assumptions | Open a structural level and its plain-language explanation |
| Disagree | Compare OI, raw-volume and directionalized-volume views side by side; no combined score | See a disagreement warning beside the displayed level; expand the same three views |
| Act | Save a local review pack; optionally choose a file/chart handoff | Preview a hypothetical push alert/chart delivery; nothing is sent |
| Review | Reopen the pack, verify its receipt and replay the later synthetic state | Reopen the same session history and inspect why the hypothetical alert appeared |

Use identical displayed levels and warning text in both concepts. Include one
stale-input card and one missing-direction card. Ask the participant what they
would trust and what they would withhold. Do not suggest that either level
predicts price. Card clicks are moderator narration, not simulated evidence of
live behavior, delivered alerts or paid access.

## Observed application task (at least six participants)

Use [First Run](first-run.md), the same pinned wheel and a fresh environment.
Alternate the provided ES/NQ fixtures across participants and record which was
used. Do not compare task times across fixtures without retaining that context.

1. Install and obtain an offline readiness result.
2. Reach Today and correctly state instrument, source and data time.
3. Explain one structural level and name a model limitation.
4. Compare the three models without adding their quantities together.
5. Save the research pack, then verify and reproduce its receipt.
6. Replay it and state whether this proves anything about live reliability or
   predictive value. Correct answer: neither.

Allow the participant to use shipped help. Log each moderator intervention;
after a blocking failure, assist only to expose the next task and mark that task
assisted. A preinstalled environment cannot count as installation success.

## Copyable scorecard

One row per participant/task; empty means not observed, never zero.

| Participant ID | Segment / buying role | Wheel / OS / Python / fixture | Task | Start / stop | Outcome (unaided / assisted / failed / not attempted) | Help count | Observed confusion or error | Exact replacement named | Follow-up consent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Not yet collected | | | | | | | | | |

- **Install activation:** unaided successful install and readiness result /
  participants who attempted install; report numerator and denominator.
- **Time to insight:** elapsed time from beginning installation to a correct
  source/model/quality explanation. Report completion count and individual
  times; failures remain failures, not discarded fast observations.
- **Loop completion:** unaided completion of all six tasks / all attempts;
  separately report assisted completion and time after install.
- **Trust defect:** participant relies on stale, mislabeled or unverified
  evidence because the product hides or contradicts its status. Record every
  occurrence and reproduction, not just an average satisfaction score.
- **Replacement:** named recurring existing job demonstrated in observation;
  compliments and feature requests are not replacement evidence.

The roadmap's ten-/fifteen-minute targets are prospective hypotheses. A tiny
convenience sample cannot establish a population conversion rate. Report raw
counts, participant mix and missing observations alongside every percentage.

## Rights questions for the responsible owners

All cells remain **unknown** until written terms and an accountable reviewer
answer the exact proposed use. SDK presence, paid access or a successful API
response is not a rights decision. This checklist is not legal advice.

| Use / obligation | BYOD local | Bundled desktop | Hosted delivery | Evidence to obtain |
| --- | --- | --- | --- | --- |
| Personal vs professional status and fees | Unknown | Unknown | Unknown | Provider/exchange classification and fee responsibility |
| Non-display computation and derived metrics | Unknown | Unknown | Unknown | Applicable calculation and derived-data terms |
| Local raw retention / backup | Unknown | Unknown | Unknown | Permitted storage, duration, location and deletion obligations |
| Display to licensed end user | Unknown | Unknown | Unknown | Authorized application, recipient and entitlement enforcement |
| Charts, alerts, exports and redistribution | Unknown | Unknown | Unknown | Written scope for each output and recipient class |
| Support access / incident artifacts | Unknown | Unknown | Unknown | Permitted access, redaction and processor obligations |
| Research reuse / publication | Unknown | Unknown | Unknown | Capture policy and source-specific reuse authority |
| Termination and audit | Unknown | Unknown | Unknown | Revocation, deletion, audit and subcontractor requirements |

Record source document/version, exact use, reviewer, decision/date and renewal
condition outside public notes when the agreement is confidential. Route actual
captures through [Capture Governance](capture-governance.md).

## First-year economics worksheet

Use separate rows for BYOD desktop, bundled desktop, hosted delivery and
developer/integration support. Inputs are **unmeasured**, not industry estimates.
Enter conservative/base/optimistic scenarios and retain units and provenance.

| Input | Unit | Evidence required |
| --- | --- | --- |
| Price P | dollars per active customer per month | A defined offer tested with the intended buyer |
| Active paid customer-months M | customer-months in year one | Cohort additions, churn and seasonality assumptions |
| Payment fraction f and per-payment cost t | fraction; dollars | Actual selected billing quote |
| Data/entitlement cost d | dollars per customer-month | Written provider/exchange quote, status and minimums |
| Hosting/storage/incident cost h | dollars per customer-month | Workload-based measured estimate |
| Support time s and loaded hourly cost w | hours per customer-month; dollars/hour | Pilot time log and owner cost assumption |
| Acquisition/onboarding A | dollars per new customer | Actual channel and onboarding effort assumptions |
| New paying customers N | customers in year one | Cohort plan, separate from M |
| Fixed build/legal/security/support F | dollars in year one | Named work and quotes or bounded labor estimates |

Monthly unit contribution: `C = P × (1 − f) − t − d − h − s × w`.
Year-one contribution after acquisition and fixed costs:
`M × C − N × A − F`. Fixed annual licensing minimums belong in F, with only
incremental per-customer charges in d; do not count the same fee twice. BYOD can
set d to zero only when written terms establish that the business owes no
incremental data fee. Developer support can use paid seat-months plus a separate
project-fee/labor row; do not invent recurring seats for one-off services.

Illustrative arithmetic only: P=60, f=0.03, t=0.30, d=0, h=2, s=0.25 and w=80
give C=35.90. At M=120, N=20, A=25 and F=10,000, year one is −6,192.
This is a formula check, not a forecast, price recommendation or rights claim.
Break-even customer-months for fixed N/F are `(N × A + F) / C` only if C>0;
negative contribution is not fixed by adding customers.

Before price testing, define exactly what is included, data charges, limitations,
support and refund/cancellation conditions. Record offered price separately
from enthusiasm, nonbinding intent and an accepted commitment. Do not charge or
promise an unavailable service. Phase 3 remains the final product-path decision.

# Live Population Preparation

This guide prepares one prospective, recurring **ES** observation population
without contacting Databento. It is an offline preregistration and review
contract, not a live command. A valid file establishes internal consistency and
stable identity only; it does not grant data rights, authorize credentials,
prove that an observation occurred, certify a report, or change provider
readiness.

The current schemas are:

- `gex-terminal.databento-live-population-plan.v1`
- `gex-terminal.databento-live-population-results.v1`
- `gex-terminal.canonical-json.v1`

Unknown schemas and fields fail closed. Both identities hash every normalized
field. JSON whitespace and object-key order do not change the digest, but any
decision, time, run, result, note, or limitation does.

## Prepare And Freeze The Plan

Start from the packaged
[`databento_es_live_population_plan_template.json`](../gex_terminal/data/provider_fixtures/databento_es_live_population_plan_template.json).
The template is intentionally invalid while any `REPLACE_WITH_...` value
remains. It contains no credential, account identifier, licensed payload, or
execution authority.

Fill every owner decision outside the public repository when timing,
entitlement, or operating details are restricted:

- one stable population ID plus non-identifying operator and reviewer aliases;
- the exact `gex-terminal`, Python, and Databento SDK versions, operating system,
  and architecture accepted for all attempts;
- a reference to the separate owner approval, a redacted entitlement scope,
  and rights and retention decisions;
- the reviewed exchange-calendar source, UTC clock source, and predeclared stale
  response;
- exactly 12 unique, chronological, non-overlapping 20-minute UTC slots across
  at least four trading dates: three each for `regular_open`, `midday`,
  `regular_close`, and `globex`;
- exactly two restart observations on distinct trading dates; and
- explicit coverage limitations. A calendar label is an operator declaration,
  not proof of an event or volatility regime.

The plan is fixed to Databento `GLBX.MDP3`, ES, multiplier 50, and the complete
registered `databento-es-prelive-v1` policy identity. Do not edit that identity
by hand. If the repository policy changes, use the new release's template and
create a new population.

For an initial population, keep:

```json
{
  "status": "first_population",
  "prior_population_id": null,
  "prior_result_manifest_sha256": null
}
```

After a failed or completed population, a successor must instead declare
`successor_population`, the prior population ID, and the exact SHA-256 printed
when its complete result manifest validated. This is an immutable lineage link;
it prevents a later population from silently replacing the prior manifest. It
does not independently prove that the referenced file was complete or genuine.

Validate locally:

```bash
gex-terminal live-population-plan-validate /private/path/es-plan.json
```

The command reads the JSON and prints its population ID, schema, and canonical
plan SHA-256. It does not connect, inspect credentials, schedule a run, make the
file immutable, or write another artifact. Store the exact reviewed plan in
owner-controlled storage and bind any later process to the printed digest.

## External Gate Before Any Observation

No execution command is shipped by this preparation slice. Before separate live
work, the accountable owner still has to accept the plan and exact versions,
authorize read-only provider access, confirm current entitlements and rights,
choose storage/deletion handling, and establish the operator procedure. Raw
capture remains false here; enabling capture requires its own valid
[Capture Governance](capture-governance.md) policy and authority.

A changed slot, build, SDK, policy, environment, or owner decision requires a
new plan identity before observation. A post-result amendment is not a repair to
the old population.

## Record And Validate The Full Population

After separately authorized observations, prepare one redacted result manifest
with all 12 runs in the plan's exact order. The top-level shape is:

```json
{
  "schema": "gex-terminal.databento-live-population-results.v1",
  "canonicalization": "gex-terminal.canonical-json.v1",
  "plan_identity": {
    "schema": "gex-terminal.databento-live-population-plan-identity.v1",
    "canonicalization": "gex-terminal.canonical-json.v1",
    "plan_schema": "gex-terminal.databento-live-population-plan.v1",
    "population_id": "the-frozen-population-id",
    "sha256": "the-printed-plan-sha256"
  },
  "observations": [
    {
      "run_id": "the-first-planned-run-id",
      "outcome": "passed",
      "actual_start_utc": "2026-10-05T14:30:00Z",
      "actual_stop_utc": "2026-10-05T14:50:00Z",
      "runtime": {
        "gex_terminal_version": "0.5.0",
        "python_version": "3.12.11",
        "provider_sdk_version": "0.83.0",
        "operating_system": "macOS 15.6.1",
        "architecture": "arm64"
      },
      "certification_policy_sha256": "the-policy-sha256-from-the-plan",
      "report": {
        "status": "produced",
        "sha256": "the-redacted-report-file-sha256"
      },
      "redacted_notes": ""
    }
  ],
  "evidence_ceiling": "offline structural validation only; no execution authority, live-provider observation, report-authenticity, provider-readiness, predictive, execution, or profitability claim"
}
```

That excerpt is not a valid manifest because it omits the other 11 runs. Allowed
outcomes are `passed`, `authentication_failure`, `entitlement_failure`,
`policy_failure`, `payload_failure`, `temporal_failure`, `lifecycle_failure`,
`operator_interruption`, `environment_failure`, and `missed`.

- Every non-missed attempt records actual UTC start/stop, the exact planned
  runtime, the policy digest, and report state.
- A pass must cover its complete planned window and include a report digest:
  the operator starts no later than the planned start and stops no earlier than
  the planned end. Actual timestamps retain seconds and fractional seconds; the
  validator does not round them to the planned minute boundary.
- A policy failure retains the failing report digest.
- Other failed attempts may declare `not_produced` with a null report digest,
  but require redacted notes.
- A missed window has null actual runtime/policy values, no produced report, and
  redacted notes. It remains one of the 12 runs; it cannot be replaced.

Validate the result against the frozen plan:

```bash
gex-terminal live-population-results-validate \
  /private/path/es-plan.json /private/path/es-results.json
```

The command rejects plan-digest, run-population, runtime, policy, time, outcome,
and report-state mismatches, then prints the complete result-manifest SHA-256.
It validates only the declared report-digest field; it does not locate, read,
hash, or authenticate the report bytes. It also cannot establish that the
declared observation happened or decide readiness. Preserve and independently
verify the redacted reports and review evidence under the separately approved
retention policy.

## Proof Ceiling

A successful validation proves that local JSON conforms to the versioned
contract and is internally bound by canonical hashes. It does not establish
live transport, current provider coverage, sequence-loss causality, OI
availability, general reliability, dealer inventory, predictive value,
execution quality, or profitability. Promotion remains a separate reviewed L3
decision over the complete lineage, including every failure and missed run.

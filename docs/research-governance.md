# Research Governance

The Offline Research Certification Workbench makes offline GEX experiments
repeatable and reviewable. It does not turn fixtures, generated chains, or saved
price paths into evidence of live-provider readiness, dealer inventory, trading
edge, execution quality, or profitability.

## Authority Model

Four contracts keep research decisions inspectable:

1. A **model profile** fixes symbol, multiplier, rates, DTE fallback, pricing
   models, position-model order, directional coverage, and underlying-age gates.
2. An **experiment spec** fixes the workflow, input, point-in-time cutoff, data
   split, outcome definition, cost assumptions, and inline model profile.
3. An **experiment manifest** records package/Python versions and SHA-256
   identities for the input, profile, and semantic result.
4. A **research corpus** records immutable dataset IDs, source digests, rights,
   redaction, split, outcome, and cost metadata in an append-only hash chain.

The schemas are versioned. Unknown schemas or unsupported model ladders fail
closed. `predictive_validity` is fixed to `unmeasured` in these offline
contracts.

## Run And Reproduce An Experiment

Start from the packaged examples in
`gex_terminal/data/provider_fixtures/model_profile_example.json` and
`experiment_spec_example.json`:

```bash
gex-terminal experiment-run experiment_spec.json /tmp/gex-experiment
gex-terminal experiment-reproduce \
  /tmp/gex-experiment/manifest.json /tmp/gex-reproduction
```

Reproduction verifies the original input digest and compares a semantic result
digest that excludes generation timestamps only. A changed input or
decision-relevant output fails the command.

## Register And Verify A Corpus

Corpus storage is local by default. Do not commit licensed or private data.

```bash
gex-terminal corpus-init /tmp/gex-corpus --corpus-id es-research-v1
gex-terminal corpus-register /tmp/gex-corpus INPUT.json METADATA.json
gex-terminal corpus-verify /tmp/gex-corpus /tmp/gex-corpus-report.json
```

Registration never edits earlier events. Duplicate IDs or source digests are
rejected. Verification fails on chain tampering, source drift, missing files,
duplicate identities, or invalid split labels. Rights metadata describes the
operator's declaration; the tool does not independently grant data rights.

Captured sessions are stricter than ordinary offline inputs. Supply the exact
capture policy during registration:

```bash
gex-terminal corpus-register /tmp/gex-corpus \
  session.gex-session.jsonl captured-session-metadata.json \
  --capture-policy capture-policy.json
```

The captured header's policy schema, ID, and SHA-256 must exactly match the
supplied policy. The policy must approve research use; corpus metadata rights
status and redistribution decision must match it; and metadata must declare
`source_kind=captured_session` plus `redaction_status=verified`. A prohibited
research-use decision, missing/mismatched policy, rights mismatch, or merely
required/unknown redaction fails closed. See
[Capture Governance](capture-governance.md) for the policy contract and its
legal/evidence limits.

## Compare Multiple Sessions

`batch-position-compare` runs the existing point-in-time OI/raw-volume/
directionalized comparison across declared sessions and groups results by day,
expiry, and DTE layer:

```bash
gex-terminal batch-position-compare batch_spec.json batch_report.json
```

Position sources are evaluated separately and never summed. Directionalized
results below the profile coverage gate stay visible but unscored.

## Offline Certification Gates

```bash
gex-terminal model-property-certify /tmp/model-properties.json
gex-terminal provider-fault-certify /tmp/provider-faults.json
gex-terminal performance-certify /tmp/performance.json
```

- Model properties cover Black-76 price/IV round trips, put-call parity,
  finite-difference gamma, row-order invariance, scaling, cumulative update
  idempotence, and nonfinite failures.
- Provider faults cover deterministic gap, duplicate, reorder, malformed,
  unknown, partial-definition, and lifecycle cases. The gap detector is a
  harness assertion; it is not evidence that every provider adapter exposes a
  native sequence-gap signal.
- Performance uses a generated normalized chain and reports its environment,
  throughput, snapshot latency, memory, and explicit budgets. It is not a live
  capacity or latency claim.

Budget overrides must appear in the retained report. Do not silently relax a
gate and compare that result with a report produced under different limits.

## Evidence Ladder

| Evidence | What it can establish | What remains open |
| --- | --- | --- |
| Unit/property tests | Deterministic software behavior | Provider and market behavior |
| Fixtures/fault lab | Mapping and fail-closed behavior for covered cases | Payload drift and real reconnect behavior |
| Generated benchmark | Local algorithm/runtime envelope | Live throughput and network latency |
| Governed saved corpus | Reproducible descriptive evaluation | Generalization and execution |
| Credentialed certification | One bounded provider/environment run | Ongoing reliability and predictive validity |
| Preregistered out-of-sample study | Narrow empirical claim under declared costs | Broader market regimes and production execution |

Promotion requires the next rung's evidence; passing a lower rung cannot be
relabeled as a higher one.

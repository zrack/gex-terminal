# GEX-HEALTH-005 — Accepted-Event Chronology

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
packet_owner: project maintainer
branch: codex/gex-health-005-accepted-chronology
created: 2026-09-04
```

Authorized by the September 4 offline-correctness request. Preserve INV-01
through INV-08, especially consumer state ownership and point-in-time evidence.
No live observation or predictive claim is in scope.

## Contract and acceptance

- Consumer updates explicitly return accepted/rejected status; existing callers
  may ignore it. Malformed, off-symbol, duplicate, and identity-conflicting
  records cannot create analytical transitions.
- Replay reports separate raw input audit timestamps/phases/count from accepted
  state time. Snapshot timestamp equals model as-of. Timeline points retain the
  accepted input index/time separately from the monotonic model-state time.
- Untimed legacy input cannot claim an observed market time: expose processing
  time as such. Raw quality annotations remain diagnostic, not state transitions.
- Regressions append late rejected records after valid state and cover downstream
  journal persistence and report formats. Valid behavior remains unchanged.

## Verification and recovery

Run focused consumer/replay/journal tests, full regression, compileall, numerical
evidence and diff checks; await hosted checks, merge and verify clean main.
Revert the merge for code recovery. Existing artifacts are not rewritten.

## Evidence

- 32 focused consumer/replay/journal tests passed. New regressions explicitly
  separate late rejected input from model time and persist that boundary through
  the journal workflow.
- All 320 tests, compileall, diff hygiene and numerical model evidence passed.
- [PR #22](https://github.com/zrack/gex-terminal/pull/22) passed all four hosted
  checks and merged as `813bb24`. Clean merged main passed all 320 tests and
  source compilation with no working-tree changes.

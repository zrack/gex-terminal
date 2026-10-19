# GEX-TRADOVATE-OFFLINE-010 — Rework PR #10 Without Provider Data

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: active
baseline: main@8cea6dd63979dc56d2a065b0271473ffa0aea941
original_contribution: 03d5ed80e93452c03a9ccce244cf1e671597f91b
branch: codex/tradovate-offline-pr10
created: 2026-10-18
packet_owner: project maintainer
external_outcome: "Open — actual sanitized Tradovate ES/NQ payloads"
```

## Authority and scope

The maintainer requested every identified offline fix in
[PR #10](https://github.com/zrack/gex-terminal/pull/10), regression tests,
documentation, commit and merge. The original contributor commits are preserved
and current main is merged into that history. Replace the self-validating flat
fixture with explicitly constructed discovery/quote examples and tests that
exercise production code. Remove automatic closure of
[issue #4](https://github.com/zrack/gex-terminal/issues/4); it remains open for
actual sanitized demo or live ES/NQ payloads and their field/entitlement evidence.

Cover real discovery with mocked HTTP responses, metadata joins, ES/NQ units,
calls/puts, expiries, cumulative trade volume, separate OI, missing IV and
malformed inputs. Expand offline auth/renewal/retry/reconnect/cleanup and probe
failure coverage. Repair demonstrated parameter, acknowledgement, cleanup,
redaction and certification defects. Preserve the existing normalized schema,
model separation, `scaffold` registry status and source-state ownership.
L3 applies to authorization gates, privacy and certification claims. No live
access, credentialed capture, orders, version/tag/release changes or participant
study amendments are authorized or performed.

## Acceptance and recovery

1. Constructed fixtures explicitly declare provenance and do not pretend to
   establish actual provider shape or market coverage. Known-sensitive-field
   checks work recursively and reject injected fields without flagging prose;
   they are not represented as a general PII sanitizer.
2. Production discovery → adapter → consumer → engine regressions cover the
   stated matrix with all network boundaries mocked. Numeric inputs reject
   booleans, fractions in integer fields, nonfinite values and invalid bounds
   before coercion. Invalid quotes cannot suppress later valid quotes or leak
   raw values in rejection logs.
3. Authorization uses correlated typed request IDs and valid statuses. Failed
   background tasks cannot bypass sibling/socket cleanup. Certification keeps
   transport distinct from options/quantitative evidence, fails after observed
   errors or degraded model inputs, and emits bounded fixed error reasons.
4. Update mappings/access documentation against authoritative references while
   distinguishing documented fields, implemented aliases and actual unobserved
   ES/NQ fields. Missing native IV may be an observed outcome; it must not be
   invented to satisfy a test. Broader production certification is a separate gate.
5. Focused/full tests, compilation, documentation links, patch hygiene,
   independent review, numerical evidence, offline provider/fault checks and
   candidate-wheel verification pass. Commit to the original fork branch with
   a fast-forward update, run final-head hosted checks and merge PR #10.
6. Verify clean merged main, local/origin/GitHub equality, full merged-tree
   suite and issue #4 OPEN. Remove only the incorporated local feature branch;
   do not delete a contributor-owned fork branch. Preserve frozen study kits.

Recover by reverting this bounded merge; no stored data migration occurs.
Generated evidence belongs under ignored
`dist/tradovate-offline-pr10/2026-10-18/`. Checkout refresh exposed 109
byte-identical untracked duplicate files; they were moved reversibly into that
directory's `duplicate-backup/`, with hashes in `duplicate-cleanup.json`.

## Evidence

Final verification and integration evidence will be recorded before closure.

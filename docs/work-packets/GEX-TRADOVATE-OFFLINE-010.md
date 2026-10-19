# GEX-TRADOVATE-OFFLINE-010 — Rework PR #10 Without Provider Data

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
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

All 734 source tests pass, including 48 new regression methods. The 81 focused
Tradovate methods pass both from source and from the candidate wheel installed
in a fresh environment outside the checkout using an existing offline
wheelhouse. Compilation, documentation/heading links, staged patch hygiene,
numerical evidence, offline provider certification and scripted fault checks
pass. Both frozen study inventories remain unchanged.

The initial numeric matrix reproduced 48 failing subcases and six overflow
errors. Independent review also reproduced untimed/mixed-legacy certification
and inherited-exception cleanup gaps; their isolated regressions and rechecks
pass after repair. The first full-suite attempt caught the new fixture missing
from Doctor's required-resource manifest; the manifest is updated and the
complete suite passes. No failed attempt is counted as acceptance evidence.

The reviewed runtime commit is
`a3b10cbdd1b3c5404a6443031436b6fc1f3e7229`. Its clean-export wheel SHA-256 is
`46667906102bf03497aa16535ba44e0e7cc96a8905cceae51c65b6ec90177f61`.
Twine, installed `pip check`, offline Doctor, fixture-lab, refusal without the
network acknowledgement and exact tested-module/resource byte comparisons pass.
This is a candidate verification build, not a new release or study cohort.

The original PR #10 remains the integration vehicle with its contributor
history retained. Its closing reference to #4 is removed. This packet closes
the bounded offline implementation with the maintainer-authorized merge,
conditional on final-head Ubuntu/macOS Python 3.11/3.12 hosted checks and the
final independent review passing. The merged-tree full-suite, clean checkout,
local/origin/GitHub equality and issue #4 OPEN checks are retained afterward in
`dist/tradovate-offline-pr10/2026-10-18/summary.json`.
Actual sanitized Tradovate ES/NQ payloads and broader provider qualification
remain separate open outcomes; readiness remains `scaffold`.

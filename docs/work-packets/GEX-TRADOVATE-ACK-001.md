# GEX-TRADOVATE-ACK-001 — Complete Acknowledgement Frames

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: "Open — offline verified; protected-branch integration pending"
baseline: main@06ea877
branch: codex/tradovate-ack-frames
created: 2026-10-11
packet_owner: project maintainer
external_outcome: "Open — actual Tradovate ES/NQ payload observation"
```

## Authorization And Scope

The maintainer explicitly requested repair of the reproduced acknowledgement
frame bug, regression tests, documentation, commit and merge. Keep
[issue #4](https://github.com/zrack/gex-terminal/issues/4) open until actual
Tradovate payloads are available. This separate offline repair does not accept
or change contributor [PR #10](https://github.com/zrack/gex-terminal/pull/10).
No live connection, credentialed capture, provider readiness promotion, version
change, tag or release is authorized. L3 applies because the acknowledgement
gate also handles authorization and entitlement failures.

## Contract And Acceptance

Tradovate WebSocket frames contain arrays of events. A matching successful
acknowledgement must not discard later market-data or error events in its
frame. Preserve market-data event order, request-ID matching and the existing
failure behavior. A matching failed response or an `error`/`md/error` event in
the acknowledged frame prevents the operation from being reported successful.
Authorization/subscription state transitions remain gated on successful
acknowledgement processing.

Regressions must reproduce quote loss and missed errors in the original code,
cover acknowledgement/data/error ordering and unrelated request IDs, and
exercise the complete scripted session through production normalization and
consumer delivery. Use synthetic, in-memory frames without provider access.
Preserve INV-01 through INV-08 from the
[adoption profile](../SAED_ADOPTION_PROFILE.md).

## Verification And Recovery

Run focused acknowledgement, adapter, protocol and certification tests, the
full source suite, compile, documentation destinations, numerical evidence and
offline provider certification. Obtain independent review and passing hosted
checks, merge through a PR, then verify clean merged main. GitHub owns exact
commit and check identities; this packet owns technical acceptance and scope.
Revert the repair merge for recovery; no user-data migration occurs.

## Local Verification — October 11, 2026

- Eleven new regression methods cover 84 constructed cases. The final test file
  produced 44 failing cases against an isolated archive of baseline `06ea877`;
  all pass with the repair. Cases cover ES/NQ, authorization and subscription,
  quote ordering, request correlation, matching rejection, error events,
  duplicate success, malformed quotes, timeout and cancellation.
- Full scripted sessions route production-normalized quotes into the real
  consumer, preserve separate trade/OI state and verify success/failure lifecycle
  marks and socket cleanup. Existing positive-trade source selection is retained.
- All 614 source tests passed. The 38 focused acknowledgement/Tradovate/document
  tests, compile, patch hygiene and independent review passed. Numerical evidence,
  twelve offline Databento cases and seven provider fault cases also passed.
- The candidate wheel passed Twine validation and its adapter bytes match the
  tested source. The package version and release tags are unchanged.
- Generated logs, reports and candidate-wheel identity are retained locally under
  ignored `dist/tradovate-ack-verification/2026-10-11/`. These are synthetic
  implementation checks; hosted checks and merged-tree verification remain the
  technical integration gates.

## Evidence Ceiling

Offline tests prove handling of the constructed frame sequences. They do not
establish actual Tradovate payload shape, ES/NQ availability, entitlements,
native IV, live authentication or live certification. Tradovate remains
`scaffold`; issue #4 and its actual-payload requirement remain open.

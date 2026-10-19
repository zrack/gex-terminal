# GEX-TRADOVATE-CAPTURE-001 — Read-Only Raw Evidence Collector

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
baseline: main@b50dfc3df3fb87c49e754221c4aac855752b1143
created: 2026-10-19
packet_owner: project maintainer
external_outcome: "Open — actual sanitized Tradovate ES/NQ payloads and mapping validation"
```

## Authority And Scope

The maintainer requested a read-only Tradovate raw-payload collector, regression
tests, documentation, commit and merge, while explicitly keeping
[issue #4](https://github.com/zrack/gex-terminal/issues/4) open until actual ES/NQ
payloads are captured and validated. This packet authorizes implementation and
offline verification of that tool. It does not authorize a credentialed capture
during development, purchase data/API access, retain provider data, or perform
account/order operations.

L3 applies to the explicit network gate, capture-policy authority, credential
exclusion, private-file creation and bounded resource ownership. The collector
is a separate CLI evidence workflow. It preserves raw eligible contract and
market-data observations before normalization, without changing consumer/model
state, the production adapter's mapping, certification thresholds, or `scaffold`
registry readiness. Frozen studies, participant handoffs, package version and
immutable release tags remain outside this slice.

## Acceptance And Recovery

1. `tradovate-capture` requires explicit `--ack-live-network`, valid policy,
   supported symbol/environment, valid limits and a new private output directory
   before opening a provider connection. Existing outputs cannot be overwritten.
2. Network operations are constrained to authentication, allowlisted read-only
   contract discovery/chain queries and market-data protocol operations. No
   account, personal-user, order or position queries are part of the workflow.
   HTTP redirects are disabled. Before any WebSocket application message, pin
   authorization to the final secure `md.tradovateapi.com:443/v1/websocket`
   endpoint with no user information; unknown/mismatched targets fail closed.
   The WebSocket library may make unauthenticated redirected handshakes before
   this final check; no token may be sent before the endpoint passes.
3. Retain provider field names/types and observed ordering in eligible REST and
   WebSocket evidence. Exclude authentication material, tokens, headers and
   outgoing WebSocket frames. Record safety omissions and malformed/limit/error
   outcomes without echoing provider text or credentials into public diagnostics.
4. Bound the total observation window, requests, maturities, subscriptions,
   frames, record size and stored evidence. Own and await network cleanup; keep
   partial/error outcomes distinguishable from completed evidence. Retain policy
   identity, file hashes, exact configuration and explicit proof limits.
   Retrieve owned receive and heartbeat failures even when they occur together,
   preventing abandoned-task exception logs from exposing arbitrary provider text.
5. Add deterministic mocked regressions for ES/NQ selection, raw preservation,
   preflight refusal, mixed protocol frames, sensitive-material exclusion,
   malformed responses, bounds, failure/cancellation and cleanup. No test needs
   a credentialed feed or represents a synthetic response as an observed one.
6. Update the canonical operator, governance, mapping and architecture guides,
   documentation routing, roadmap and changelog. Document access/rights decisions,
   private storage, manual review, separate actual ES/NQ runs and the remaining
   issue #4 acceptance gate.
7. Pass focused/full tests, compilation, local link/heading checks, patch hygiene,
   independent review, applicable offline model/provider gates and installed-wheel
   verification. Commit on a `codex/` branch, pass final-head hosted checks, merge,
   verify clean synchronized main and issue #4 OPEN, and run the merged-tree suite.

Recover by reverting this bounded integration. No normalized data migration or
existing research-store mutation is required. Private raw observations, once an
operator later authorizes collection, remain subject to the operator's retention
and sharing decisions; reverting software does not delete them.

## Evidence

Technical implementation and offline verification are complete. All 776 source
methods pass, including 42 new collector/CLI/safety regressions. The focused
collector plus documentation-link run passes 47 methods. Compilation, patch
hygiene, seven model properties, seven scripted provider faults and the numerical
model gate pass; predictive validity remains unmeasured. Independent review
verified endpoint pinning before token transmission, mixed-frame preservation,
strict resource limits and simultaneous task-failure cleanup.

A candidate wheel built from the reviewed source passes all 42 new methods from
a fresh environment outside the checkout, installed using an existing offline
wheelhouse. Twine, installed pip check, Doctor, fixture-lab, CLI help and refusal
without network acknowledgement pass. All 122 packaged source/resource files
match both the reviewed working tree and installed bytes. Candidate wheel SHA-256:
`d78465ef1b51d3aa2b976426e105f7814a4256650055d426afd65aa84436c851`.
This verification build does not change version 0.6.0 or publish a release.

The first full-suite attempt encountered sandbox-denied local listeners; its
failure log is retained and is not acceptance evidence. The suite passes with
its inert loopback servers permitted. Earlier candidates superseded by final
review fixes remain separately identified. No test opened a provider connection.

Integration is conditional on the exact final head passing the existing four-job
Ubuntu/macOS Python 3.11/3.12 matrix. The final commit/merge identities, hosted
checks, merged-tree suite, clean synchronization and issue #4 OPEN verification
are retained in `dist/tradovate-raw-capture/2026-10-19/summary.json` after integration.
The technical closeout covers this collector only. Actual authorized ES/NQ
collection, permitted sanitized derivatives and production mapping validation
remain open; no actual provider payloads were captured by this work.

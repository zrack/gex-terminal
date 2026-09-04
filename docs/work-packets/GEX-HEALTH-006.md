# GEX-HEALTH-006 — TUI Refresh Teardown Ownership

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: active
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: pull-request reviewer and hosted CI
baseline: codex/gex-050-release-record@dcb75ea
branch: codex/gex-health-006
created: 2026-09-04
```

## Observed failure and authority

PR #26 pull-request CI run `33923631319` failed in its Linux Python 3.12 test
job while its branch checks passed. The Python 3.11 matrix job was cancelled by
fail-fast during its installed-wheel step; it did not independently reproduce
the defect. In Python 3.12, a periodic `refresh_terminal_data` call was still
awaiting the consumer when the Textual test app began teardown. It then resumed
after the application screen's widgets had been pruned, and `_render_lifecycle`
raised `NoMatches` while querying `#feed-websocket`. The three observed errors
reached Demo Lab pack generation and the first-run assumption-controls test;
they are one asynchronous lifecycle race, not evidence that those workflows
have independent model defects.

The maintainer authorized a bounded lifecycle-ownership repair in the TUI and
deterministic regressions. This packet does not authorize model, consumer,
replay-writer, provider, artifact, documentation-index, version, release, live
data, credential, or readiness changes.

## Invariants

- `H6-01` — The periodic refresh timer and initial deferred refresh belong to
  the mounted application screen, whose message-pump closure stops them before
  its widgets are detached.
- `H6-02` — A refresh that crosses an await boundary may render only when the
  same mounted application screen still owns the widgets it began with.
  Teardown or screen replacement invalidates that render without
  relabeling the consumer result as displayed.
- `H6-03` — Exceptions raised by consumer work or by rendering into a still
  current mounted screen remain visible. Do not catch `NoMatches` broadly, add
  a blind delay/retry, or suppress unrelated render defects.
- `H6-04` — Manual refresh, periodic refresh, terminal resize, replay switching,
  and assumption changes keep their current behavior while mounted.
- `H6-05` — The H3 replay source-task transition remains separately owned:
  teardown must not cancel, replace, or hide failures from `_source_task`.

## Acceptance

1. A deterministic test pauses consumer snapshot work, begins a refresh, exits
   or unmounts the test application, then releases the pause. The refresh must
   finish without querying widgets from the detached/default screen and without
   leaking an asynchronous exception.
2. A mounted-screen test proves an unexpected render exception still
   propagates; the repair is lifecycle-aware, not blanket exception handling.
3. Existing replay-ownership and first-run controls continue to pass, including
   source-task failure visibility and replacement ordering.
4. The focused TUI, Demo Lab, terminal-size, screenshot, and replay-ownership
   tests pass. The full suite and compilation pass on the isolated branch.

## Evidence ceiling and recovery

Passing evidence establishes deterministic local Textual lifecycle ownership
for the tested refresh boundaries. It does not establish every terminal/runtime
scheduler interleaving, live-provider operation, customer usability, or release
acceptance. Recovery is a reviewed revert of this packet's TUI/test change; no
stored research, provider state, or user data is migrated or deleted.

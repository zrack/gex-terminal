# GEX-HEALTH-003 — Replay Writer Ownership

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
packet_owner: project maintainer
baseline: 4d58f89
branch: codex/gex-health-003-replay-ownership
created: 2026-09-04
```

The maintainer's September 4 offline-work authorization includes H3. Preserve
INV-01 through INV-08: consumer remains sole market-state owner, and switching
session must never mix sources. No live data or new provider is in scope.

## Acceptance and design

The CLI passes the active writer task to the terminal. A replay transition is
serialized; it validates the new input, cancels and awaits the previous writer,
and only then changes configuration or resets state. A failed old writer blocks
replacement and is still reported at CLI shutdown. Capture and live modes
cannot switch. Cancellation must settle adapter cleanup before new data enters.

Public CLI regressions exercise active fixed-delay and event-clock streams,
switch through the terminal, and prove no old-only strike reaches replacement
state. Existing idle-switch and capture/shutdown tests must continue passing.

## Verification and recovery

Focused lifecycle tests, full regression, compileall, diff hygiene, independent
review, hosted checks, contributor merge, and clean-main regression. Revert the
merge to recover prior behavior; no artifact migration occurs.

## Evidence

- 19 focused replay/terminal/capture tests passed, including full CLI ownership
  regressions for both replay clocks and failed-source preservation.
- All 316 tests, source compilation, and diff hygiene passed on the branch.
- [PR #21](https://github.com/zrack/gex-terminal/pull/21) passed all four hosted
  Python 3.11/3.12 checks and merged as `ba6319203f41f47b549f3637d792cf1f3daed57a`.
  Clean main at that merge passed all 316 tests and compilation with no changes.

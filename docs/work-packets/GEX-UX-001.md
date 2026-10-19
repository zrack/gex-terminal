# GEX-UX-001 — Replay Picker Keyboard Routing

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L2
status: closed
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent reviewer and hosted CI
baseline: main@72d68f47a41c2c330351476cef99b48411f9fe3d
branch: codex/replay-picker-keyboard
created: 2026-09-13
```

## Authority and scope

The maintainer authorized a clean pull, replay-picker repair with real-keyboard
regressions, canonical documentation/roadmap updates, commit, pull-request merge
and synchronization with `origin/main`. This is a bounded offline interaction
repair. It does not authorize a new release tag, package-version change,
deployment, live observation, credential use or readiness promotion.

## Baseline and design

With the strike table focused, `p → Down → Enter` opens the browser but does not
move its selection or load a replay. The focused Textual DataTable consumes the
ordinary application navigation bindings. Existing first-run tests call action
methods directly and therefore do not exercise this event-routing boundary.

Route picker navigation ahead of table bindings only while the picker is open
on the current dashboard. When closed or another screen is active, preserve
that screen's normal keyboard behavior. Retain the existing replay-loading,
writer-settlement, live-mode and capture restrictions; do not change model,
consumer, catalog, artifact or provider contracts.

## Acceptance

1. Real `pilot.press` events open, browse up/down (including wraparound), and
   load the selected bundled session from a focused table. Check loaded path,
   instrument, multiplier and actual consumer data, not just the browser flag.
2. Exercise both first-run/demo and active-replay replacement at compact
   140×42 and larger 180×54 terminal sizes.
3. Escape and repeated `p` close without loading; reopening works. Table
   navigation and Enter resume their normal behavior after close/load.
4. A pushed screen retains its navigation; resize/return preserves the picker.
   Live mode and active capture cannot use the keyboard path to load a replay.
5. The new regression fails on baseline, then focused tests, the full suite,
   compilation, documentation links, independent review and hosted checks pass.
   Verify the clean merged tree and remote commit after merge.

## Evidence ceiling and recovery

Automated key events establish the tested Textual interaction behavior, not
native-terminal accessibility, unaided customer acceptance, live reliability or
predictive validity. Six observed offline first-use sessions remain the next
product gate. Recovery is a reviewed revert; no user files or research data are
migrated or removed.

## Verification and closeout

- Baseline: the new real-keyboard selection regression failed at both 140×42
  and 180×54 on `72d68f4`; after `p → Down`, the selection stayed
  `zero-gamma-flip` instead of moving to `expiration-compression`.
- Implementation: priority navigation bindings are enabled only while the
  picker is open on its dashboard. The `p` binding also stays dashboard-scoped.
  Binding refreshes keep footer hints synchronized after toggle, Escape and
  successful loading. The existing loader and source-settlement code is intact.
- Six new keyboard regressions cover both terminal sizes, ES-to-NQ replacement,
  wraparound, cancellation, footer and normal table selection, pushed-screen
  keys and resize, live/capture restrictions, and missing/malformed-file retry.
  The existing fixed/event-clock CLI source-replacement test now uses keyboard
  events rather than direct actions/index mutation.
- Local macOS ARM64, Python 3.12.13, Textual 8.2.7: 23 focused tests and the
  complete 431-test suite passed. Compilation and patch hygiene passed.
  An independent reviewer found no blocking issues and repeated the eight
  keyboard/source-ownership tests successfully. A follow-up table `RowSelected`
  assertion directly observes Enter falling through to the focused table.
- Independent installed-wheel verification passed outside the checkout on
  macOS ARM64/Python 3.12.13: real keys loaded ES ×50 then NQ ×20, preserved
  closed-table navigation, and passed version and `pip check`. Offline doctor
  exited 0 with required checks passing and only two unselected optional-SDK
  warnings (IBKR and yfinance absent).
  The isolated environment reused dependency packages; it is not a clean-machine
  installation study. Candidate wheel SHA-256:
  `329fab009339a367e4cf513b07b33429ee37816ac9672324c152098a2a9c7090`.
  Its package source matches repair commit `54a720e`.
- All four Linux Python 3.11/3.12 push and pull-request checks passed for that
  commit: [push run](https://github.com/zrack/gex-terminal/actions/runs/34766738374)
  and [PR run](https://github.com/zrack/gex-terminal/actions/runs/34766741383).
  These include fresh installed-wheel commands, build validation and the
  offline install/recovery lifecycle.
- [PR #27](https://github.com/zrack/gex-terminal/pull/27) merged as
  `b5ecfb1ee6526999576fd18fc9d84a11fa708342`. Clean pulled main at that commit
  passed all 431 tests, compilation, documentation links and patch hygiene;
  local main and `origin/main` matched. Technical implementation is closed.
  Subsequent documentation closeout changes no application or test code.
- Package version remains `0.5.0`, and the original `v0.4.0` and `v0.5.0` tags
  are unchanged. No new tag, publication, deployment, live observation or
  real-user study was performed. Freeze a reviewed repaired wheel before
  collecting the next six observed offline task sessions.

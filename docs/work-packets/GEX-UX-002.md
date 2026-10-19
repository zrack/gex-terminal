# GEX-UX-002 — Easier Setup And Terminal Experience

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent reviewer
baseline: main@f4df041665ad360f0d37fd75f021e474e6a4c304
branch: codex/deployment-ux-polish
created: 2026-09-26
```

## Authority And Scope

The maintainer requested a deployment review, implementation of easier setup,
and a stronger visual and interaction experience. This packet covers the
existing local terminal application: a reviewed-wheel setup helper and launcher,
a repeatable local handoff folder, and improvements to dashboard hierarchy,
window-size adaptation, replay selection, keyboard help and export feedback.
Installation lifecycle changes receive L3 rigor even though the regular wheel
remains the package format and source of installed code.

The original request authorized implementation and disposable local
installation. The September 26 follow-up explicitly authorizes documentation
updates, commits, a pull request and merge to `origin/main`. Merge follows
independent review and successful final-head hosted checks; it does not require
a further approval round. No provider connections, participant observation, credentials,
automatic updates, system Python changes, telemetry, new hosted service,
package publication or release tag are involved. The frozen September 20 study
bundle remains unchanged. This is a new build, not a replacement of its
historical observations or materials. Preserve INV-01 through INV-08.

## Review Findings And Design

Fresh baseline captures at 180×54, 140×42 and 120×40 and keyboard probes found:

1. Setup requires manual wheel selection, environment creation and activation;
   the next launch depends on shell state. A caller's `.env` can break even an
   explicitly selected demo before launch. A wheel alone does not include its
   dependencies, and version `0.5.0` is insufficient to distinguish later builds.
2. At 120×40 the app displays only resize guidance. At larger sizes, secondary
   diagnostics consume space while metric notes and replay choices are clipped.
3. The replay picker has no dedicated focusable list keeping selection visible.
   A normal data refresh resets table selection to the first row.
4. A few labels imply more than the data: raw volume is called OI and a
   compatibility level is described as a volatility inflection. Static symbol
   labels resemble controls, while the first-run instructions disappear as soon
   as demo data loads.

Keep one local Python/Textual application. A small standard-library installer
creates only an explicitly selected, owned application folder. It checks the
supplied wheel identity, installs and verifies a new environment before changing
the active launch target, and stores research separately. The launcher pins an
explicit synthetic replay and isolates initial configuration from ambient data
provider settings. An optional complete wheelhouse supplies dependencies without
network access. This is not a new distribution registry or an auto-updater.

Build the terminal's visual identity around legible high-contrast typography,
restrained amber and cyan accents, explicit source/instrument context and clear
primary actions. Use a real scrollable replay picker and contextual help.
Support smaller windows only where fresh visual and interaction checks establish
readability; all detailed model and quality information must remain reachable.

## Acceptance

1. An end user can install a supplied reviewed wheel and reopen its offline
   dashboard without Git, shell activation, provider credentials or admin rights.
   Record exact wheel/source/Python identity and explain dependency downloads.
2. Checksum or installation failure preserves the previous working launch target
   and separate research. Repeated setup safely reuses a matching healthy build.
   Reject unknown owned-folder state rather than deleting or adopting it.
3. Test spaces in paths, ambient configuration, repeated install, wrong/corrupt
   wheels, failed update and research preservation in disposable locations.
4. At each newly supported size, metric values, current source, table net values,
   replay selection, quality details and controls are readable or explicitly
   reachable. Capture and inspect current screens; geometry alone is insufficient.
5. Keyboard replay selection keeps the selected item visible, restores table
   focus on dismissal, respects capture/live restrictions, and preserves source
   task settlement and screen ownership. Normal refresh preserves selected strike.
6. Source tests, compilation, documentation links, build/Twine, installed-wheel
   rehearsal and independent review pass. Record local versus hosted results
   separately. No usability acceptance or accessibility compliance is inferred
   from automated checks or screenshots alone.

## Recovery And Evidence

Code changes can be reverted as one bounded slice. The launcher selects only a
successfully verified environment; an earlier reviewed wheel can be reinstalled
without deleting separate research. No data-schema migration is introduced.

Fresh local baseline screenshots and probes are retained under ignored
`dist/deployment-ux-review/before/`. Installation
instructions remain owned by [First Run](../first-run.md); current source
boundaries remain owned by [Architecture](../architecture.md).

## Local Verification And Handoff

- Full source suite: **479 tests passed**, including installation/reuse,
  failed update preservation, launcher PTY behavior, small-window interaction,
  source labeling, export feedback and documentation links. Compilation and
  whitespace checks passed. Python 3.11 syntax and eight CI shell blocks were
  also checked locally; this is not a hosted Python 3.11 execution result.
- Independent review found no unresolved issues after receipt validation,
  atomic active-selection publication, payload verification, interpreter
  selection and live-source labels were repaired.
- Matched before/after demo captures at 180×54, 120×40 and 140×42 were inspected.
  Additional small-window and overlay checks cover 100×32 and 120×36. Current
  tracked dashboard and replay-picker SVGs come from the running application.
  Commands, dimensions and file hashes are recorded in
  `dist/deployment-ux-review/comparison/manifest.json` and
  `dist/deployment-ux-review/final-previews/manifest.json`.
- The prior-wheel installation rehearsal passed with a complete macOS ARM64 /
  CPython 3.12 wheelhouse, downloads disabled, caller/research configuration
  contamination, repeat setup, separate research and ES/NQ exports. It proves
  the setup mechanism independently of the redesigned UI. Final distribution,
  installed-UI and reusable-launcher verification are recorded separately in
  `dist/deployment-ux-review/closeout.json`, including exact build identities.
- All **219** frozen September 20 study-file checksums remained unchanged.
- Final wheel/sdist build and Twine checks passed. The handoff installs source
  `b4c37d5481ac3917d58c47bea9e8b5611a16b2e9`, wheel SHA-256
  `d82d4f1ed0cc8278286de22919e3f338b0014d8a080ade5afc7787f84d6e3ce6`,
  on macOS ARM64 / Python 3.12.13 with its supplied dependency wheels and no
  downloads. Repeat setup reused the healthy installation; all 94 application
  payload files, doctor and ES/NQ launcher exports passed. Eighteen installed-UI
  checks passed from a neutral folder, with four actual 100×32 captures inspected.
  Installed NQ Demo Lab generation, verification and reproduction passed, as
  did the installed numerical gate. The final documentation-only follow-up
  adds the explicit installed CLI path for that advanced workflow; its five
  documentation-link checks passed.

## Hosted Acceptance And Integration

Source `5c78391a860abab0f95ec41d397cbda78d0289d5` passed all four Ubuntu/macOS
and Python 3.11/3.12 jobs in
[PR #31](https://github.com/zrack/gex-terminal/pull/31), including the new
setup, repeat-install, doctor and launcher-export checks. Both the
[pull-request run](https://github.com/zrack/gex-terminal/actions/runs/36295333103)
and the [branch run](https://github.com/zrack/gex-terminal/actions/runs/36295331609)
completed successfully, including synthetic evidence collection and uploads.

This packet closes technical shipment with PR #31's merge, conditional on all
final-commit hosted checks passing. The PR owns final checked-source and merge
identities. Final documentation-only closeout changes must pass the same matrix
before merge. Clean merged-main regression, hosted outcome and remote equality
are recorded locally in `dist/deployment-ux-review/merged-closeout.json` after
merge. The original local handoff retains its recorded wheel/source identity.

The local handoff contains the reviewed wheel, installer and platform-specific
dependency wheels. Package publication, observed-user acceptance and live-data
verification remain outside this slice. No version or readiness promotion is
implied by merging these setup and interface improvements.

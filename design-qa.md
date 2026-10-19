# Market Wind Tunnel Design QA

## Reference And Rendered Evidence

The selected direction is the Exposure Landscape concept, with Scenario Compare
and Fragility Atlas implemented as additional tabs. The source landscape image
is the generated `exec-b0c115bc-72d8-47c0-89f3-be62d1ce4d39.png` in this task's
generated-images folder. It is illustrative, not numerical evidence.

The actual implementation capture is [the committed landscape](assets/market-wind-tunnel.png).
It uses ES Wind Tunnel Lab's final checkpoint, volume proxy and +2 absolute IV
points. Source and implementation images are both 1487×1058 pixels. The desktop
browser viewport was 1487×1058 CSS pixels at device scale 1 for this capture.
The actual page has no horizontal overflow. A second 390×844 CSS-pixel capture,
also at scale 1, verifies the stacked layout with no horizontal overflow.

Both images were placed side by side in one browser-rendered comparison, not
judged from separate screenshots. Local evidence is retained under
`dist/wind-tunnel-development/design-comparison/` and `screenshots/`.
Intermediate full-page browser captures had inconsistent raster scaling and
were excluded from fidelity judgment; the committed capture uses the measured
viewport without full-page stitching.

## Visual Review

The implementation retains the navy workstation, amber/cyan scenario language,
large exposure plot, adjacent controls and replay footer. Tabs, source selection,
explicit baseline/scenario metrics and supporting tables add product navigation
that the static concept did not include. The calculated surface differs from
the illustrative smooth wave: exact front-expiry removal creates a real
discontinuity. The geometry must follow calculated values.

The initial render devoted too much height to the hero and showed a small scene.
The revised desktop spacing and camera place the plot, all primary controls,
search action and replay/save footer in the reviewed desktop viewport. Narrow
screens deliberately scroll vertically. The initial narrow metric columns
overflowed; they now stack and wrap complete values.

## Interaction Checks

- All three examples execute in the real browser. The broad search evaluates
  35 points and finds a nearest tested wall change at −25 spot points and zero
  IV shift. The narrow grid evaluates nine points without a wall change.
  Expiry removal changes the displayed ES wall from 6000 to 6050 and modeled
  net exposure from about +420.12M to +46.84M.
- 3D and selectable 2D views render real calculated points. Changing IV to +2
  updates net exposure to about +391.47M and keeps the source unchanged.
- Saving and reopening a named search verifies and restores the exact 7×5
  sampled grid. Importing its JSON verifies and restores the same search.
- A browser round trip exposed changed numeric formatting in signed receipts.
  Reopen/import now preserve raw JSON text. The regression verifies raw HTTP
  save/read/export/reproduction bytes and CLI loading; transformed numbers are
  rejected. Browser download destination remains managed by the browser.
- Loaded examples display their real grid dimensions. Editing bounds prepares
  a new grid. Pending or failed recalculation clears stale save ownership.
- Keyboard activation, arrow navigation between tabs and visible focus work.
  Number inputs accompany sliders; strike and tested-cell tables provide text
  alternatives. Source details expose contract records and assumptions.
- Normal refresh retains the tab's capability and reloads the workbench. Missing
  or invalid capabilities are covered by HTTP tests and explicit UI guidance.

Browser console inspection returned no error or warning entries during the
reviewed flows. HTTP, CLI, numerical and packaging tests supplement browser
inspection; no real participant observation or cross-browser usability claim
is made. WebGL rendered on this host; selectable 2D mode was also exercised.
Automatic fallback for an actual GPU failure was not forced in browser QA.

## Final Result

**Passed for the reviewed local browser and viewports.** No unresolved blocking
visual or interaction findings remain. This verifies the implementation and
synthetic workflows; predictive validity and unaided user acceptance remain
unmeasured. [GEX-WIND-001](docs/work-packets/GEX-WIND-001.md) owns release gates.

## 2026-10-18 Handoff And Guided Intake Supplement

This supplement records the additional synthetic workflows shipped in
[PR #40](https://github.com/zrack/gex-terminal/pull/40) and
[PR #41](https://github.com/zrack/gex-terminal/pull/41). The original visual
comparison, captures and conclusions above retain their original build and
viewport scope. This closeout reviews the retained evidence; it does not claim
a new application run, refresh the front-door screenshots or change a frozen
study build.

### Evidence And Build Identity

The handoff evidence is retained locally under ignored
`dist/wind-tunnel-handoff/2026-10-18/`. Its `summary.json` binds the reviewed
wheel to source commit `5f4ff9f3cfd55bb00d97b3d05cb920a027e824cb`, wheel SHA-256
`ae90358b8b99f50b3d87ea5e2b4bbd850380e6ade2817facfd5ed90c50a22b58`
and merge commit `cd81cc71075c64a31899c59cc9222f5f0be9ccb7`.

The intake evidence is retained locally under ignored
`dist/guided-intake/2026-10-18/`. Its `execution.json` identifies source commit
`0ddfbc4c0d94dd09935590ccb00db5d980863151`, source tree
`92aa7af9f670801c563ee256c09764bc12cde8d8` and wheel SHA-256
`f1d5aa236d69a1c1d6514e6a5bf98d38a736bd28a6469ed2dd10057b573f0fc6`.
The merged feature record is `0dab6bb6a39ce3077338c6b14f5e5c7a53213a46`.

These are the actual decoded raster dimensions. The historical files have
`.png` names but contain JPEG bytes; their names and hashes are preserved.
Raster size alone does not establish CSS viewport or device scale.

| Evidence file | Raster size | SHA-256 |
| --- | --- | --- |
| `wind-tunnel-handoff/2026-10-18/checkpoint-browser.png` | 1280×720 | `0c91f1ddc3f00da47585d0d585025cd38015f55cbb087cf056b5e53699b6c37a` |
| `wind-tunnel-handoff/2026-10-18/checkpoint-browser-full.png` | 1280×1177 | `8b35e457ef9782890554ad96f10ed3e82beb0be63f7d08142177f8b5497eefa6` |
| `guided-intake/2026-10-18/browser-inspection.png` | 1280×720 | `7fdd489adb92e39cb56d90233058e801e2f397bd22a830b83b67236b77d52671` |
| `guided-intake/2026-10-18/browser-comparison.png` | 1280×720 | `7b4417922a6f72b28cc59540c0b279bcd47a2e1217f95aca393817b397f1be2a` |
| `guided-intake/2026-10-18/browser-fresh-reproduced.png` | 1280×720 | `7b4417922a6f72b28cc59540c0b279bcd47a2e1217f95aca393817b397f1be2a` |

Paths in the table are relative to ignored `dist/`; these local proof files are
not assets shipped in Git or the public documentation. The comparison and
fresh-reproduced images have identical bytes, so the second image is not
independent proof of server restart. The execution record supplies that check:
it records stopping the source server and reproducing each receipt through a
fresh server with an empty workspace.

### Reviewed Behavior And Limits

- Terminal's explicit **`w`** action opens a fixed demo/replay checkpoint. The
  retained NQ comparison shows the frozen source time, **Terminal selected
  proxy**, disabled single-checkpoint playback and an IV +1 scenario. The
  full-height capture also shows the successful save/reopen message.
- Guided intake exposes **Choose and verify**, permission acknowledgement and
  **Inspect the verified inputs**. The retained NQ inspection shows integrity,
  source classification and event-time bounds. Its scrollable dialog preserves
  a visible close action; the first raster intentionally shows only the upper
  portion, so it is not evidence that every checkpoint control fits at once.
- The captured-checkpoint comparison retains source time and synthetic status
  while changing the scenario. The installed-wheel execution record covers
  ES and NQ intake, prefix selection, scenario calculation, export and fresh
  empty-workspace reproduction. Terminal handoffs were rehearsed at 140×42
  and 180×54 cells in the same independent execution record.
- Local capture verification does not establish authenticity, provider
  certification or permission to redistribute inputs. The server projects
  calculation fields only; saved receipts still require review before sharing.
  Later Terminal events do not update an already frozen checkpoint.

The historical original QA includes a 390×844 narrow-browser check. These
handoff/intake captures add desktop evidence only; they do not extend that
narrow-screen result to the new dialog, establish cross-browser coverage or
replace observed participant sessions. Both the September and guided-intake
study kits retain their own frozen identities. Six observed sessions remain
an external usability gate; automated rehearsal is not participant evidence.

### Component Diagram Reconciliation

`assets/workbench-components.svg` now distinguishes standalone/Both's separate
Python process from Terminal's owned in-process handoff listener. It also names
the verified local-capture input path and immutable checkpoint boundary. The
canonical contracts remain in [Architecture](docs/architecture.md#c4-views).
The diagram's accessible description follows the same ownership rules.

A true PNG render and a source-SVG SHA-256 manifest are retained locally under
ignored `dist/docs-closeout/2026-10-18/`. This is a diagram render for label and
arrow inspection, not application QA or a new screenshot of either study build.

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

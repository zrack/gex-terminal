# Visual Assets

Current visuals describe the two-component local product: Terminal and Market
Wind Tunnel. Screenshots use bundled synthetic inputs. Architecture and social
artwork explain the product; they are not screenshots or measured results.

## Current Assets

| Asset | Source and owner | What it shows |
| --- | --- | --- |
| [Terminal](gex-terminal-actual.png), [source SVG](gex-terminal-actual.svg) | Current source CLI, seeded demo, 140×42 cells; [First Run](../docs/first-run.md) | Actual Terminal with strike rows, source health, pricing qualifications and coverage availability |
| [Wind Tunnel landscape](market-wind-tunnel.png) | Actual browser; ES Wind Tunnel Lab, checkpoint 33, Volume proxy, IV +2, price/time unchanged | Original and recalculated synthetic exposure surfaces, coverage and accepted-IV age |
| [Model comparison](wind-tunnel-model-comparison.png) | Actual browser; Terminal-exported `nq-research-loop` checkpoint, +100 price, +1 IV point, +30 model minutes | Separate default/directionalized cards, net signs, walls and observation ages |
| [Focused strikes](wind-tunnel-focused-strikes.png) | Same NQ checkpoint and scenario | Matched chart axes, original/scenario futures-price markers, Focused selector and exact-value access |
| [Demo pack](gex-terminal-demo-lab.svg), [replay picker](gex-terminal-onboarding.svg) | Maintained synthetic preview command; bundled `zero-gamma-flip`; [Demo Lab](../docs/demo-lab.md#contributor-preview) | Generated research graphic and actual replay-picker capture |
| [Product architecture](workbench-components.svg) | Derived from [Architecture](../docs/architecture.md#c4-views) | Starter, saved sessions, independent Terminal/Wind Tunnel state and frozen checkpoint handoff |
| [Research architecture](offline-research-architecture.svg) | [Architecture](../docs/architecture.md#offline-research-flow) and [Research Governance](../docs/research-governance.md) | Input bounds, local calculation/cache boundaries, compact views, full receipts and separate research authority |
| [Social preview SVG](github-social-preview.svg), [PNG](github-social-preview.png) | Product presentation artwork, 1280×640 | Illustrative two-component product overview; no runtime or provider claim |

The screenshot runtime is source commit
`2d6a239edd509a5dde8eb5019d0b634311c1784b`, application version `0.6.0`, with
Python 3.12.13. Documentation-only changes do not restate these as captures from
a later runtime. [Visual provenance](visual-provenance.json) records current
file hashes, dimensions, source inputs and reproduction settings. The local
execution manifests remain under ignored `dist/documentation-refresh-20261019/`.
No capability-bearing launch URL is included in public provenance.

The Terminal seeded demo and the NQ comparison fixture retain legacy coverage
metadata. Their explicit “not reported” or “unavailable” coverage labels are
intentional; the images do not invent percentages. Accepted-IV age can still be
reported from qualified observation clocks. The ES landscape has separate
complete coverage metadata. Exercise style remains unknown in these older
synthetic fixtures and is shown as unqualified. These examples do not represent
the later private Databento ES/NQ captures or validate empirical pricing accuracy.

## Reproduce And Review

Use a source environment with the app's installed runtime dependencies. Keep
provider credentials and ambient configuration out of capture processes. The
maintained preview command isolates its child processes and records source,
runtime, input and asset identities:

```bash
python scripts/refresh_previews.py --include-onboarding --write-assets
```

It stages a fresh directory under ignored `dist/previews-*`, verifies the demo
pack and refreshes only the demo and replay-picker SVGs. It does not modify a
frozen study bundle or refresh either front-door screenshot automatically.

The Terminal front-door view uses the source CLI with `--demo --screenshot
assets/gex-terminal-actual.svg --screenshot-width 140 --screenshot-height 42`.
Run it through `source_command` and `clean_environment` from the maintained
preview helper, from a scratch working directory. Use the same clean source
invocation to export a new checkpoint with `--replay-session nq-research-loop
--wind-tunnel-checkpoint NEW_CHECKPOINT.json`.

For the browser images:

1. Start a loopback Wind Tunnel with bundled sources; choose **ES Wind Tunnel
   Lab**, its last checkpoint, **Volume proxy**, and IV **+2**. Capture
   **Exposure landscape** after “Calculated locally.”
2. Start a new workbench with the explicit synthetic NQ checkpoint. Open
   **Model comparison**, set price **+100**, IV **+1**, time **+30**, and leave
   expiry removal off. Wait for “Both models ready.” Capture the cards, then
   scroll to **Focused** and the two marker charts. Do not alter chart values.
3. Inspect source labels, units, assumptions, readouts, legends, clipping and
   overflow. Save native browser pixels without editing labels or numbers.
   Encode actual PNG bytes even when a capture API returns another raster format.

The landscape is a complete 1280×1432 page captured from the normal 1280×720
viewport. Its measured document width is 1280, with no horizontal overflow.
The two comparison images are 1280×720 viewport captures. The Terminal PNG is
1726×1075, rendered locally from the unchanged new SVG with Sharp. No raster
resize, chart repaint or numerical editing is applied. Fonts, SVG identifiers,
report clocks and UI timing can change on a later regeneration; these hashes
identify the reviewed files, not a promise of universal pixel identity.

Update architecture prose and C4 views before reconciling derived SVGs.
Inspect a rendered version of each diagram; XML parsing alone cannot detect
clipped text or misleading arrows. Keep overview labels legible at README
width, and keep implementation detail in the technical diagram.

## Historical Captures And Concepts

The previous current captures are preserved byte-for-byte in [history](history/).
They retain the settings and evidence ceilings of their original reviews:

- [Earlier Terminal SVG](history/terminal-before-20261019.svg) and
  [PNG](history/terminal-before-20261019.png): SVG originally entered Git in
  `b4c37d5481ac3917d58c47bea9e8b5611a16b2e9`; the reviewed 140×42 capture is
  documented in [Deployment Review](../docs/deployment-ux-review.md).
- [Earlier Wind Tunnel landscape](history/wind-tunnel-before-20261019.png):
  original source entered Git in `c6545c53268a37035167af2fba695f8cfd8bee96`;
  `d59e34203fc9d1748631b6ac61e0d9cb37d8616c` stored correct PNG encoding.
  [Design QA](../design-qa.md) preserves the original 1487×1058 review scope.
- The earlier [replay picker](history/onboarding-before-20261019.svg),
  [demo graphic](history/demo-lab-before-20261019.svg) and
  [social preview](history/social-preview-before-20261019.png) retain the
  pre-refresh bytes. Their hashes are in the provenance inventory.

`gex-terminal-mockup.png`, `gex-terminal-mockup 2.png`,
`live-gamma-regime-map-mockup.svg` and `github-social-preview 2.png` are retained
concepts or maintainer-supplied alternatives. Labels such as LIVE, dealer
regime, connectivity and OI status in a concept are illustrative. They do not
override [current status](../README.md#current-status), model semantics or
provider-readiness gates. Do not present them as current application captures.

Dated September/October study records and participant materials remain frozen.
A fresh source screenshot is implementation evidence; it does not establish
unaided usability, live access, predictive validity or trading performance.

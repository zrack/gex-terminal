# Visual Assets

This directory contains documentation graphics, generated terminal captures,
and retained visual concepts. A graphic is presentation material unless its
own source and verification record identify it as runtime evidence.

## Ownership And Reproduction

| Asset | Canonical owner and source | Evidence boundary |
| --- | --- | --- |
| `market-wind-tunnel.png` | [Wind Tunnel](../docs/wind-tunnel.md) and [design QA](../design-qa.md); browser capture of ES Wind Tunnel Lab at final checkpoint, IV +2 points | Calculated synthetic scenario, 1487×1058 desktop capture; not a forecast or live observation |
| `workbench-components.svg` | [Architecture](../docs/architecture.md#c4-views); derived overview of the Terminal and Market Wind Tunnel interfaces, shared package code and separate runtime state | Current component explanation; not a screenshot, shared-state service or new deployment |
| `offline-research-architecture.svg` | [Architecture](../docs/architecture.md#offline-research-flow) and [Research Governance](../docs/research-governance.md); maintained SVG summary of those contracts | Derived architectural explanation; not a run result or deployment diagram |
| C4 context, container and component views | Mermaid source lives in [Architecture](../docs/architecture.md#c4-views), not a separate asset copy | Two interfaces shipped in one Python package; the combined starter runs separate Terminal and Wind Tunnel processes with independent state |
| `gex-terminal-demo-lab.svg`, `gex-terminal-onboarding.svg` | [Demo Lab](../docs/demo-lab.md#contributor-preview) owns `scripts/refresh_previews.py` and its local provenance manifest | Calculated synthetic demo graphic and actual replay-picker capture for the generating source build |
| `gex-terminal-actual.svg`, `gex-terminal-actual.png` | [Deployment And Terminal Experience Review](../docs/deployment-ux-review.md), using the CLI screenshot command below; PNG is a raster rendition of that SVG | Actual 140×42 terminal with synthetic demo data; not live-market evidence |
| `gex-terminal-mockup.png`, `gex-terminal-mockup 2.png`, `live-gamma-regime-map-mockup.svg` | Retained product/visual concepts; interpretation belongs with [Product Validation](../docs/product-validation.md) | Illustrative concepts; no implementation or usability claim |
| `github-social-preview.svg`, `github-social-preview.png`, `github-social-preview 2.png` | Repository presentation artwork | Promotional illustration; no runtime or provider-readiness claim |

When changing a source boundary, update the canonical architecture prose and
C4 views first, then reconcile the derived SVG in the same pull request. The
research SVG separates workflow execution from corpus verification; manifest
and semantic-result identity belongs to orchestration, not the pricing engine.
Its accessible title/description identifies the owning guides. Inspect the
rendered SVG for clipped labels and incorrect arrows after editing.

The workbench overview describes code reuse, not a central calculation service.
Both interfaces use the installed package's consumer and engine code in their
own process. Choosing **Both** manages their launch and shutdown together;
source selections, checkpoints, scenarios and mutable state remain independent.
The browser communicates with its local Wind Tunnel server, not with the
Terminal process. The owning C4 views carry the detailed process boundaries.

Rebuild screenshots through their owning guide, recording the source commit,
command, terminal dimensions, and input fixture in the change evidence. Existing
assets are not automatically screenshots of a later study build. Use
[Study Build](../docs/study-build.md) for exact build identity and fresh rehearsal
evidence, and [Contributing](../CONTRIBUTING.md#documentation-and-diagram-ownership)
for documentation placement and validation.

The preview command stages fresh output under ignored `dist/previews-*` by
default; `--write-assets` explicitly refreshes the repository copies. Its local
manifest binds source/runtime/input identities and exact asset hashes. Inspect
both SVGs before accepting the diff. Snapshot calculations are repeatable, while
legacy replay report timestamps and terminal SVG identifiers/timing may vary.
The current preview refresh does not replace the frozen study bundle.

The front-door terminal capture uses `gex-terminal --demo --screenshot
assets/gex-terminal-actual.svg --screenshot-width 140 --screenshot-height 42`.
Run from a clean configuration with `NO_COLOR` unset for color captures; record
source and file hashes with the review. The running app continues to honor a
user's monochrome preference. The replay-picker asset uses the maintained
preview refresh command and its explicit bundled `zero-gamma-flip` input.

## Front-Door Capture Provenance

The README reuses reviewed runtime captures. It does not substitute product
concepts or imply that the Terminal and Wind Tunnel are showing one synchronized
session. Display each capture at full content width and link to the original
for closer inspection; side-by-side thumbnails make the table and controls
too small to read.

- **Terminal:** `gex-terminal-actual.svg` entered Git in
  `b4c37d5481ac3917d58c47bea9e8b5611a16b2e9`. It matches the recorded
  `after-04-dashboard.svg` hash in the local
  `dist/deployment-ux-review/comparison/manifest.json`: a 140×42 Textual capture
  of the seeded demo. That manifest identifies the edited source files used
  before their commit. The retained SVG has a 1726×1074.8 view box. Its PNG
  rendition is 1726×1075, rendered locally with Sharp from the unchanged SVG;
  no values, labels or layout were edited. The PNG fixes the displayed font
  rendering for README viewers while the SVG remains the capture source.
- **Market Wind Tunnel:** the browser capture entered Git in
  `c6545c53268a37035167af2fba695f8cfd8bee96`; commit
  `d59e34203fc9d1748631b6ac61e0d9cb37d8616c` stored it with correct PNG encoding.
  [Design QA](../design-qa.md#reference-and-rendered-evidence) owns its reviewed
  1487×1058 viewport and source settings. To recreate the view, open the local
  Wind Tunnel, select **ES Wind Tunnel Lab**, the final checkpoint and
  **Volume proxy**, then set IV shift to **+2** with spot/time shifts at zero
  and expiry removal off. Capture **Exposure landscape** at that viewport.
  Preserve the synthetic source label and omit the capability-bearing URL.

The corresponding Terminal presentation files and Wind Tunnel implementation
are unchanged at documentation baseline `5d3727652f8927d8dd7bab2f8ca171ddecd86c94`.
This establishes why the retained captures remain representative; it is not a
new runtime capture or an exact later installed-build claim. Original files
and the PNG rendition have these SHA-256 identities:

| File | SHA-256 |
| --- | --- |
| `gex-terminal-actual.svg` | `0570b981f30ae9b0160673812175e04b577c6566bc8f37069fdf1b17e7884185` |
| `gex-terminal-actual.png` | `6d7fb8c7d83e40780fb91916a925742348f60c8692d2cd4257f0f941a11e7157` |
| `market-wind-tunnel.png` | `f53012caaf1262de14330fad4e001a863a6868e4a58dcc13bcd6c39adcaf92b7` |

Documentation review renditions and their local manifest are staged under
ignored `dist/component-docs/`. Rendering the existing captures does not run a
provider, change an installed research folder or alter the frozen study build.

## Retained Concepts

`gex-terminal-mockup 2.png` and `github-social-preview 2.png` are preserved
alternate concepts supplied by the maintainer. They are not application
screenshots, live-provider certification, or evidence of observed dealer
inventory. Labels such as `LIVE`, WebSocket connectivity, OI proxy status, and
dealer regime are illustrative and do not override the readiness and evidence
boundaries in the [project status](../README.md#current-status) or
[architecture](../docs/architecture.md).

For current public documentation, prefer an asset already referenced by the
owning document or a fresh deterministic export from the repository.

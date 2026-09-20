# Visual Assets

This directory contains documentation graphics, generated terminal captures,
and retained visual concepts. A graphic is presentation material unless its
own source and verification record identify it as runtime evidence.

## Ownership And Reproduction

| Asset | Canonical owner and source | Evidence boundary |
| --- | --- | --- |
| `offline-research-architecture.svg` | [Architecture](../docs/architecture.md#offline-research-flow) and [Research Governance](../docs/research-governance.md); maintained SVG summary of those contracts | Derived architectural explanation; not a run result or deployment diagram |
| C4 context, container and component views | Mermaid source lives in [Architecture](../docs/architecture.md#c4-views), not a separate asset copy | Current source boundaries; one local Python application with local files |
| `gex-terminal-demo-lab.svg`, `gex-terminal-onboarding.svg` | [Demo Lab](../docs/demo-lab.md) owns deterministic export commands | Captured synthetic terminal behavior for the generating build |
| `gex-terminal-actual.svg` | [Replay Lab](../docs/replay-lab.md) owns its replay screenshot command | Synthetic replay screenshot; not live-market evidence |
| `gex-terminal-mockup.png`, `gex-terminal-mockup 2.png`, `live-gamma-regime-map-mockup.svg` | Retained product/visual concepts; interpretation belongs with [Product Validation](../docs/product-validation.md) | Illustrative concepts; no implementation or usability claim |
| `github-social-preview.svg`, `github-social-preview.png`, `github-social-preview 2.png` | Repository presentation artwork | Promotional illustration; no runtime or provider-readiness claim |

When changing a source boundary, update the canonical architecture prose and
C4 views first, then reconcile the derived SVG in the same pull request. The
research SVG separates workflow execution from corpus verification; manifest
and semantic-result identity belongs to orchestration, not the pricing engine.
Its accessible title/description identifies the owning guides. Inspect the
rendered SVG for clipped labels and incorrect arrows after editing.

Rebuild screenshots through their owning guide, recording the source commit,
command, terminal dimensions, and input fixture in the change evidence. Existing
assets are not automatically screenshots of a later study build. Use
[Study Build](../docs/study-build.md) for exact build identity and fresh rehearsal
evidence, and [Contributing](../CONTRIBUTING.md#documentation-and-diagram-ownership)
for documentation placement and validation.

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

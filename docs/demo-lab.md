# Demo Lab

Demo Lab generates a complete no-credential demo pack from bundled replay and
provider fixture data. It is meant for GitHub screenshots, issue attachments,
contributor onboarding, and quick offline verification before live data is
available.

## Run It

```bash
gex-terminal demo-lab demo_lab
```

Use a different replay session:

```bash
gex-terminal demo-lab demo_lab --replay-session gap-fade
gex-terminal demo-lab demo_lab --replay-session zero-gamma-flip
```

The default session is `zero-gamma-flip` because it shows the market-structure
boundary behavior more clearly than the compact demo fixture.

## Output Folder

The command writes:

| File | Purpose |
| --- | --- |
| `README.md` | Human-readable guide to the generated pack. |
| `manifest.json` | Machine-readable artifact index and top-line metrics. |
| `gex-terminal-color.svg` | Color preview generated from real replay snapshot values. |
| `terminal-screenshot.svg` | Color-themed Textual terminal capture after replaying the session. |
| `snapshot.json` | Full snapshot with metrics, strikes, expiries, and feed quality. |
| `snapshot.md` | Human-readable snapshot summary. |
| `tradingview-overlay.json` | Portable chart levels and bands. |
| `tradingview-overlay.csv` | Spreadsheet-friendly chart levels and bands. |
| `replay_lab.md` | Replay Lab report for the selected session. |
| `replay_lab.json` | Replay Lab JSON baseline. |
| `provider_fixture_lab.md` | Provider Fixture Lab scorecard. |
| `provider_fixture_lab.json` | Provider Fixture Lab JSON baseline. |

`demo_lab/` and `demo_pack/` are ignored by Git by default so local generated
packs do not get staged accidentally.

## Refresh The README Preview

The README front image is a generated color SVG. To refresh it from the current
code path:

```bash
gex-terminal demo-lab /tmp/gex_terminal_demo_lab --replay-session zero-gamma-flip
cp /tmp/gex_terminal_demo_lab/gex-terminal-color.svg assets/gex-terminal-demo-lab.svg
```

The asset uses offline replay data only. It should not contain live provider
payloads, credentials, account identifiers, or proprietary data.

## Why This Exists

The terminal itself is the product, but contributors and GitHub visitors need a
fast way to understand the workflow without installing a live feed. Demo Lab
packages the most important offline proof points in one place:

- Visual preview for the repository page.
- Color-themed terminal capture for UI review.
- Snapshot and overlay exports for trader review.
- Replay Lab report for model behavior.
- Provider Fixture Lab report for adapter-path confidence.

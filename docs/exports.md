# Export Formats

`gex-terminal` exports research artifacts from computed snapshots so users can
review levels outside the terminal without exposing credentials or live feed
payloads.

## Demo Lab Pack

Demo Lab writes the most useful offline artifacts into one folder:

```bash
gex-terminal demo-lab demo_lab
gex-terminal demo-lab demo_lab --replay-session zero-gamma-flip
```

The pack includes a color SVG preview, color-themed Textual terminal screenshot,
snapshot JSON/Markdown, TradingView overlay JSON/CSV, Replay Lab Markdown/JSON,
Provider Fixture Lab Markdown/JSON, a local README, and `manifest.json`.

Use this when preparing GitHub screenshots, attaching reproducible evidence to
issues, or onboarding contributors who do not have live market-data access yet.

## Snapshot JSON

The base snapshot export contains the computed metrics, strike matrix, expiry
breakdown, model inputs, and session metadata. It can be written as JSON, CSV,
or Markdown:

```bash
gex-terminal --demo --export gex_snapshot.json
gex-terminal --demo --export gex_snapshot.csv
gex-terminal --demo --export gex_snapshot.md
gex-terminal --replay-session zero-gamma-flip --export gex_snapshot.md
```

The snapshot is the best format for reproducible research because it keeps the
strike-level values that produced the displayed gamma wall, zero-gamma node,
call wall, put wall, and concentration band.

When a snapshot carries replay alerts or feed-quality metadata, Markdown and CSV
exports include those sections as shareable rows.

Provider injection snapshots include `provider_injection` metadata and
`feed_quality` counters:

```bash
gex-terminal inject-provider tests/fixtures/tradovate_live_sample.jsonl \
  --provider tradovate \
  --symbol ES \
  --export injected_tradovate.json
```

## Provider Fixture Lab Reports

Provider Fixture Lab reports run the bundled provider-shaped samples and export
a contributor-friendly scorecard:

```bash
gex-terminal fixture-lab provider_fixture_lab.md
gex-terminal fixture-lab provider_fixture_lab.json
gex-terminal fixture-lab provider_fixture_lab.csv
```

Markdown is best for GitHub issues and pull requests. JSON keeps the full
snapshot baseline for every provider case. CSV gives spreadsheet-friendly rows
for fixture health, parser counters, gamma wall, zero-gamma level, and message
counts.

## Replay Lab Reports

Replay Lab reports run one or more bundled synthetic sessions and export a
research artifact:

```bash
gex-terminal replay-lab replay_lab.md
gex-terminal replay-lab replay_lab.json
gex-terminal replay-lab replay_lab.csv
```

Markdown is best for issues and discussion. JSON keeps the saved final snapshot
for every replay session so future model or fixture changes can be compared
against a baseline. CSV gives spreadsheet-friendly session, alert, and
comparison rows.

## Historical Journal Reports

Historical Research Journal reports export selected replay-session studies saved
under the local `research_journal/entries/` directory:

```bash
gex-terminal journal add --replay-session trend-day
gex-terminal journal add --replay-session zero-gamma-flip
gex-terminal journal report research_journal/journal.md
gex-terminal journal report research_journal/journal.csv
gex-terminal journal report research_journal/journal.json
```

The Markdown report is useful for issues and research notes. CSV captures
entry rows plus the latest comparison row. JSON preserves the entries, final
snapshots, alerts, timeline events, and generated comparison metadata.

## TradingView Overlay

The TradingView overlay export is a lightweight chart-annotation format derived
from the snapshot:

```bash
gex-terminal --demo --tradingview-overlay gex_levels.json
gex-terminal --demo --tradingview-overlay gex_levels.csv
```

Both formats include:

- Gamma wall.
- Zero-gamma level.
- Call wall.
- Put wall.
- Top strike-level exposure levels.
- Major exposure band from the 70% net-gamma concentration range.

The JSON schema starts with:

```json
{
  "schema": "gex-terminal.tradingview-overlay.v1",
  "symbol": "ES",
  "levels": [],
  "bands": []
}
```

The CSV columns are:

```text
record_type,name,label,price,low,high,color,line_style,notes
```

## Sensitivity Reports

Sensitivity reports are separate from snapshots because they recompute the model
under alternate assumptions:

```bash
gex-terminal --demo --sensitivity sensitivity.json
gex-terminal --demo --sensitivity sensitivity.csv
gex-terminal --demo --sensitivity sensitivity.md
```

Default scenarios compare changes to contract multiplier, expiry, risk-free
rate, implied volatility, and the volume/open-interest proxy.

## Manual TradingView Workflow

TradingView does not import these files directly as native annotations. For now:

1. Export JSON or CSV from `gex-terminal`.
2. Add each `level` as a horizontal ray or price line on your chart.
3. Add the major exposure `band` as two boundary lines or a shaded box.
4. Use labels and colors from the export so the chart matches the terminal.

Automatic chart drawing would require a Pine Script, browser extension, webhook,
or broker/charting integration. That later integration should consume the same
portable JSON shape rather than coupling TradingView directly to the terminal UI.

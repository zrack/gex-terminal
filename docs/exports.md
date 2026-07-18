# Export Formats

`gex-terminal` exports research artifacts from computed snapshots so users can
review levels outside the terminal without exposing credentials or live feed
payloads.

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

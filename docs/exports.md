# Export Formats

`gex-terminal` exports research artifacts from computed snapshots so users can
review levels outside the terminal without exposing credentials or live feed
payloads.

## Snapshot JSON

The base snapshot export contains the computed metrics, strike matrix, expiry
breakdown, model inputs, and session metadata:

```bash
gex-terminal --demo --export gex_snapshot.json
```

The snapshot is the best format for reproducible research because it keeps the
strike-level values that produced the displayed gamma wall, zero-gamma node,
call wall, put wall, and concentration band.

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

## Manual TradingView Workflow

TradingView does not import these files directly as native annotations. For now:

1. Export JSON or CSV from `gex-terminal`.
2. Add each `level` as a horizontal ray or price line on your chart.
3. Add the major exposure `band` as two boundary lines or a shaded box.
4. Use labels and colors from the export so the chart matches the terminal.

Automatic chart drawing would require a Pine Script, browser extension, webhook,
or broker/charting integration. That later integration should consume the same
portable JSON shape rather than coupling TradingView directly to the terminal UI.

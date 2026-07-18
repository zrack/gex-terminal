# Replay Research Lab

Replay Research Lab turns bundled synthetic market days into shareable offline
research artifacts. It is designed for contributors who do not have paid market
data yet but still want to improve fixtures, alert logic, exports, and model
assumptions.

## Run The Lab

Generate a Markdown report across every bundled replay session:

```bash
gex-terminal replay-lab replay_lab.md
```

Generate machine-readable baselines:

```bash
gex-terminal replay-lab replay_lab.json
gex-terminal replay-lab replay_lab.csv
```

Limit the lab to one session:

```bash
gex-terminal replay-lab gap_fade_lab.md --replay-session gap-fade
```

## What The Report Includes

- A session dashboard with final spot, session change, net GEX, gamma wall,
  zero-gamma, regime, and alert count.
- A leaderboard for largest absolute net GEX, most alerts, tightest gamma
  concentration, and largest spot move.
- Session-to-session comparisons using saved final replay snapshots.
- Replay alerts for gamma wall shifts, zero-gamma crosses, net-GEX sign flips,
  major exposure changes, imbalance threshold crossings, and data-quality cases.
- Full snapshot payloads in the JSON report so future changes can be compared
  against a saved baseline.

## Bundled Lab Sessions

The current lab catalog covers:

- `demo`: compact screenshot/smoke-test flow.
- `full-session`: open, mid-session, and late-session ES 0DTE flow.
- `trend-day`: rising spot with call-side accumulation.
- `chop-day`: range-bound balanced call/put flow.
- `volatility-spike`: downside move with higher IV and put-heavy flow.
- `gap-fade`: gap-up open that rejects higher call walls and rotates lower.
- `call-wall-breakout`: upside breakout that walks the call wall higher.
- `zero-gamma-flip`: flow rotation across the zero-gamma boundary.
- `expiration-compression`: late 0DTE pinning around the gamma wall.
- `quality-stress`: off-symbol, partial-chain, and latency fixture cases.

## Screenshot Workflow

Screenshots can now render a replay session, not only seeded demo data:

```bash
gex-terminal --replay-session zero-gamma-flip --screenshot assets/gex-terminal-actual.svg
```

That makes the public README screenshot reproducible from a no-credential
replay scenario.

## Contributor Workflow

1. Add or edit a normalized JSONL fixture in `sample_data/`.
2. Register it in `gex_terminal/replay_catalog.py`.
3. Validate it with `gex-terminal validate-fixture PATH`.
4. Run `gex-terminal replay-lab replay_lab.md`.
5. Review changed alerts, walls, zero-gamma levels, and comparison deltas.
6. Add or update tests for any intended fixture, alert, or export behavior.

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
  strike-profile/zero-gamma compatibility level, regime, and alert count.
- A leaderboard for largest absolute net GEX, most alerts, tightest gamma
  concentration, and largest spot move.
- Session-to-session comparisons using saved final replay snapshots.
- Replay alerts for gamma wall shifts, compatibility-level crosses, net-GEX sign flips,
  major exposure changes, imbalance threshold crossings, and data-quality cases.
- Full snapshot payloads in the JSON report so future changes can be compared
  against a saved baseline.

## Bundled Lab Sessions

The lab runs the packaged catalog documented in
[Replay Research Mode](replay-research.md#bundled-sessions). That page owns the
session list and synthetic-scenario descriptions.

## Screenshot Workflow

Screenshots can now render a replay session, not only seeded demo data:

```bash
gex-terminal --replay-session zero-gamma-flip --screenshot assets/gex-terminal-actual.svg
```

That makes the public README screenshot reproducible from a no-credential
replay scenario.

For interactive review, run `gex-terminal --demo`, press `p` to open the replay
browser, and load bundled replay sessions directly inside the terminal.

For a fuller GitHub-ready bundle, use Demo Lab:

```bash
gex-terminal demo-lab demo_lab --replay-session zero-gamma-flip
```

It writes a color preview, color-themed terminal capture, snapshot exports,
overlays, Replay Lab reports, Provider Fixture Lab reports, and a manifest in
one folder.

## Historical Journal Workflow

Use the Historical Research Journal when you want to keep a local trail of
selected replay studies instead of regenerating the full lab every time:

```bash
gex-terminal journal add --replay-session trend-day
gex-terminal journal add --replay-session zero-gamma-flip
gex-terminal journal compare
gex-terminal journal report research_journal/journal.md
```

The journal compares saved entries by gamma wall, zero-gamma, call/put wall,
net-GEX, imbalance, session change, and replay-alert count. See
[docs/research-journal.md](research-journal.md) for the full command reference.

## Contributor Workflow

1. Add or edit a normalized JSONL fixture in `gex_terminal/data/replays/` so it
   is included in source and wheel workflows.
2. Register it in `gex_terminal/replay_catalog.py`.
3. Validate it with `gex-terminal validate-fixture PATH`.
4. Run `gex-terminal replay-lab replay_lab.md`.
5. Review changed alerts, walls, strike-profile levels, model provenance, and
   comparison deltas.
6. Add or update tests for any intended fixture, alert, or export behavior.

`tests/test_replay_lab.py` checks semantic checkpoints from the bundled inputs:
initialization after the first accepted option, timed wall changes, put-driven
sign flips, balanced and concentrated positions, quality-annotation deduplication,
off-symbol rejection, and schema-v2 event time. The checks use explicit fixture
events and bounded level/sign expectations rather than treating a generated
report or a nonzero alert count as its own oracle. Legacy ES expectations fix
fallback DTE at `0.01` days; NQ uses its contract-specific expiry and multiplier.

Keep net-GEX sign, proximity state, and compatibility-level crosses distinct.
For example, at these inputs `zero-gamma-flip` changes net-GEX sign while spot
stays above the historical strike-profile compatibility level, so it must not
emit a `zero_gamma_cross` alert. A scenario label is not evidence of a particular
alert, market regime, or predictive outcome.

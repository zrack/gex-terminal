# Replay Research Mode

Replay mode lets contributors exercise GEX calculations and terminal states
without live market data or broker credentials.

## Bundled Sessions

List the bundled sessions:

```bash
gex-terminal list-replays
```

Run a bundled session:

```bash
gex-terminal --replay-session trend-day
gex-terminal --replay-session chop-day
gex-terminal --replay-session volatility-spike
gex-terminal --replay-session gap-fade
gex-terminal --replay-session call-wall-breakout
gex-terminal --replay-session zero-gamma-flip
gex-terminal --replay-session expiration-compression
```

The current research fixtures are:

- `trend-day`: rising spot with call-side accumulation.
- `chop-day`: range-bound balanced call/put flow.
- `volatility-spike`: downside move with higher IV and put-heavy flow.
- `gap-fade`: gap-up open that rejects higher call walls and rotates lower.
- `call-wall-breakout`: upside breakout that walks the call wall higher.
- `zero-gamma-flip`: flow rotation across the zero-gamma boundary.
- `expiration-compression`: late 0DTE pinning around the gamma wall.
- `quality-stress`: valid fixture with off-symbol drops and partial chain
  coverage for Provider Health testing.

## In-Terminal Replay Selector

Start the terminal without live credentials:

```bash
gex-terminal --demo
```

Press `p` inside the terminal to open the bundled replay browser. Use Up/Down to
choose a session, Enter to load it into the same matrix, structure panels,
feed-health panel, and event log, and Escape to close the browser. Demo mode
offers `zero-gamma-flip` first because it shows a useful regime transition for
new users and screenshots.

The selector is available in demo and replay mode. Live mode keeps replay
loading disabled so background provider tasks cannot be mixed with local replay
state.

While a replay is loaded, use `x`, `d`, `m`, and `i` to cycle expiry selection,
fallback days-to-expiry, contract multiplier, and risk-free rate from inside the
terminal. These controls recompute the current snapshot, which makes quick
sensitivity checks possible before exporting a report.

## Replay Research Lab

Run every bundled replay session through the offline lab:

```bash
gex-terminal replay-lab replay_lab.md
gex-terminal replay-lab replay_lab.json
gex-terminal replay-lab replay_lab.csv
```

The lab report includes a session dashboard, replay alerts, session-to-session
comparisons, and saved final snapshots for reproducible baseline review. See
[docs/replay-lab.md](replay-lab.md) for the full workflow.

## Historical Research Journal

Save replay-session studies into a local journal:

```bash
gex-terminal journal add --replay-session trend-day
gex-terminal journal add --replay-session zero-gamma-flip
gex-terminal journal list
gex-terminal journal compare
gex-terminal journal report research_journal/journal.md
```

The journal stores generated entries in `research_journal/entries/`, which is
ignored by Git. It is useful for comparing level changes and replay alerts while
iterating on fixtures, model assumptions, or terminal output. See
[docs/research-journal.md](research-journal.md) for details.

## Historical Session Store

Save computed snapshots into a local store:

```bash
gex-terminal session-store save --replay-session zero-gamma-flip
gex-terminal session-store list
gex-terminal session-store report historical_sessions/session_store.md
```

The store writes records under `historical_sessions/sessions/`, which is ignored
by Git. It is useful when you want a lightweight archive of final snapshots
without the fuller narrative entry shape used by the journal. See
[docs/historical-sessions.md](historical-sessions.md) for details.

Record or replay a normalized event session when a final snapshot is not enough:

```bash
gex-terminal --replay-session trend-day --record-session \
  --capture-path /tmp/trend-day.gex-session.jsonl
gex-terminal --captured-session /tmp/trend-day.gex-session.jsonl \
  --replay-clock event --replay-speed 20
gex-terminal session-store captures
```

See [docs/captured-sessions.md](captured-sessions.md) for integrity, event-time,
and journal workflows.

The replay browser intentionally disables session switching during an active
capture. Finish the capture and start a new run so each file has one unambiguous
event stream.

## Demo Lab Pack

Generate a no-credential demo pack from a replay session:

```bash
gex-terminal demo-lab demo_lab
gex-terminal demo-lab demo_lab --replay-session gap-fade
```

The pack bundles the color preview, color-themed terminal screenshot, snapshot
exports, TradingView overlay exports, Replay Lab reports, Provider Fixture Lab
reports, and a manifest. It is the easiest path for GitHub screenshots and
contributor issue attachments.

## Provider Injection

Provider injection exercises raw or provider-shaped samples through adapter
parsing, consumer state, GEX math, snapshot export, and Provider Health
counters without opening a live connection:

```bash
gex-terminal inject-provider bundled:tradovate-live-sample
gex-terminal inject-provider bundled:databento-glbx
gex-terminal inject-provider bundled:yfinance-etf-options
gex-terminal inject-provider bundled:cboe-option-quotes-csv
```

Use this for captured/demo provider samples and converter work. Use normalized
replay fixtures when you want to test the engine contract directly. See
[docs/provider-injection.md](provider-injection.md) for details.

Run the Provider Fixture Workbench when you want a single scorecard across all
bundled provider-shaped samples:

```bash
gex-terminal fixture-lab provider_fixture_lab.md
```

That report is useful for adapter pull requests because it includes pass/fail
state, feed-health counters, computed levels, and saved snapshots without using
live credentials.

## Fixture Validation

Validate normalized JSONL before submitting fixtures:

```bash
gex-terminal validate-fixture gex_terminal/data/replays/es_trend_day.jsonl
```

Named `--replay-session`, `bundled:NAME`, and `fixture-lab` workflows resolve
package resources when installed from a wheel. The explicit validation path
above is for contributors editing the source fixture itself.

The validator checks JSON syntax, required normalized fields, option type,
positive prices/strikes, non-negative volume, IV shape, and basic fixture
coverage such as underlying ticks and option strikes.

## Offline Quality Scenarios

Demo/export workflows can simulate feed-health issues:

```bash
gex-terminal --demo --quality-scenario stale
gex-terminal --demo --quality-scenario partial-chain
gex-terminal --demo --quality-scenario dropped
gex-terminal --demo --quality-scenario latency
gex-terminal --demo --quality-scenario all
```

These scenarios mutate the local consumer state only. They do not represent a
real provider outage, but they make stale ticks, missing strikes, dropped
messages, and latency visible in the Provider Health panel and exported
snapshots.

## Model Sensitivity

Generate a model sensitivity report:

```bash
gex-terminal --demo --sensitivity sensitivity.md
gex-terminal --replay-session trend-day --sensitivity sensitivity.csv
```

The report compares base GEX output against assumption shifts for contract
multiplier, expiry, risk-free rate, implied volatility, and volume/open-interest
proxy scaling. For schema-v2 state, the base scenario uses the same contract rows,
pricing models, authoritative expiry timestamps, and multipliers as the snapshot.

Run the independent numerical/deterministic gate separately:

```bash
gex-terminal model-evidence model_evidence.md
```

That gate does not establish predictive market validity. See
[docs/model-validation.md](model-validation.md).

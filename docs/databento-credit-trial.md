# Databento Free-Credit ES/NQ Test

Use a small historical CME options sample to test the app locally. This workflow
uses the Historical API and the current checkout's setup scripts. It does not
need a live subscription or change provider readiness. The first test covers a
quarterly option-parent subset and uses trade volume, not open interest or
observed dealer positions.

## 1. Create The Account

Open [Databento signup](https://databento.com/signup), verify your email, and use
historical usage-based access. Databento may request a payment card during
onboarding. Do not activate a live subscription for this exercise.

Check **Billing** for your actual credit balance. New teams receive $125 in
credits, shared across the team and expiring after six months. Credits apply
before charges. Eligibility and the remaining balance are provider-controlled;
an existing team may have already used its credits.

Set a low historical monthly usage limit in Billing before testing; $5 is a
reasonable initial ceiling if the portal accepts it. Databento describes this as
blocking requests once usage exceeds the limit, so it is not a guaranteed
pre-request zero-dollar spending lock. The local downloader also previews every
request and refuses an estimated total above $1 per symbol by default.

Official references:

- [Credits and cost previews](https://databento.com/docs/faqs/usage-pricing-and-data-credits)
- [Billing and historical usage limits](https://databento.com/docs/portal/billing)
- [Historical versus live access](https://databento.com/docs/quickstart/new-user-guides)

## 2. Save An API Key Privately

Open [API keys](https://databento.com/portal/keys). Use the automatically created
key or create one named `GEX historical local test`. Keep the key out of chat,
screenshots, shell command arguments, and source files.

In Terminal, run:

```bash
cd "/Users/scottzeitner/Documents/shared projects/gex"
./.venv/bin/python -m scripts.databento_trial_download set-key
./.venv/bin/python -m scripts.databento_trial_download check
```

Paste the key only into the hidden prompt. It saves `.env.databento` with mode
`600`; Git ignores that file. The helper reads only this explicit key file and
does not change the main `.env`, provider defaults, or any Tradovate credentials.
It refuses to replace an existing key file. If needed, edit that file locally
and retain its owner-only permissions. `check` verifies local format,
permissions and SDK availability; it does not authenticate or use credits.

The current checkout already has the optional SDK. On a fresh developer checkout,
install the project's pinned extra with
`./.venv/bin/python -m pip install -e '.[databento]'` first.

## 3. Preview A Small ES Request

This example is a completed weekday interval: October 16, 2026, 13:35–13:36 UTC
(06:35–06:36 Pacific daylight time). Use an active completed session at least
24 hours old if changing the date.

```bash
./.venv/bin/python -m scripts.databento_trial_download quote \
  --symbol ES --start 2026-10-16T13:35:00Z
```

The authenticated metadata requests return costs only; no market data is
downloaded. The exact plan is:

| Input | Historical request |
| --- | --- |
| Contract metadata | `definition`, `ES.OPT` and `ES.FUT` parents, from the prior UTC midnight to replay start |
| Underlying quotes | `bbo-1s`, continuous `ES.v.0`, one-second top-of-book snapshots from two seconds before replay start through replay end |
| Option trades | `trades`, `ES.OPT` parent, one minute |

All requests use `GLBX.MDP3` and have a 60,000-record limit per schema. An empty
response or a response reaching that limit stops the downloader without writing
the completion marker; retained files may already have consumed credits. This is
a bounded sample, not a complete chain/session. `ES.OPT` excludes the separately
named weekly, daily and month-end families; `NQ.OPT` is similarly root-specific.
The replay bridge retains options matching the selected futures contract and
reports excluded other-month contracts. It does not substitute ETF options.

Definitions published after replay start are excluded. This prevents using
later metadata to construct an earlier checkpoint. The underlying quote must
match each option's `underlying_id`. The existing adapter calculates IV from
option trade price and a sufficiently recent futures midpoint with Black-76;
this feed does not supply a ready-made Greeks chain for this workflow.
One-second underlying snapshots reduce quote traffic while preserving every
requested option trade. BBO quotes become available at their `ts_recv` interval
end; their `ts_event` is a last-trade timestamp and is not used as quote time.
The bridge records this sampling and timestamp basis in its provenance. This is
a sampled historical test, not a reconstruction of every futures book update.
For BBO, the two-second freshness check measures time since the snapshot
boundary; a snapshot may carry a previously observed book forward.
The rate defaults to the app's configured 4.5% assumption; it is not downloaded
market evidence. The merge uses provider event time and does not reconstruct
original wire arrival or certify a point-in-time trading backtest.

References: [dataset](https://databento.com/docs/venues-and-datasets/glbx-mdp3),
[option-product discovery](https://databento.com/docs/examples/futures/futures-product-options).

## 4. Download Within The Credits

Read the estimated total, then check the remaining credits in Billing. Replace
`125` below with the balance actually shown. This explicitly requests data;
the downloader repeats the cost preview before making any data request.

```bash
./.venv/bin/python -m scripts.databento_trial_download download \
  --symbol ES --start 2026-10-16T13:35:00Z \
  --max-cost 1 --credits-remaining 125 --use-credits
```

The request is refused if the total quote exceeds either the $1 estimate ceiling
or the balance you supplied. Actual billing remains provider-controlled, and
other account usage can consume credits between checking and downloading.
The helper does not purchase subscriptions, use the Live API, retry downloads,
or overwrite earlier runs.

Files are owner-only under the Git-ignored directory
`historical_sessions/databento_trial/es-20261016T133500Z-bbo-1s/`:

- `definitions.dbn`, `underlying.dbn`, and `trades.dbn`;
- `request-plan.json` recording scope and quoted costs;
- `download-complete.json`, written only after all three requests return.

Keep payloads and derived captures private under the dataset's applicable
licence. Review its License tab during signup. Neither free credits nor a
successful download grant redistribution or indefinite-retention rights.
The provider's 30-day batch download availability is not a local retention grant.

## 5. Open The Sample In The App

Convert the three local files into a report and normalized captured session:

```bash
TRIAL_ES_DIR=historical_sessions/databento_trial/es-20261016T133500Z-bbo-1s
./.venv/bin/python -m scripts.databento_trial_replay \
  --definitions "$TRIAL_ES_DIR/definitions.dbn" \
  --underlying "$TRIAL_ES_DIR/underlying.dbn" \
  --trades "$TRIAL_ES_DIR/trades.dbn" \
  --symbol ES --output-dir "$TRIAL_ES_DIR/replay"
```

The bridge has no network path. It joins definitions, orders events, and uses
the existing provider adapter, consumer and model. Read `es-replay-report.json`
for observed inputs, exclusions, fallback IV and timing failures before
interpreting the chart. A failed or empty mapping is an integration finding;
do not fill missing fields with invented data or claim full-chain coverage.

A saved historical capture can still contain `configured_default` IV. New
conversions instead retain a qualified earlier same-contract IV where available,
or mark IV unavailable while preserving volume. For example, a trade premium
can fall outside pricing bounds when paired with a sampled futures midpoint.
Check `retained_prior_iv_ticks`, `unavailable_iv_ticks` and final
`pricing_coverage` separately from `inverted_iv_ticks`; event counts and current
unpriced quantities are different measures. No later observation repairs an
earlier checkpoint. Confirmed American contracts now use an early-exercise
futures model for IV and gamma; earlier captures retain their selected model.
European exercise metadata does not establish that a last-trade IV surface is
economically accurate. See [pricing assumptions](model-assumptions.md).

New conversions preserve a native trade fingerprint because distinct Databento
records can share the same venue sequence. If an older capture lacks
`provider_trade_event_id`, convert its original DBN files into a **new** output
directory to recover those distinctions. Preserve the earlier capture for
comparison; replaying it alone cannot add missing native identity fields.

Open the normalized capture in the Terminal:

```bash
./.venv/bin/python main.py \
  --captured-session "$TRIAL_ES_DIR/replay/es.gex-session.jsonl" \
  --symbol ES --multiplier 50
```

For Wind Tunnel, wait for options to appear in Terminal, then press **`w`** to
open a frozen checkpoint. This works without uploading the entire capture.
See [Terminal handoff](wind-tunnel.md#stress-a-terminal-checkpoint).
Alternatively, captures within the guided intake's 4 MiB/5,000-event limits can
be opened with **Open local session** in Wind Tunnel; see
[guided intake](wind-tunnel.md#bring-a-local-captured-session).
Replay and scenario changes use saved local data and consume no new credits.

## 6. Repeat For NQ

NQ uses `NQ.OPT`, `NQ.FUT`, and `NQ.v.0`. Start with its own cost preview:

```bash
./.venv/bin/python -m scripts.databento_trial_download quote \
  --symbol NQ --start 2026-10-16T13:35:00Z
```

Recheck Billing and replace `125` with the remaining balance before downloading:

```bash
./.venv/bin/python -m scripts.databento_trial_download download \
  --symbol NQ --start 2026-10-16T13:35:00Z \
  --max-cost 1 --credits-remaining 125 --use-credits
```

Convert and open the NQ sample:

```bash
TRIAL_NQ_DIR=historical_sessions/databento_trial/nq-20261016T133500Z-bbo-1s
./.venv/bin/python -m scripts.databento_trial_replay \
  --definitions "$TRIAL_NQ_DIR/definitions.dbn" \
  --underlying "$TRIAL_NQ_DIR/underlying.dbn" \
  --trades "$TRIAL_NQ_DIR/trades.dbn" \
  --symbol NQ --output-dir "$TRIAL_NQ_DIR/replay"
./.venv/bin/python main.py \
  --captured-session "$TRIAL_NQ_DIR/replay/nq.gex-session.jsonl" \
  --symbol NQ --multiplier 20
```

Canonical multipliers are ES $50 and NQ $20 per index point. Terminal does not
infer them from the capture header, so keep the explicit flags.

### Recover From The Earlier NQ Record-Limit Stop

The initial helper requested every futures `mbp-1` update. The documented NQ
minute has more than 700,000 quote updates and reaches the 60,000-record guard.
That is a sample-size stop, not an API-key failure. Repeating the old command
cannot complete it and an existing partial directory is intentionally preserved.

The updated helper defaults to `bbo-1s` and writes a separate `-bbo-1s` directory.
Use the NQ commands above; no key re-entry or deletion of the old partials is
needed. Existing successful ES captures remain usable at their original paths.
Advanced `--underlying-schema mbp-1` retains the original per-update request and
its record guard; it is not the recovery path for this NQ minute.

Failures now identify the request stage/schema and safe provider status when
available. Failed downloads retain `download-stopped.json` for diagnosis. Raw
provider messages, credentials and account identifiers are not printed.

A quiet minute may contain no usable NQ option trades. An empty result is a
reported data-coverage limit, not a reason to invent inputs or retry
automatically. Review the counts and choose a different active historical minute
or a separately cost-previewed wider scope if needed.

Success means both real historical samples produce inspectable contract and
model state in the app, with provenance and quality issues visible. It does not
establish live authentication/streaming, all option families, licensed OI
coverage, dealer inventory, or predictive validity. OI needs separately scoped
statistics and publication-time handling; it is intentionally absent from the
first credit test.

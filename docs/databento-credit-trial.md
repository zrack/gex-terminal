# Databento Free-Credit ES/NQ Test

Use a small historical CME options sample to test the app locally. This workflow
uses the Historical API and the current checkout's setup scripts. It does not
need a live subscription or change provider readiness. The first test covers a
quarterly option-parent subset and uses trade volume, not open interest or
observed dealer positions.

If the data is already downloaded, skip signup, quoting and downloading. The
conversion, replay, validation and saved-data starter paths below read local
files and use no new credits. A cost quote still contacts Databento; it is not
part of an offline review. [First Run](first-run.md#open-saved-es-or-nq-data)
owns launching saved ES/NQ data in both interfaces.

## 1. Create The Account

Open [Databento signup](https://databento.com/signup), verify your email, and use
historical usage-based access. Databento may request a payment card during
onboarding. Do not activate a live subscription for this exercise.

Check **Billing** for your actual credit balance, eligibility and expiry before
making a request. The original October 2026 trial used an advertised $125
new-team credit offer with a six-month validity period; this guide does not
guarantee that offer for another signup or confirm a current balance. Credits
are shared across a team, and an existing team may already have used them.

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

The helper's local `check` reports SDK availability. If the developer environment
does not have it, install the project's pinned extra with
`./.venv/bin/python -m pip install -e '.[databento]'` first. Installing missing
dependencies can use the network; replaying files after installation does not.

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
option trade price and a sufficiently recent futures midpoint. New conversions
use Black-76 for European options and the numerical `american_futures_crr`
model for confirmed American exercise. This feed does not supply a ready-made
Greeks chain for this workflow.
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

To open both interfaces from the same completed capture, use the
[saved-data starter](first-run.md#open-saved-es-or-nq-data). Browser upload keeps
its smaller limit; a full trading day uses the starter's explicit local-file
streaming path. Preserve older captures and convert into a new folder when
testing a corrected mapping or pricing model.

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

## Full Trading Day ES And NQ

The full-session workflow uses the same Historical API, but quotes all **26
application-supported option parents per market**, one explicitly identified
futures contract per market, and the completed Chicago trading-day window.
For October 16, 2026 this is **October 15 22:00 UTC through October 16 21:00 UTC**
(17:00 the prior day through 16:00 Chicago). Exchange pauses remain gaps; this
is 23 hours of session coverage, not 23 hours of uninterrupted trading.

Check Billing first. The helper requires an explicitly supplied remaining
free-credit balance and caps the combined quote at **$5**. A quote uses metadata
only. A download repeats every quote before its first data request, refuses
changed record/byte counts or an excessive total, and writes private per-request
progress receipts. It never retries, overwrites an earlier run or silently
narrows option-family coverage.

```bash
FULL_DAY_DIR=historical_sessions/databento_trial/full-day-example
./.venv/bin/python -m scripts.databento_session_download quote \
  --date 2026-10-16 --output "$FULL_DAY_DIR/quoted-plan.json"
```

For this date, the default futures identity is read from the previously owned
ES/NQ `broader-20261019` BBO files. For another date, explicitly supply
`--es-underlying` and `--nq-underlying` with already-owned BBO files that identify
its intended futures contracts. The helper does not automatically roll contracts
or resolve a different underlying after quoting.

Review the saved plan and replace `REMAINING_CREDITS` below with Billing's
verified numeric balance. This command spends credits:

```bash
./.venv/bin/python -m scripts.databento_session_download download \
  --plan "$FULL_DAY_DIR/quoted-plan.json" \
  --output "$FULL_DAY_DIR/acquisition" \
  --credits-remaining REMAINING_CREDITS --max-cost 5 --use-credits
```

Definitions cover two prior UTC days through session end, including intraday
updates. Underlying BBO-1s starts two seconds before the session; option trades
cover the session itself. Each market is bounded to five million native records;
all compressed files together are bounded to 512 MiB. Each request uses its
quoted count plus one as a sentinel limit; reaching that limit, truncation or an
empty input stops completion. Partial files may already have used credits.
Actual billed cost is provider-controlled and remains distinct from the quote.
Holiday or special session hours require separate calendar verification.

Convert each market into a **new** output folder, entirely offline:

```bash
./.venv/bin/python -m scripts.databento_session_replay --symbol ES \
  --definitions "$FULL_DAY_DIR/acquisition/es/definitions.dbn" \
  --underlying "$FULL_DAY_DIR/acquisition/es/underlying.dbn" \
  --trades "$FULL_DAY_DIR/acquisition/es/trades.dbn" \
  --start 2026-10-15T22:00:00Z --end 2026-10-16T21:00:00Z \
  --output-dir "$FULL_DAY_DIR/replays/es"
```

Repeat with `NQ` and `nq` paths. The converter uses a private disk index rather
than loading the raw history into memory, and one adapter/consumer across UTC
midnight. It preserves native fill fingerprints, interval-end quote availability,
causal definitions and the existing IV freshness/bounds rules. American-option
inversion can make this step take several minutes; progress goes to stderr.
No pricing approximation is weakened to accelerate conversion.

Only option definitions matching the selected futures contract enter the
capture. Reports count excluded definitions and other-future trade events.
All supported parents does **not** establish complete-chain coverage, and this
workflow supplies **trade volume**, with no open interest or observed dealer
inventory. BBO-1s samples do not reconstruct every book update or original
network arrival. Rate and model assumptions remain configured research inputs.
Closing calculations use each contract's latest captured IV, which can predate
the close by hours. Coverage describes usable model inputs, not a synchronized
closing chain; see [full-session assumptions](model-assumptions.md).

Wind Tunnel shows the distinction directly: **Mode: REPLAY** is separate from
the captured **Health**; pricing coverage separates priced contracts and selected
quantity from excluded exposure; accepted-IV ages use the captured cutoff or
advanced scenario model time. Five minutes is an age reference, not a filter
that drops unchanged IV. Retained prior-valid IV keeps its original observation
clock, and missing or timestamp-ambiguous clocks remain unknown. Price, IV and
time shocks do not repair captured premium/bound failures or acquire later
observations. See [the diagnostic guide](wind-tunnel.md#read-source-health-and-accepted-iv-age).

Validate the native files against the normalized captures and checkpoint output:

```bash
./.venv/bin/python -m scripts.validate_full_session \
  --manifest "$FULL_DAY_DIR/acquisition/download-complete.json" \
  --replays "$FULL_DAY_DIR/replays" --output "$FULL_DAY_DIR/validation"
```

The validator builds its own native-data index. It reconciles event occurrences,
unique fill quantities, identities, causal metadata/quotes and pricing status;
checks prefixes at opening +15 minutes, 13:40 UTC, immediately before and after
20:00 UTC expiry, and the close; and reproduces fresh Wind Tunnel receipts.
Independent European arithmetic is checked directly. Independent American
finite-difference comparison runs only if QuantLib is already installed and is
explicitly marked unavailable otherwise. An empty/all-expired prefix cannot
produce a nonempty canonical checkpoint; its unavailability is reported, with an
explicit time-advance receipt checked from an earlier valid checkpoint where
available. No validation step requests provider data or uses credits.

Finally, in a **fresh reviewed setup** with full-session support, register both:

```bash
"./GEX App/run-gex" --register-saved-data ES \
  --captured-session "/absolute/path/to/replays/es/es.gex-session.jsonl"
"./GEX App/run-gex" --register-saved-data NQ \
  --captured-session "/absolute/path/to/replays/nq/nq.gex-session.jsonl"
```

Open **Start GEX.command → Saved data — Both → ES or NQ**. Long sessions load
Terminal to the final state and open that final checkpoint in Wind Tunnel.
The closing checkpoint excludes already expired contracts; retained raw trade
quantity and active unpriced quantity are different measures. Checkpoint limits
remain 8 MiB / 5,000 rows; a larger capture does not bypass those limits.
[First Run](first-run.md#open-saved-es-or-nq-data) owns reuse and loading behavior.
Keep the source files, captures and validation evidence private and preserve
older samples unchanged.

# Market Wind Tunnel

The Wind Tunnel answers a conditional research question: **if these assumptions
change, how does the modeled structure change?** It reconstructs a bundled
replay, accepts a frozen Terminal demo/replay checkpoint, or guides you through
a local captured session. It keeps the selected checkpoint's contract
quantities fixed and reprices scenarios
through the same calculation engine as the terminal.

The pricing notice above the charts identifies the formula and exercise-style
qualification. **Source & assumptions** explains early exercise, the configured
risk-free rate and ACT/365 timing. Newly normalized Databento futures options
with confirmed American exercise use a numerical early-exercise model. Older
captures keep their recorded model: American contracts priced with Black-76
retain the European-approximation qualification. Missing exercise metadata
remains explicitly unknown.
See [model assumptions](model-assumptions.md).

## Open The Workbench

In a fresh setup folder with the unified starter, open **Start GEX.command**
on macOS or run **`run-gex --choose`** on Linux, then choose **Wind Tunnel**,
**Both**, or **Saved data — Both** for an existing ES/NQ capture.
The direct **Start Wind Tunnel.command** / **run-wind-tunnel** shortcuts
also remain available, including in the original 0.6.0 setup.
[First Run](first-run.md#choose-terminal-wind-tunnel-or-both) owns the shortcut
and update details. Manual wheel installations use:

```bash
gex-terminal wind-tunnel
```

The direct command opens your browser. Keep its launcher window open; Control-C
stops the local server. In **Both**, quitting the terminal also stops the server
that combined session started. Closing a browser tab closes only the view.
The terminal and browser keep independent source selections and research state.
Ordinary **Both** opens independent synthetic sources; **Saved data — Both**
initializes both views from one private capture. Press `w` in Terminal to make
an explicit frozen handoff into a separately owned Wind Tunnel session.
No provider account, live data, CDN or telemetry is involved.
The browser connects only to a Python process on this computer. The launcher
uses a free port; the direct command defaults to port 8765. To select a free
port and an explicit research location:

```bash
gex-terminal wind-tunnel serve --port 0 --workspace ./wind_tunnel_research
```

Commands below assume `gex-terminal` is on your PATH. For the manual environment
in [First Run](first-run.md), use its explicit `gex-app/bin/gex-terminal` path
instead; no activation is required.

Add `--no-browser` to print the launch URL. Use that complete URL, including its
fragment, when reopening the app. Its random capability grants access to this
local session. Restarting creates a new capability. Saved receipts exclude it.

## Explore A Scenario

### Open Saved ES Or NQ Data In Both Views

Choose **Saved data — Both** in a fresh reviewed starter, then select ES or NQ.
The starter validates a completed normalized capture, remembers a private frozen
source and reconstructs its final checkpoint through the installed application.
[First Run](first-run.md#open-saved-es-or-nq-data) owns capture selection,
registration/reuse commands, inherited assumptions and missing-value defaults.

Wind Tunnel opens that final checkpoint. Terminal loads long sessions without
source-time delays; short samples replay at 60×. The starter prints the policy,
time span and event count. Let Terminal reach the endpoint before comparing values.
Unavailable IV and raw quantities are preserved, with excluded exposure shown
in pricing coverage. Subsequent source selections and scenarios are independent.
This path uses no provider requests or credits.

The explicit local starter accepts captures up to 1 GiB / 2 million events;
guided browser upload keeps its smaller limits. Frozen checkpoints remain
bounded to 8 MiB / 5,000 rows. Full-day final checkpoints exclude contracts that
have already expired, even though their trades remain in the capture.

### Stress A Terminal Checkpoint

In Terminal, load a demo/replay and press **`w` — Stress checkpoint**. The action
copies the consumer's current state under its lock, including spot, authoritative
market time, effective rate/DTE/multiplier, expiry filter and source quality.
Wind Tunnel opens on **Terminal selected proxy**: positive trade volume
per contract, with OI fallback, matching Terminal without summing both quantities
for one contract. Alternative volume, OI and directional models remain separate.

The browser labels this as a frozen checkpoint and shows its time, expiry filter
and captured health. It cannot scrub to other events or broaden the original
expiry filter. Later ticks, replay loads and assumption changes in Terminal do
not alter it. Press `w` again for a new checkpoint; that replaces only the handoff
service owned by this Terminal. Quitting Terminal stops that service and retains
its files. Other standalone Wind Tunnel sessions remain independent.

Checkpoint JSON and receipt workspaces are saved beneath
`wind_tunnel_handoffs/` in Terminal's working/research directory. Details (`v`)
shows the last checkpoint path. If the browser could not open, use that path in
the command below. Files contain market data; retain/share them only under the
input source's rights. A replay file is not automatically synthetic or licensed.

For an explicit CLI handoff, export a supported demo/replay checkpoint, then
open it. These commands run without live provider access:

```bash
gex-terminal --replay-session nq-research-loop --symbol NQ --multiplier 20 --wind-tunnel-checkpoint nq-checkpoint.json
gex-terminal wind-tunnel --checkpoint nq-checkpoint.json --port 0
```

Use a new output filename; an existing checkpoint is never overwritten. Input
files must be regular, bounded checkpoint JSON, not symlinks. The server reads
only the path explicitly supplied by its operator; browser requests cannot
choose filesystem paths. This is a single-state handoff, not a general session
importer or live synchronization. Live-state capture is rejected pending its
separate governed authority. Mixed legacy/v2 state, missing market time and
invalid/oversized inputs also fail closed.

### Bring A Local Captured Session

Choose **Open local session** in the workbench. Select a complete
`*.gex-session.jsonl` made by the [capture recorder](captured-sessions.md), then
review its integrity result, declared source, genuine market times, effective
model assumptions and fallback warnings. Recorded footer quality describes the
end of the original session; the opened checkpoint shows replay-computed quality
for the selected prefix. Arbitrary CSV/provider files are not
supported. Inspect your original file for sensitive content and confirm your
source permits this local use before selecting it.

Choose a capture-sequence checkpoint and explicitly open it. The production
consumer reconstructs only that prefix; later events cannot enter the frozen
input. The selection preview shows the maximum genuine message time in the
capture prefix, so a late record never moves that preview backward. The opened
checkpoint shows the consumer's authoritative accepted-state time, which can be
earlier when later captured records were ignored. A prefix without usable underlying and
option state cannot open. Missing genuine message clocks fail closed even if
the capture envelope used receipt-time fallback.

The upload is bounded to 4 MiB and 5,000 events. Up to four inspected sessions
are retained in server memory; discard an inspection before adding a fifth.
If an interrupted tab loses those inspection IDs, restart the local server to
clear its registry; saved receipts remain available.
Cancel/discard release inspected state (a pending verification is discarded when
its response arrives); server shutdown clears the registry. Raw uploads are not
written to the workspace. The browser sends bytes rather than a filesystem path;
unknown header labels and message extensions are removed after integrity
verification. Source contract identifiers become stable opaque aliases while
preserving contract linkage. Receipts still contain market data: inspect them
before sharing. Checksums establish integrity, not authenticity or
source rights. Original files remain under their owner's retention policy.

The opened source is a **Frozen captured checkpoint**. Its generated provenance
binds the complete capture content digest and selected event number. Calculation,
model comparison and save/export/reopen use the existing checkpoint workflow.
The receipt embeds its frozen input and reproduces on a fresh server without the
capture file. Reopening a receipt does not restore the full session for scrubbing;
select the original capture again to choose a different prefix. Canceling or a
failed inspection leaves the current validated research source available.

### Bundled Synthetic Sessions

1. Start with **ES Wind Tunnel Lab**, a bundled synthetic multi-expiry chain.
   Move the checkpoint to select the last replay event permitted into the model.
2. Choose a position model. Volume, open interest and aggressor-directionalized
   volume are separate proxies; the workbench never sums them.
3. Change spot, IV or elapsed time, or remove the nearest expiry. Inspect the
   original and scenario metrics and contract contributions.
4. Switch between **Exposure landscape**, **Compare** and **Fragility map**.
   Save a useful scenario and reopen it from **Saved scenarios**.

The landscape prices a spot/time grid with the selected IV and expiry settings.
Each plotted value comes from a calculation. A 2D view and inspectable tables
keep results accessible where WebGL is unavailable. Compare uses matched axes
so a larger-looking plot cannot come from a different scale. Fragility shows
only tested cells: missing or invalid cells do not mean stability.

## Read Pricing Coverage

The **Pricing coverage** panel above the charts shows priced/selected contracts
and priced/selected quantity, with percentages. Read **Original** and
**Scenario** separately; identical coverage shares an **Original & scenario**
panel. The denominators follow the selected quantity model and eligible expiry
cohorts, not incoming event counts. Earlier valid IVs count as priced and are
separately labeled.

**Complete** covers every selected contract and quantity. **Partial** excludes
unpriced exposure from GEX while retaining its raw quantity, and never rounds
up to 100%. **Unavailable — no selected contracts are priced** means GEX is
unavailable rather than zero. **No selected contracts** means the current
selection is empty, with coverage percentages not applicable. **Coverage
unavailable** means contract-level coverage cannot be established; a legacy
aggregate must not be read as complete coverage.

Open **Source & assumptions** for each unpriced contract and its captured
pricing inputs. Available evidence includes the original premium, violated
model bound, underlying input and quote age. These describe the failed
inversion at capture time, even after spot, IV or time changes. Scenario controls
do not fill unavailable IV or rewrite that evidence. A mismatch explains the
model failure without establishing its market or feed cause.
[Model Assumptions](model-assumptions.md#quantity-and-position-sources) owns the
pricing and retention policy.

## What The Controls Mean

| Control | Meaning |
| --- | --- |
| Spot shift | Add underlying price points to the checkpoint spot; not a percentage return |
| IV shift | Add absolute volatility points uniformly to each row; +1 means +0.01 annualized IV |
| Time advance | Advance model time in minutes with quantities frozen; later replay events are not consumed |
| Remove nearest expiry | Remove the expiry cohort nearest at the original checkpoint, even after time advances; never retarget a later cohort |
| Position model | Select an independent quantity proxy on the same frozen input |

`Terminal selected proxy` is available only for Terminal checkpoints. It
preserves their explicit per-contract fallback policy; it is not an additional
source of quantities to sum with the other models.

The IV policy is sticky strike with a uniform shift, not a simulated volatility
smile. Invalid nonpositive spot or IV, expired contracts and absent quantities
are handled explicitly. Exact expiry instants take precedence; legacy rows use
the declared fallback time to expiry. Changing time does not invent trades,
open-interest updates, hedging activity or a future price path.

The API rejects unknown fields, nonfinite numbers, ambiguous models and
out-of-range requests. Absolute supported limits are spot shift ±5,000 points,
IV shift ±100 volatility points and time advance 0–43,200 minutes. Each grid
axis accepts at most 41 distinct increasing values, at most 1,681 cells. Browser
controls offer narrower practical ranges. These limits bound computation;
they do not imply that extreme scenarios are plausible.

## Find A Breaking Case

Choose a dominant-wall change, net-GEX sign change or model disagreement and
run a bounded search. A model disagreement means the two selected models differ
in their dominant wall or net sign at the same sampled point. It is a sensitivity
finding, not evidence that one model is correct.

Wall/sign searches compare candidates with the zero-shock checkpoint (time zero,
no expiry exclusion). Fixed time or expiry changes apply only to candidates, so
a changed claim can occur at a zero/zero grid coordinate. Grid values replace
the common shocks on their selected axes; they are not added to those shocks.

The nearest result minimizes
`sqrt((x / x_scale)^2 + (y / y_scale)^2)` among changed sampled points. Each
scale is the largest absolute tested coordinate on that axis; a zero-only axis
uses one. Ties resolve by distance, then ascending x and y. Fixed shocks such as
time advance or expiry removal are disclosed and excluded from this two-axis
distance. Changing bounds or grid resolution can change the nearest result.

- **Break found:** at least one tested point changes the selected claim.
- **No break found:** no evaluable tested point changes it within this grid.
- **Not evaluable:** required exposure, contracts or directional coverage are
  unavailable. Unavailable cells cannot support a no-break conclusion.

The result is a nearest **tested** change, never a global minimum, probability
or safety guarantee. A wall is the model's dominant exposure strike; no observed
dealer positioning, support/resistance certainty or prediction is inferred.

## Save, Export And Reproduce

Saving recalculates the submitted inputs on the server, then writes an immutable
receipt containing the normalized request, bundled source/checkpoint identity,
calculation fingerprint, results and checksum. Terminal handoff requests also
embed their frozen input, so reproduction does not need the original checkpoint
file or running Terminal. Open a saved scenario to
recalculate it; export its JSON to retain or transfer it. Receipt verification
checks content integrity and independently recomputes the result.

```bash
gex-terminal wind-tunnel verify experiment.json
gex-terminal wind-tunnel reproduce experiment.json --output reproduction.json
```

Files are never overwritten. Choose a new output filename. Exact reproduction
requires the same supported schema, source, implementation, application version,
Python minor and NumPy version. A changed build can yield a mismatch even if its
displayed rounded values look alike. A checksum proves content identity, not
the truth or authorship of a research claim.

Checkpoint inputs are limited to 8 MiB and 5,000 copied rows. Requests and saved
receipts obey a 32 MiB JSON bound so full-session checkpoints and their detailed
results can be retained together. Browser capture intake keeps its separate
4 MiB / 5,000-event bound. No data is silently truncated.
The workspace must be empty or already owned by the Wind Tunnel. It holds up to
100 receipts, 32 MiB per receipt and 64 MiB total. Keep unrelated files elsewhere.
When full, choose a new workspace and preserve the old one. Browser requests
cannot select arbitrary disk paths. Existing terminal research remains separate.

API clients must forward signed receipt JSON text unchanged. Parsing and
reserializing it in another language can change number formatting and invalidate
the checksum. The browser preserves the original text for reopen/import and
exports the exact server response bytes.

## Three Completed Examples

The **Examples** control runs these requests against the installed calculation
engine; it does not load a picture or a canned chart. Reproduce them from a
manual installation with:

```bash
gex-terminal wind-tunnel example discovered-break --output discovered-break.json
gex-terminal wind-tunnel verify discovered-break.json
gex-terminal wind-tunnel example no-break --output no-break.json
gex-terminal wind-tunnel verify no-break.json
gex-terminal wind-tunnel example expiry-exclusion --output expiry-exclusion.json
gex-terminal wind-tunnel verify expiry-exclusion.json
```

| Example | What it demonstrates |
| --- | --- |
| `discovered-break` | A broad synthetic spot/IV grid changes the original dominant wall and identifies the nearest tested changed point |
| `no-break` | A narrow synthetic neighborhood retains its dominant wall at all tested points; the conclusion stays inside those bounds |
| `expiry-exclusion` | Removing the front expiry changes the composition of a multi-expiry synthetic chain while preserving the remaining contracts |

Verification coverage and release identity are recorded in
[GEX-WIND-001](work-packets/GEX-WIND-001.md). The examples verify the software
workflow only. `predictive_validity` remains `unmeasured`; dealer/customer and
opening/closing classifications remain `unobserved`.

## Assets And Recovery

The wheel bundles Plotly.js 4.1.1 and a selected set of Phosphor 2.1.1 icons.
Their MIT license notices and exact file identities are retained in
`gex_terminal/wind_tunnel_web/vendor/`. No browser build step is needed.

Install updates into a fresh reviewed setup folder, retain the previous folder
and your receipts, and use the previous launcher to roll back. Receipt
reproduction reports disagreement instead of silently rewriting old results.
The September 20 frozen study remains a separately identified historical build.

# Market Wind Tunnel

The Wind Tunnel answers a conditional research question: **if these assumptions
change, how does the modeled structure change?** It reconstructs a synthetic
replay checkpoint, keeps its contract quantities fixed and reprices scenarios
through the same calculation engine as the terminal.

## Open The Workbench

Open **Start Wind Tunnel.command** in a fresh 0.6.0 setup folder on macOS, or
**run-wind-tunnel** on Linux. Manual wheel installations use:

```bash
gex-terminal wind-tunnel
```

The command opens your browser. Keep the launcher window open; Control-C stops
the local server. No provider account, live data, CDN or telemetry is involved.
The browser connects only to a Python process on this computer. The launcher
uses a free port; the direct command defaults to port 8765. To select a free
port and an explicit research location:

```bash
gex-terminal wind-tunnel serve --port 0 --workspace ./wind_tunnel_research
```

Commands below assume `gex-terminal` is on your PATH. For the manual environment
in [First Run](first-run.md), use its explicit `gex-env/bin/gex-terminal` path
instead; no activation is required.

Add `--no-browser` to print the launch URL. Use that complete URL, including its
fragment, when reopening the app. Its random capability grants access to this
local session. Restarting creates a new capability. Saved receipts exclude it.

## Explore A Scenario

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

## What The Controls Mean

| Control | Meaning |
| --- | --- |
| Spot shift | Add underlying price points to the checkpoint spot; not a percentage return |
| IV shift | Add absolute volatility points uniformly to each row; +1 means +0.01 annualized IV |
| Time advance | Advance model time in minutes with quantities frozen; later replay events are not consumed |
| Remove nearest expiry | Remove the expiry cohort nearest at the original checkpoint, even after time advances; never retarget a later cohort |
| Position model | Select an independent quantity proxy on the same frozen input |

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
calculation fingerprint, results and checksum. Open a saved scenario to
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

The workspace must be empty or already owned by the Wind Tunnel. It holds up to
100 receipts, 4 MiB per receipt and 64 MiB total. Keep unrelated files elsewhere.
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

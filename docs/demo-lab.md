# Demo Lab

Demo Lab is the portable, no-credential review loop. It packages one bundled
synthetic replay, the resulting research views, and a versioned review receipt
into a self-contained folder. The public contract is the CLI and the versioned
artifacts; Python helpers remain experimental.

Both replay and provider-fixture inputs are installed package resources, so the
workflow works outside a source checkout. It does not establish live-provider
readiness, dealer inventory, predictive validity, execution quality, or
profitability.

## Generate

Bundle and manual-wheel users should first follow the
[installed CLI instructions](first-run.md#compare-replay-and-review), which
work without shell activation. Use that explicit CLI path in the examples below.

Generate the default ES pack:

```bash
gex-terminal demo-lab demo_lab
```

Generate the complete NQ research loop:

```bash
gex-terminal demo-lab nq_demo_lab --replay-session nq-research-loop
```

`nq-research-loop` is a dedicated synthetic NQ replay with contract multiplier
20, normalized schema-v2 messages, exact event and expiry times, open-interest
rows, incremental trade rows, and trade-direction provenance. It exists to make
the full offline comparison reviewable without licensed data.

The default remains `zero-gamma-flip` for first-run visual continuity. Other
catalog sessions may be selected with `--replay-session NAME`.

## Review Sequence

The generated README follows one path:

1. **Today** — inspect the final synthetic snapshot.
2. **Explain** — inspect the source and bound model assumptions.
3. **Compare** — review OI, raw trade-volume, and directionalized trade-volume
   proxies separately. These values may not be summed.
4. **Replay** — run the copied `inputs/replay.jsonl` or reproduce the pack.
5. **Review** — verify source, runtime, semantic content, and artifact integrity.

Verify a pack before using or sharing it:

```bash
gex-terminal demo-lab verify demo_lab
```

Reproduce it into a new, empty directory:

```bash
gex-terminal demo-lab reproduce demo_lab reproduced_demo_lab
```

Reproduction uses the copied replay as its data source, reconstructs the bound
model profile, regenerates the pack, verifies the result, and compares all bound
decision-content hashes. It does not read the catalog's original replay file.
The source pack and output directory must be separate.

## Receipt And Failure Rules

`review-receipt.json` records:

- source byte hash, catalog identity, schema versions, event range, position and
  direction sources, and explicit synthetic redistribution status;
- complete model profile and model-profile hash;
- application version, Python major/minor runtime, and bound dependency versions;
- stable replay/provider quality summaries and the evidence ceiling;
- semantic hashes for the decision artifacts and byte hashes for every other
file in that exact pack; and
- a self-hash for the receipt.

These are unkeyed integrity hashes, not a signature or independent proof of
authenticity. Source rights are the catalog declaration recorded by the pack.

Verification fails closed when an input or artifact changes; a file is missing,
extra, renamed, or symbolic; a path escapes the pack; symbol, multiplier, model,
or catalog identity conflicts; or an artifact, application, runtime, normalized
input, or receipt schema is incompatible. The strict inventory means notes or
other additions belong beside the pack, not inside it.

Named elapsed-time and latency fields are omitted from semantic identity because
they vary between executions. Raw byte hashes still bind those files within the
exact pack, and generation time remains part of semantic identity.

Producer and reader compatibility is an explicit allowlist, never an inference
from version ordering. The current source table is:

| Contract | Accepted producer | Accepted reader |
| --- | --- | --- |
| Review receipt v1 / runtime v1 | `0.4.0`, `0.5.0`, `0.6.0` | Current `0.6.0` reader |

The 0.4.0 contributor implementation accepted only 0.4.0 producers. The current
0.6.0 reader also accepts its receipts when exact runtime and semantic results
match. The original tagged 0.4.0 release did not produce these receipts; its
legacy Demo Lab packs are not silently upgraded. Unknown versions remain
rejected. Python major/minor and pinned NumPy/Textual versions must match the
recorded runtime; cross-Python reproduction is not promised.

## Output Folder

| File | Purpose |
| --- | --- |
| `README.md` | Portable Today → Explain → Compare → Replay → Review guide. |
| `manifest.json` | Artifact inventory, source/model identity, top-line metrics, and limitations. |
| `review-receipt.json` | Source, runtime, content, artifact, and evidence-ceiling integrity receipt. |
| `inputs/replay.jsonl` | Exact authorized synthetic replay copied into the pack. |
| `gex-terminal-color.svg` | Color preview generated from replay snapshot values. |
| `terminal-screenshot.svg` | Textual terminal capture after replaying the session. |
| `snapshot.json`, `snapshot.md` | Machine-readable and human-readable final snapshot. |
| `tradingview-overlay.json`, `.csv` | Portable chart levels and bands. |
| `replay_lab.json`, `.md` | Selected-session replay analysis. |
| `provider_fixture_lab.json`, `.md` | Bundled provider-shaped fixture scorecard. |
| `model-comparison.json`, `.md`, `.csv` | Raw versus directionalized trade-volume comparison. |
| `position-model-comparison.json`, `.md`, `.csv` | Separated OI/raw/directional proxy ladder and differences. |

Generated `demo_lab/` and `demo_pack/` folders are ignored by Git by default.

## Contributor Preview

From a source checkout with the development dependencies installed, stage fresh
previews using the current interpreter:

```bash
python scripts/refresh_previews.py --include-onboarding
```

The command prints a new ignored `dist/previews-<unique-id>` directory containing
`demo.svg`, optional `onboarding.svg`, and `manifest.json`. Use `--output-dir PATH`
to choose another **new** directory; existing directories and symlinks are
rejected. Without `--include-onboarding`, only the Demo Lab graphic is generated.
The command stages previews by default. To generate them and update the two
documentation assets, use:

```bash
python scripts/refresh_previews.py --include-onboarding --write-assets
```

Inspect the generated SVGs and the asset diff before accepting a refresh. The
demo graphic uses calculated snapshot values; onboarding captures the actual
Textual replay picker at 180 columns by 64 rows so its list viewport is visible.
The taller capture retains the application's normal list viewport; it does not
show every choice at once. The temporary Demo Lab terminal capture remains
180 columns by 54 rows, and the manifest records both sizes. Both select the explicit bundled
`zero-gamma-flip` replay. Demo Lab also evaluates its bundled provider-shaped
fixtures; none of these operations connects to a provider.

Each application command runs from a fresh temporary working directory using
the checkout source and the current Python interpreter in isolated mode. The
environment allowlist removes ambient GEX/provider settings and credentials;
the repository and caller `.env` files are not loaded. Existing research folders
and the frozen study bundle are untouched.

The local manifest records source commit and dirty state, source/input hashes,
Python and direct dependency versions/metadata hashes, exact commands and exit
codes, terminal and SVG dimensions, verified Demo Lab receipt identities, and
asset hashes. The input inventory covers the bundled catalog and fixtures,
including files not consumed by this run. Dependency metadata is not a complete
environment lock. A failed command leaves a failed manifest without retaining
arbitrary subprocess diagnostics. Source or input changes during generation
fail the refresh before repository assets are copied.

Repeatability means fixed inputs and snapshot calculations. The legacy replay
preserves its `timestamp` chronology, but Demo Lab's report/as-of fields for
this schema-v1 fixture use run time; those fields vary between runs. Terminal
SVG identifiers and timing can vary too. Hashes identify the exact
outputs, not a promise of identical bytes for every report or screenshot. These
are current source-build previews, not screenshots of the frozen study build or
evidence of participant acceptance or live reliability.

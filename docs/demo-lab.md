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
| Review receipt v1 / runtime v1 | `0.4.0` | `0.4.0` |

A later release may add an older producer and a newer reader only after the
receipt, runtime, model, and result semantics are shown to match; unknown
versions remain rejected.

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

To refresh repository preview assets from the existing ES visual path:

```bash
gex-terminal demo-lab /tmp/gex_terminal_demo_lab --replay-session zero-gamma-flip
cp /tmp/gex_terminal_demo_lab/gex-terminal-color.svg assets/gex-terminal-demo-lab.svg
gex-terminal --demo --screenshot assets/gex-terminal-onboarding.svg --screenshot-view replay-browser
```

The interactive terminal uses the same first-run session: start
`gex-terminal --demo`, press `p`, and select a replay. Pack inputs and generated
assets must never contain credentials, account identifiers, private payloads, or
licensed data without explicit redistribution rights.

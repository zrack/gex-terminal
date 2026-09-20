# Offline First-Use Build — September 20, 2026

Technical preparation is complete. This record identifies the local study
bundle and its automated rehearsal; no participants, activation measurements or
task times have been collected. [Study Build](../study-build.md) owns the
handoff procedure; [Product Validation](../product-validation.md) owns tasks,
scoring and consent. [GEX-STUDY-001](../work-packets/GEX-STUDY-001.md) owns change
review and closeout.

## Frozen identity

| Field | Recorded value |
| --- | --- |
| Study build | `offline-first-use-2026-09-20` |
| Source commit | `cb59b7f6cf9d681fa854196fe6bffb5b1102a8fd` |
| Application version | `0.5.0`, including the accepted replay-picker repair |
| Wheel | `gex_terminal-0.5.0-py3-none-any.whl` |
| Wheel SHA-256 | `9718b6c320562af35fb9990496aa1b79070e95105251fb5b7fe2b8bc1d4bad24` |
| Build manifest SHA-256 | `16de1ffb11194707e8188869d2757ff00bb54785d6401092bf242521127f6acd` |
| Dependency lock SHA-256 | `742477657ceb26cdcf03ff82ec10da01bccaa6356d41950fe16520c982cc8ff5` |
| Frozen Product Validation SHA-256 | `e8467bf286079a2ddc6750998aec3ac2b4c098d9b8a1bcc7a5b754108573c416` |
| Source archive SHA-256 | `cd54b20fdfab65471bdc7dd23bf6de3a336d40abe05011be4989362e15759d0e` |
| Build and rehearsal host | macOS 26.6 ARM64, CPython 3.12.13 |
| Build tools | build 1.5.0, setuptools 83.0.0, wheel 0.47.0, Twine 7.0.0 |
| Bound calculation/UI dependencies | NumPy 2.4.6, Textual 8.2.7; all 22 application dependencies pinned in the lock |
| Rehearsed terminal sizes | 140×42 and 180×54 |

The maintainer retains the bundle under ignored
`dist/study/offline-first-use-2026-09-20/`, with distributions, `source.tar`,
`build-manifest.json`, `requirements-lock.txt`, frozen `materials/`, rehearsal
records, `HANDOFF.md` and a 219-file `SHA256SUMS` inventory. A repository clone
does not contain those generated files; obtain the exact bundle from the
maintainer and verify its wheel checksum before use.
The convenience `materials/` copy contains the participant guides and canonical
documentation. Extract `source.tar` to browse technical links into source code;
those targets are retained in the archive rather than duplicated in materials.

The source archive and materials intentionally remain at the recorded source
commit. Later documentation commits record preparation and review; they do not
rebuild or relabel the frozen wheel. The original `v0.5.0` tag is unchanged and
does not identify this repaired build. Hashes are integrity checks, not signatures.

## Synthetic fixtures

| Catalog name | Identity | Installed input SHA-256 |
| --- | --- | --- |
| `zero-gamma-flip` | ES ×50; `gex_terminal/data/replays/es_zero_gamma_flip.jsonl` | `fabb925d53942deb2e9abe182659027946e6a8e04b529219e457ceb528952507` |
| `nq-research-loop` | NQ ×20; `gex_terminal/data/replays/nq_research_loop_v2.jsonl` | `1935529bdf4e594c56d26fdc8f5139f78d3eefbada8bbb70d7adb138c67b73c6` |

Both are bundled, owned synthetic inputs with redistribution allowed by their
catalog declarations. Their source coverage differs. The moderator uses each
verified pack's snapshot, model guide and receipt as its answer reference;
missing OI or direction evidence remains unavailable, not a failed participant
answer or an invented measurement. Keep fixture assignment with every task row.

## Recorded verification

- The committed source passed all 435 tests, including five documentation-link
  tests; compilation and patch hygiene passed. Independent review identified
  and verified fixes for literal-code heading slugs before the source freeze.
- Source and wheel distributions passed Twine. Two clean exports built with
  the same commit-derived `SOURCE_DATE_EPOCH` and recorded tools produced the
  same wheel SHA-256. This is reproducibility of this tested build recipe.
- The exact wheel installed into a fresh virtual environment outside the
  checkout with its 22 pinned dependencies. Imported package location and
  installed fixture bytes matched the declared installation. `pip check`,
  version and offline doctor passed. Dependencies were downloaded; this is not
  a network-free installer or a new-user clean-machine study.
- Both ES and NQ snapshots and portable packs were generated, receipt-verified
  and reproduced. Real Textual key events loaded ES ×50 and then NQ ×20 at
  both declared terminal sizes, with normal table navigation and picker cancel.
- Numerical, Databento offline, model-property, provider-fault and generated-chain
  performance checks passed. No provider extras, credentials or live data were
  used by the application rehearsal.
- All 20 final distinct rehearsal checks passed. The log retains one failed
  keyboard command and two earlier setup attempts caused by the one-off harness
  (package-name normalization, existing scratch directory and a missing config
  argument). Corrected reruns passed; these are not participant attempts.
- The updated architecture SVG was rendered and visually checked. C4 Mermaid
  source and component relationships were independently reviewed; Mermaid was
  not locally rendered.

## Participant boundary

Zero participant sessions are recorded. The owner must select a retention date
before recruitment and obtain the existing observation consent. Contact and
consent data stay outside the repository. Run the six observed sessions using
the frozen materials, preserving failures, assistance and not-started attempts.
Different source, dependencies, fixtures or scoring require a new identity;
record environment differences separately before collection. Phase 0/1 customer
acceptance and the live-provider gate remain open.

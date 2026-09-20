# Offline Study Build

This guide owns preparation and handoff of one exact offline first-use build.
[Product Validation](product-validation.md) owns the study tasks, scoring key,
participant selection and consent. [First Run](first-run.md) owns installation
and the application journey. A prepared bundle is not a completed user study.

The prepared [September 20 build record](studies/offline-first-use-2026-09-20.md)
identifies the repaired wheel, frozen materials, fixture hashes and rehearsal.
Use that exact artifact for this cohort; rebuilding creates a new candidate
unless its wheel and declared material/runtime identities match.

## Freeze the source and materials

Use a reviewed commit containing the [replay-picker repair](work-packets/GEX-UX-001.md).
Record the full source commit, Git tree, application version and build tools.
Build from a clean export of that commit with the existing
[contributor procedure](../CONTRIBUTING.md#verification). Keep the original
release tags unchanged. `0.5.0` alone cannot identify the repair.

Set `SOURCE_DATE_EPOCH` to the source commit timestamp for both builds. Preserve
the exact wheel SHA-256 and source archive, and compare a second independently
exported build using the same Python/build-tool versions. A matching wheel hash
establishes only the tested build recipe's byte reproducibility.

Copy the source commit's Product Validation, First Run, Demo Lab and model guide
into the handoff bundle, preserving their relative links with the repository
source archive. Hash those files. The Product Validation hash freezes the
scoring key and paper concepts as well as the task sequence; do not silently
edit them after collection starts.

Choose `zero-gamma-flip` (ES ×50) and `nq-research-loop` (NQ ×20). Record their
catalog names, package-relative paths, byte hashes, synthetic origin and
redistribution status. Keep the scenarios separate in task results: their
position-source coverage differs, and missing evidence must remain visible.

## Bundle inventory

Keep generated artifacts under ignored `dist/study/`, not in source control.
Use a distinct study-build directory and never overwrite a frozen bundle.

| Artifact | Purpose |
| --- | --- |
| Reviewed wheel | Exact application artifact supplied to participants |
| Source archive | Committed source, documentation and diagram provenance |
| `build-manifest.json` | Commit/tree, wheel identity, environment, fixture and material hashes, rehearsal evidence and limits |
| `requirements-lock.txt` | Exact installed application dependency versions for the declared environment |
| `materials/` | Frozen guides and scoring protocol copied from the source commit |
| `rehearsal/` | Automated synthetic checks and separately verified ES/NQ packs |
| `SHA256SUMS` | Integrity inventory of the handoff files, excluding itself |

These hashes detect changed bytes; they are not signatures or proof of origin.
The maintainer must deliver the reviewed checksum through a trusted channel.
Keep participant identities, contacts, consent and observations outside this
bundle in owner-controlled storage. Do not add files inside a verified Demo Lab
pack: its receipt requires an exact inventory.

## Rehearse outside the checkout

Create a fresh virtual environment, install the exact wheel with its recorded
dependency constraints, run `pip check`, and confirm the imported application
comes from that environment. Dependency downloads may use the network. The
application rehearsal needs no credentials, provider extras or live data.

Run version and offline doctor; exercise actual replay-picker key events at
140×42 and 180×54; verify ES ×50 and NQ ×20 identities. Generate, verify and
reproduce both Demo Lab packs using [Demo Lab](demo-lab.md#review-sequence).
Record commands, outcomes, Python/OS/architecture, terminal sizes and exact
dependency versions. Preserve failed attempts and explain any rerun.

A fresh environment on a developer's machine is an automated installation
rehearsal. It does not establish clean-machine customer activation, native
terminal accessibility or an unaided time-to-insight measurement. Tests and
moderator answer materials are not participant assistance evidence.

## Handoff and study start

Supply the wheel, checksum, dependency lock and frozen First Run guide. Install
with `python -m pip install -c requirements-lock.txt PATH_TO_REVIEWED_WHEEL` in
the participant's fresh environment. Record actual OS/architecture and Python
version; do not pool a different runtime with the frozen cohort without a
recorded amendment. Dependency constraints pin versions, not artifacts for
every platform; they are not a network-free installer.

The moderator retains the frozen protocol and answer key. Before recruiting,
the owner chooses the retention/deletion date and uses the existing consent
procedure. Assign de-identified participant IDs and record every failed,
assisted and not-started attempt. Installation success cannot be measured from
a preinstalled environment. Any source, dependency, fixture or scoring change
receives a new build/cohort identity before collecting further observations.

The next milestone remains six real observed task sessions. Their findings
determine the next engineering slice and distribution/support choice; build
preparation does not close those roadmap gates.

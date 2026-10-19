# Offline Study Build

This guide owns preparation and handoff of exact offline first-use builds.
[Product Validation](product-validation.md) owns the study tasks, scoring key,
participant selection and consent. [First Run](first-run.md) owns installation
and the application journey. A prepared bundle is not a completed user study.

The prepared [September 20 build record](studies/offline-first-use-2026-09-20.md)
identifies that cohort's repaired wheel, frozen materials, fixture hashes and
rehearsal. Preserve it unchanged. Guided session intake and Terminal checkpoint
handoff use a separate current-build cohort and the frozen GI-01 through GI-06
supplement in [Product Validation](product-validation.md). A matching version
number cannot substitute for source, wheel, runtime and material identities.

The prepared [October 18 guided-intake build](studies/guided-intake-2026-10-18.md)
binds the current wheel, separate cohort, synthetic fixtures and execution
evidence. Use that exact kit for its cohort; preserve both historical records.

For recruitment, use the separate
[participant-only delivery](studies/participant-delivery-2026-10-18.md) and
[Study Recruitment](study-recruitment.md) procedure. The 20-file participant
ZIP is delivery revision `guided-intake-2026-10-18-r1-participant-v1`; it
excludes moderator, scoring, answer-key and rehearsal materials. Its application,
dependency lock, synthetic captures and task guide retain the October cohort's
identities. Five links to omitted maintainer documents are plain text in its
help copies; GI-01 through GI-06 and scoring are unchanged. This is a recorded
delivery amendment, not a replacement of the frozen 86-file full kit. Reusable
blank recruitment sources and generation tooling are versioned through
[Study Recruitment](study-recruitment.md); generated archives and completed
personal records stay outside Git.

## Prepare the guided intake cohort

Commit the reviewed implementation and materials first. Use the same Python and
build tools intended for the study runtime. Prepare exact application dependency
constraints from the intended installed environment; remove editable/local URLs
and provider extras. The helper rejects anything other than unique exact
`name==version` pins, requires direct wheel dependencies to be covered and never
downloads or installs dependencies.

```bash
python scripts/build_study_kit.py \
  --commit FULL_REVIEWED_COMMIT_SHA \
  --study-id guided-intake-YYYY-MM-DD-rehearsal \
  --requirements-lock /path/to/requirements-lock.txt
```

The helper exports that exact commit twice, builds both wheels using the commit
timestamp as `SOURCE_DATE_EPOCH` and stops if their names or hashes differ. It
packages a source archive, exact wheel and dependency constraints, frozen docs,
the [guided protocol](study-kit/protocol.json), participant/moderator guides,
blank de-identified scorecards and synthetic ES/NQ captured-session files. The
captures are generated through the frozen commit's `CapturedSessionWriter`
using genuine fixture event timestamps; no provider data, wall-clock fallback
or personal account metadata is introduced. `fixture-answer-key.json` freezes
the final event index and as-of without inventing model coverage or level values.

Build logs and capture integrity are preparation checks. The initial manifest
explicitly marks installation and browser interaction `not_run`. Rehearse its
exact wheel outside the checkout, including local-capture inspection, selecting
a checkpoint, a scenario calculation, save/export and reproduction on a fresh
server with an empty workspace. Rehearse Terminal `w` separately. Preserve
failed attempts and distinguish all automated checks from observed participants.

Freeze the resulting execution record with the final kit using a new identity:

```bash
python scripts/build_study_kit.py \
  --commit SAME_REVIEWED_COMMIT_SHA \
  --study-id guided-intake-YYYY-MM-DD \
  --requirements-lock /path/to/requirements-lock.txt \
  --rehearsal-record /path/to/execution.json
```

The execution JSON uses schema `gex-terminal.study-rehearsal.v1`, exact
`source_commit` and `wheel_sha256`, integer `participant_sessions: 0`, and a
nonempty `checks` list. Every check has a name and explicit `passed`, `failed`
or `not_run` status; retain commands, runtime and artifact evidence with it.
The helper validates that identity binding and copies/hashes the entire record.
It does not independently establish the truth of reported observations.

Output is a new ignored `dist/study/STUDY_ID/` directory, sibling ZIP and ZIP
checksum. Existing directories, ZIPs or checksums are never replaced; failed
preparation retains its reserved identity and logs. `SHA256SUMS` covers every
kit file except itself. `verify_inventory` in the build helper also rejects
added files, changed bytes and links. Any amendment after freezing requires a
new identity and reviewed inventory. No existing release tag is moved.

## Freeze the source and materials

Use a reviewed commit containing the intended workflow and regression repairs.
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

Send the verified participant-only ZIP, reviewed checksum and personalized
consent separately. Retain the full frozen kit for moderation. The participant
delivery includes the wheel, dependency lock, task guide and user help. Install
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

# GEX-STUDY-001 — Offline First-Use Study Build

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L2
status: in_progress
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent reviewer and hosted CI
baseline: main@182822c27654216b62c380f467f195aeb2b105b6
branch: codex/offline-study-build-docs
created: 2026-09-20
```

## Authority and scope

The maintainer authorized preparation of the offline study build, local
Markdown heading-link validation, documentation ownership cleanup, architecture
and diagram reconciliation, contributor guidance, a pull request and merge to
`origin/main`. Use the existing wheel build and synthetic research workflows;
there is no new release mechanism, application behavior or package version.

[Study Build](../study-build.md) owns the repeatable handoff procedure and routes
to the exact frozen build record. [Product Validation](../product-validation.md)
continues to own participant tasks, scoring and consent. Architecture owns the
current system and diagram sources; roadmap owns remaining gates; changelog
owns delivery history. Generated bundles and rehearsal outputs stay outside Git.

## Acceptance

1. Local Markdown checks reject missing files and missing heading fragments,
   including same-document fragments, while ignoring external URLs and code
   examples. Focused cases cover heading normalization and duplicate anchors.
2. The study bundle identifies its committed source, wheel SHA-256, build
   environment, runtime dependency versions, synthetic ES/NQ input hashes and
   frozen participant instructions/scoring protocol. A second wheel build from
   that source is compared with the first; do not claim byte reproducibility
   without a matching digest.
3. Install the exact wheel into a fresh environment outside the checkout.
   Exercise doctor, ES/NQ identity, real replay-picker keys, portable pack
   verification and reproduction. Record the precise environment and assistance
   boundary. Package installation is permitted to download dependencies;
   application rehearsal uses only synthetic data and no provider credentials.
4. Audit root, topic, architecture, diagram and contributor documentation for
   correct ownership. Update affected statements and navigation without
   rewriting historical evidence or copying full references into the README.
5. Focused and full tests, compilation, distributions/Twine, independent review
   and hosted checks pass. Merge the reviewed PR and verify clean main against
   `origin/main` with a post-merge regression run.

## Evidence ceiling and recovery

This packet prepares a technical build and study materials. Automated rehearsal
is not a participant, unaided installation, task timing, design-partner
commitment or passed Phase 0/1 gate. Participant recruitment, consent and the
owner's retention date remain outside this preparation. Live observations,
provider readiness, model claims and original release tags are unchanged.

The wheel remains `0.5.0`; its exact commit and digest distinguish it from the
original tag. Future changes require a separate build/cohort identity. Recovery
is a reviewed revert of the bounded documentation/test change and withdrawal of
the affected local study bundle; no customer or research files are migrated.

## Verification and closeout

Pending the committed-source build, independent review and hosted checks.

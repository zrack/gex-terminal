# Good First Issues

These are issue-ready starter items for contributors who want to help without
needing live market-data credentials. Maintainers can copy one into GitHub,
apply `good first issue` and `help wanted`, and adjust scope as the codebase
changes.

## Existing provider queue — reviewed September 4, 2026

- [Databento issue #5](https://github.com/zrack/gex-terminal/issues/5) asks for
  dataset/schema selection, synthetic payloads, normalized mappings and known
  gaps. These are already owned by [Databento Fixture Mapping](databento-fixtures.md),
  packaged Databento fixtures and the offline certification tests. Do not assign
  a duplicate implementation. Administrative issue closure is separate from
  these shipped artifacts; live certification remains open.
- [Tradovate PR #10](https://github.com/zrack/gex-terminal/pull/10), inspected at
  `03d5ed80e93452c03a9ccce244cf1e671597f91b`, is an existing contribution for
  issue #4, not accepted live evidence. Its three-file diff adds a fixture and
  shape-only tests, not an adapter-to-consumer mapping test. The fixture's
  descriptive string includes `credentials`, so its own blanket substring
  assertion against `credential` fails. The entitlement/demo-access assertions
  need provider-source evidence, and the requested observed payload provenance
  is not established by labeling a fixture sanitized. No hosted checks were
  attached at inspection. Request changes within that contribution instead of
  implementing the same scope in parallel; do not merge or close issue #4 on
  this evidence. No provider access was attempted during this review.

## 1. Add Replay Alert Expectations For New Fixtures

Labels: `good first issue`, `help wanted`, `testing`, `replay`

Summary:
Add expected alert checks for one bundled replay fixture in the Replay Lab tests.

Why it helps:
Replay fixtures are most useful when contributors can tell whether a model or
parser change altered expected behavior.

Suggested scope:
- Add or extend a focused test in `tests/test_replay_lab.py`.
- Pick one session from `gex-terminal list-replays`.
- Assert one expected alert, gamma wall, strike-profile flip/nearest-neutral, or
  regime property.

Verification:

```bash
python -m unittest -v tests.test_replay_lab
```

## 2. Add A README Preview Refresh Script

Labels: `good first issue`, `help wanted`, `documentation`, `terminal-ui`

Summary:
Add a small maintainer script or documented Make-style command that refreshes
the generated README demo preview and optional onboarding asset.

Why it helps:
The project looks better when the README visual stays aligned with the actual
Textual terminal.

Suggested scope:
- Add a script under a maintainer-friendly location such as `scripts/`.
- Generate `assets/gex-terminal-demo-lab.svg` through the documented Demo Lab
  workflow; optionally refresh the replay-browser onboarding asset too.
- Avoid committing generated local demo packs.

Verification:

```bash
gex-terminal demo-lab /tmp/gex-readme-preview --replay-session zero-gamma-flip
```

## 3. Validate Markdown Heading Links

Labels: `good first issue`, `help wanted`, `documentation`, `testing`

Summary:
Extend the documentation link contract to verify local `#heading` fragments in
addition to file existence.

Why it helps:
The documentation index now links many canonical guides. A renamed heading can
break navigation even when the target file still exists.

Suggested scope:
- Extend `DocumentationLinkContractTests` in `tests/test_release_contract.py`.
- Normalize common GitHub-style Markdown heading fragments deterministically.
- Add focused valid and invalid fragment cases without checking external URLs.

Verification:

```bash
python -m unittest -v tests.test_release_contract.DocumentationLinkContractTests
```

## 4. Document One Provider Payload Shape

Labels: `good first issue`, `help wanted`, `adapter`, `documentation`

Summary:
Add sanitized notes for one provider-shaped fixture and explain how it maps into
the normalized consumer payload.

Why it helps:
Provider adapters get easier when contributors can compare raw fields against
the normalized JSONL contract.

Suggested scope:
- Pick one fixture in `gex_terminal/data/provider_fixtures/`.
- Update the matching provider doc in `docs/`.
- Do not include credentials, account IDs, or private market-data payloads.

Verification:

```bash
python -m unittest -v tests.test_provider_fixture_lab
```

The previously proposed dedicated NQ replay is now shipped as
`nq-research-loop`; see [Demo Lab](demo-lab.md). Choose a distinct regression or
scenario instead of duplicating its fixture.

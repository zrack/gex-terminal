# Good First Issues

These are issue-ready starter items for contributors who want to help without
needing live market-data credentials. Maintainers can copy one into GitHub,
apply `good first issue` and `help wanted`, and adjust scope as the codebase
changes.

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

## 5. Add A Dedicated Synthetic NQ Replay

Labels: `good first issue`, `help wanted`, `replay`, `testing`

Summary:
Add one small schema-v2 NQ replay whose own rows use the NQ multiplier and a
declared deterministic structural expectation.

Why it helps:
The packaged replay catalog is ES-focused. A dedicated NQ fixture would exercise
symbol and multiplier handling without requiring live data or implying provider
certification.

Suggested scope:
- Add a synthetic JSONL replay under `gex_terminal/data/replays/`.
- Use schema-v2 contract identity, event time, expiry, IV provenance, and the NQ
  multiplier consistently.
- Register it in the replay catalog and add one focused validator or Replay Lab
  expectation.
- Label the scenario synthetic and avoid copied licensed market data.

Verification:

```bash
gex-terminal validate-fixture gex_terminal/data/replays/NEW_NQ_FIXTURE.jsonl
python -m unittest -v tests.test_replay_lab tests.test_release_contract
```

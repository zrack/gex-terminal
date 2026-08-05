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

## 2. Add A Terminal Onboarding Screenshot Refresh Script

Labels: `good first issue`, `help wanted`, `documentation`, `terminal-ui`

Summary:
Add a small maintainer script or documented Make-style command that refreshes
the README onboarding screenshot.

Why it helps:
The project looks better when the README visual stays aligned with the actual
Textual terminal.

Suggested scope:
- Add a script under a maintainer-friendly location such as `scripts/`.
- Use `--screenshot-view replay-browser`.
- Avoid committing generated local demo packs.

Verification:

```bash
gex-terminal --demo --screenshot /tmp/gex-terminal-onboarding.svg --screenshot-view replay-browser
```

## 3. Add Session Store Example Output Fixture

Labels: `good first issue`, `help wanted`, `documentation`, `exports`

Summary:
Add a tiny sanitized example output fixture or regression assertion for
`session-store save`, `list`, and `report` against a bundled replay session.

Why it helps:
New contributors can practice the historical research workflow without a live
provider.

Suggested scope:
- Extend `tests/test_session_store.py` with a small inline/sanitized record.
- Use `/tmp` or another ignored folder for generated output.
- Explain that `historical_sessions/` is ignored by Git.

Verification:

```bash
gex-terminal session-store save --replay-session zero-gamma-flip --session-store-dir /tmp/gex-store
gex-terminal session-store list --session-store-dir /tmp/gex-store
gex-terminal session-store report /tmp/gex-store/session_store.md --session-store-dir /tmp/gex-store
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

## 5. Add A Small Snapshot Export Assertion

Labels: `good first issue`, `help wanted`, `testing`, `exports`

Summary:
Add one focused assertion for Markdown or CSV snapshot exports.

Why it helps:
Exports are how users share research, so small format regressions matter.

Suggested scope:
- Extend `tests/test_snapshot_formats.py`.
- Check one field that appears in both snapshot metrics and the human-readable
  output.
- Keep the test deterministic and fixture-based.

Verification:

```bash
python -m unittest -v tests.test_snapshot_formats
```

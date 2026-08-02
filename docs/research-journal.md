# Historical Research Journal

The Historical Research Journal saves replay-session studies as local JSON
entries, then lets you list, compare, and export them later. It is designed for
offline research before live market-data access is available.

## Why Use It

- Keep a dated record of replay-session behavior while changing the model.
- Compare gamma wall, zero-gamma, call wall, put wall, net-GEX, imbalance, and
  replay-alert changes between saved entries.
- Export Markdown for issues or discussions, CSV for spreadsheet review, and
  JSON for reproducible baseline checks.
- Keep generated research output local by default.

The default journal directory is `research_journal/`, and it is ignored by Git.
Do not store live provider payloads, credentials, account identifiers, or
proprietary data in journal entries.

## Add Entries

Save a replay session into the local journal:

```bash
gex-terminal journal add --replay-session trend-day
gex-terminal journal add --replay-session zero-gamma-flip
```

Entries are written under:

```text
research_journal/entries/
```

Each entry contains:

- Replay source metadata.
- Runtime model inputs such as symbol, expiry, risk-free rate, and multiplier.
- Session summary metrics.
- Replay alerts.
- Timeline events.
- Final computed snapshot.

Bundled replay-journal entries use the ES replay fixture context so local `.env`
symbol overrides do not mislabel the synthetic research sessions.

## List And Compare

List saved entries:

```bash
gex-terminal journal list
```

Compare the previous entry to the latest entry:

```bash
gex-terminal journal compare
```

Compare explicit refs:

```bash
gex-terminal journal compare 1 latest
gex-terminal journal compare first previous
gex-terminal journal compare 20260801_ latest
```

Supported refs are:

- `latest` or `last`
- `previous` or `prev`
- `first`
- 1-based entry index from `journal list`
- exact entry ID
- unique entry ID prefix

## Export Reports

Write a Markdown report:

```bash
gex-terminal journal report research_journal/journal.md
```

If no output path is provided, the command writes
`research_journal/journal.md`.

Write machine-readable formats:

```bash
gex-terminal journal report research_journal/journal.csv
gex-terminal journal report research_journal/journal.json
```

Markdown is best for GitHub discussions and issues. CSV is useful for quick
level-delta review. JSON preserves the complete saved journal report.

## Alternate Journal Directory

Use a separate directory when testing a branch or preparing examples:

```bash
gex-terminal journal add --journal-dir /tmp/gex_journal --replay-session gap-fade
gex-terminal journal list --journal-dir /tmp/gex_journal
gex-terminal journal report /tmp/gex_journal.md --journal-dir /tmp/gex_journal
```

## Contributor Workflow

1. Run or update a replay fixture.
2. Save a journal entry with `gex-terminal journal add --replay-session NAME`.
3. Compare against the previous entry with `gex-terminal journal compare`.
4. Export Markdown for an issue or pull request.
5. Include the fixture, model, or export change that explains the journal delta.

This gives contributors a durable research trail without requiring paid data,
live credentials, or screenshots for every model experiment.

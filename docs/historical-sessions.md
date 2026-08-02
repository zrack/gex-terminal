# Historical Session Store

The Historical Session Store saves computed GEX snapshots as local records. It
is separate from the Historical Research Journal: the journal is for replay-study
notes and comparisons, while the session store is a lightweight archive of
snapshot records that can later support live-day replay and day-over-day review.

The default folder is `historical_sessions/`, which is ignored by Git.

## Save A Session

Save a replay snapshot:

```bash
gex-terminal session-store save --replay-session zero-gamma-flip
```

Add a human label:

```bash
gex-terminal session-store save --replay-session trend-day --session-label trend-baseline
```

Use an explicit local folder:

```bash
gex-terminal session-store save --replay-session zero-gamma-flip --session-store-dir /tmp/gex-store
```

Each saved record contains:

- timestamp and record ID
- source name and snapshot timestamp
- symbol, DTE, risk-free rate, and contract multiplier
- top-line levels: spot, net GEX, gamma wall, zero gamma, call wall, put wall,
  imbalance, and strike count
- feed-quality summary when available
- the full computed snapshot

## List Records

```bash
gex-terminal session-store list
gex-terminal session-store list --session-store-dir /tmp/gex-store
```

## Export A Report

Reports can be written as Markdown, CSV, or JSON:

```bash
gex-terminal session-store report historical_sessions/session_store.md
gex-terminal session-store report historical_sessions/session_store.csv
gex-terminal session-store report historical_sessions/session_store.json
```

If two or more records exist, the report includes a latest-record comparison for
net GEX, gamma wall, zero gamma, call wall, put wall, and imbalance.

## Contributor Notes

- Keep generated `historical_sessions/` output local.
- Use replay sessions for examples unless you have permission to share delayed
  or live provider data.
- Strip credentials, account IDs, and proprietary payload details before sharing
  store records in an issue.
- Prefer Markdown or CSV reports for GitHub discussion; JSON is better for
  fixtures and regression review.

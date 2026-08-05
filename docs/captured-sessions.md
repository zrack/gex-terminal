# Captured Sessions

Captured sessions turn a replay or live normalized-message stream into a local,
integrity-checked research artifact. They preserve the order and source timing of
the normalized messages that reached the consumer. Built-in adapters do not put
raw provider frames or broker credentials into those messages, but the capture
writer preserves arbitrary extension fields and does not perform secret
redaction. Adapter authors must keep sensitive fields out, and users must inspect
captures before sharing them.

## Record A Session

Capture a bundled replay to an explicit path:

```bash
gex-terminal --replay-session trend-day \
  --record-session \
  --capture-path /tmp/trend-day.gex-session.jsonl \
  --capture-label "trend-day round trip"
```

Capture a live, read-only provider stream:

```bash
gex-terminal --mode live --provider tradovate --symbol ES --record-session
```

When `--capture-path` is omitted, completed captures are written under
`historical_sessions/captures/`. Supplying `--capture-path` also enables
recording. Seeded `--demo` state cannot be captured because it is not an event
stream; use a bundled replay session instead.

Capture files can contain licensed market data. Keep them local unless the data
license permits redistribution. Git ignores repo-local capture paths matching
`*.gex-session.jsonl` and `*.gex-session.jsonl.partial` by default; only
force-add one after reviewing its license and contents.

The in-terminal replay browser cannot switch sessions while recording is active.
Consumer resets are not normalized market events, so allowing a switch would
create an ambiguous capture boundary. Finish the current capture and start a new
run for the next replay.

## File Contract

The append-only JSONL schema is `gex-terminal.captured-session.v1`:

1. A header records a session ID, source, label, model inputs, creation time,
   and timing contract.
2. Each event records a contiguous capture sequence, normalized message,
   source event time, receipt time, receipt offset, message hash, and record
   hash.
3. A complete footer records counts, schema versions, time bounds, feed quality,
   and aggregate SHA-256 digests.

The writer first creates `OUTPUT.partial`, flushes and synchronizes the complete
footer, then atomically renames the file to `OUTPUT`. An interrupted or failed
run keeps the `.partial` file for diagnosis. Partial files, missing footers,
sequence gaps, changed messages, changed records, or changed aggregate hashes
fail integrity verification and cannot be replayed.

The capture sequence is authoritative. `event_time` determines replay pacing;
it does not reorder records. If a normalized message has no usable event time,
the recorder uses receipt time and counts that fallback in the footer.

## Replay A Capture

Replay a completed capture with its event-time clock:

```bash
gex-terminal --captured-session /tmp/trend-day.gex-session.jsonl
```

`--replay-clock auto` selects event time for captured sessions and fixed delay
for legacy normalized JSONL. Timing controls are:

```bash
gex-terminal --captured-session /tmp/trend-day.gex-session.jsonl \
  --replay-clock event \
  --replay-speed 20 \
  --replay-max-gap 2
```

- `--replay-speed N` divides source-time gaps by `N`.
- `--replay-max-gap SECONDS` caps a source gap before speed scaling.
- `--replay-clock none` replays without intentional delay.
- `--strict-event-time` fails when the selected replay item lacks a usable time
  or when event time regresses. Completed captures always carry an envelope
  event time, using recorded receipt time when the source message lacked one.

Without strict mode, a regressing event time is clamped to a zero delay and
reported as a feed-quality note while capture order is preserved.

Noninteractive snapshot workflows, including exports, overlays, sensitivity,
session-store saves, and journal entries, always replay captures without
intentional delay. Event-time pacing applies only to the interactive terminal.

## Inventory And Research Workflows

List complete, integrity-verified captures in the local session store:

```bash
gex-terminal session-store captures
gex-terminal session-store captures --session-store-dir /tmp/gex-store
```

Add a captured market day to the Historical Research Journal:

```bash
gex-terminal journal add \
  --captured-session /tmp/trend-day.gex-session.jsonl \
  --journal-dir /tmp/gex-journal
```

The session store inventories event artifacts; its existing `save`, `list`, and
`report` actions manage computed snapshot records. The journal replays a capture
through the normal consumer and model path before saving a research entry, so a
later model version can be compared against the same event evidence.

## What A Capture Proves

A verified capture is internally consistent under its in-file SHA-256 values: it
detects truncation, sequence gaps, accidental corruption, and edits whose hashes
were not reconciled. Because the hashes are unkeyed and stored in the same file,
they can be recomputed. Without an externally anchored digest or signature, the
format does not prove authenticity, historical immutability, or who created the
capture.

Verification also does not prove that a provider payload was complete, that
implied volatility was native rather than a fallback, that the position proxy
represents dealer inventory, or that the result predicts price action. Preserve
the capture together with separately retained snapshot model provenance and
provider-health evidence when making comparisons.

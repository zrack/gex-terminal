# Tradovate Raw-Payload Capture

Use `tradovate-capture` to collect a bounded, private sample of actual Tradovate
REST contract metadata and WebSocket market-data frames. This is the preparation
tool for [issue #4](https://github.com/zrack/gex-terminal/issues/4), which remains
open until actual ES **and** NQ samples are reviewed and their mappings validated.
Demo or live provider responses qualify as actual payloads; constructed fixtures
do not. Building or successfully running this collector does not certify the
adapter, establish complete chain coverage, or change its `scaffold` readiness.

The collector never places orders. It uses authentication, allowlisted contract
queries, and market-data authorization/subscription operations. It does not
request account, position, order, or personal-user information. Authentication
payloads, tokens, headers, and outgoing WebSocket frames are excluded from saved
evidence. Retained market data can still be licensed or sensitive; the output is
private evidence requiring review, not an automatically shareable fixture.

## Before Connecting

1. Confirm API access for your account. Tradovate's published
   [retail access requirements](https://tradovate.zendesk.com/hc/en-us/articles/4403105829523-How-Do-I-Get-Access-to-the-Tradovate-API)
   include a live account holding more than $1,000, the CME agreement, and the API
   Access add-on. Check eligibility with the provider for a prop/funded account
   before purchasing access. The demo REST environment does not waive access or
   data-rights requirements.
2. Give the key **Contract Library** and **Market Data** read-only access. Orders,
   Positions, and Account Information can remain denied. The provider's
   [permission guide](https://tradovate.zendesk.com/hc/en-us/articles/4408873526547-How-Do-I-Change-My-API-Key-Permissions)
   describes these domains separately. Confirm the actual account's ES/NQ
   options subscriptions; do not infer them from futures quotes or the demo flag.
3. Decide whether the applicable agreements allow local retention and the intended
   review/sharing. Record that decision in your own capture policy. The
   [Capture Governance](capture-governance.md) schema is required even for demo
   payloads. Its packaged synthetic example does not authorize provider capture.
4. Use a private working directory outside the repository and participant study
   folders. Keep credentials in its local `.env`, using the field names from
   the repository's [.env.example](../.env.example). Protect that file with
   owner-only permissions. Do not paste credentials or raw captures into an
   issue, chat, or pull request.

Provider access references above were reviewed on 2026-10-19. The software cannot
verify the operator's agreement, subscriptions, retention decision, or authority
to redistribute samples.

## Prepare The Local Policy

Save your policy separately from capture output, for example as
`capture-policy.json` in the private working directory. Use the complete example
in [Capture Governance](capture-governance.md#policy-contract), replacing its ID,
rights basis, retention period/location/owner, redaction profile, and research-use
decision with your actual decisions. A suitable redaction profile describes
manual review of raw provider contract and market-data observations; the
normalized-session profile alone does not describe this output.

Keep passwords, identifiers, tokens, and market-data samples out of the policy.
`rights.redistributable=false` permits no automatic sharing. Research use can be
`prohibited` for a private mapping review. The policy is a declaration of
authority; validation does not grant rights or enforce retention deletion.

Validate locally before any connection:

```bash
gex-terminal capture-policy-validate capture-policy.json
```

Use a reviewed installation containing `tradovate-capture`; run
`gex-terminal tradovate-capture --help` to check availability. A frozen participant
study kit predating this command must retain its original wheel and materials.

## Capture ES, Then NQ

Run from the private working directory containing your `.env` and policy. The
commands below use new output directories; replace the run suffix for every
attempt. The command refuses an existing target rather than replacing evidence.
Its parent must already exist; symlink paths and destinations inside Git
checkouts are refused. Choose a normal private directory outside the repository,
even though `.gitignore` also excludes common capture filenames.
No connection is opened without both the explicit network acknowledgement and a
valid capture policy.

```bash
umask 077
gex-terminal tradovate-capture es-demo-run-001 \
  --ack-live-network --capture-policy capture-policy.json \
  --tradovate-environment demo --symbol ES \
  --capture-duration 60 --max-option-contracts 12

gex-terminal tradovate-capture nq-demo-run-001 \
  --ack-live-network --capture-policy capture-policy.json \
  --tradovate-environment demo --symbol NQ \
  --capture-duration 60 --max-option-contracts 12
```

Prefer an active market window so matching quotes have a chance to arrive. The
duration bounds the entire authentication, discovery, and observation run;
cleanup has a separate allowance of at most one second. A slow discovery may leave little
streaming time. A quiet or permission-denied run is evidence of that attempt,
not proof that a field or product is unavailable everywhere. Review its manifest
before trying again in a new directory.

Discovery includes the read-only `contract/getoptionschain` operation and
available contract/maturity dependencies. Subscription selection is bounded by
the returned contract identities; it does not depend on the current adapter's
unverified strike/option-side aliases. It cannot promise a complete chain, a
balanced calls/puts sample, or multiple expiries. If the sample lacks the needed
contracts, retain that limitation and make a separately reviewed follow-up run.

## Output And Limits

Each new output directory is created with owner-only permissions (`0700`), with
owner-only files (`0600`):

| File | Purpose |
| --- | --- |
| `manifest.json` | `gex-terminal.tradovate-raw-capture.v1` run identity, limits, policy identity, request/subscription accounting, omissions, file hashes, status/outcome, and evidence limits |
| `rest.jsonl` | Received time, method/path, allowlisted arguments and HTTP status; eligible successful response text is retained in `raw_body` |
| `websocket.jsonl` | Received time, frame index/prefix, source/omitted event counts, and retained `raw_event` substrings with their original event indices |

The manifest binds the capture-policy schema, ID, and SHA-256; it does not copy
the policy's free-text decisions or credentials. Keep the matching policy and
your private access/entitlement notes separately. A file hash establishes local
consistency, not independent proof that bytes came from Tradovate.

For a fully retained eligible WebSocket frame, `raw_frame` contains the original
text. Mixed frames exclude authentication or unsafe events while keeping eligible
market events in original order and preserving their exact event substrings;
their `raw_frame` is `null`. Known private fields, credential literals, provider
error bodies, invalid/duplicate-key/nonstandard JSON, unsupported non-quote
events and protocol controls are excluded with accounting. Safety checks omit
the affected body/event rather than inventing replacement market fields.

Default bounds are two maturities, 12 contract-library requests, 12 option
subscriptions plus selected underlying contracts, 1,000 received frames
(including protocol controls), 16 MiB of retained output including its manifest
reserve, and 1 MiB per response/frame. The corresponding controls are `--capture-max-maturities`,
`--capture-max-requests`, `--max-option-contracts`, `--capture-max-frames`,
`--capture-max-bytes`, and `--capture-max-frame-bytes`. These are safety/sample
limits, not a statement of adequate market coverage. Limit, cancellation,
malformed-input, and provider failures must be read from the run accounting;
an output directory alone is not successful payload evidence.

The contract-request cap excludes the single authentication attempt, whose
response is also bounded by `--capture-max-frame-bytes` and is never saved.
Authentication and contract HTTP requests do not follow redirects. Before any
WebSocket application message, the collector verifies that the final connected
endpoint is secure `md.tradovateapi.com:443/v1/websocket` with no user information.
An unknown or mismatched endpoint is closed with `websocket_target_rejected`;
no Tradovate token is sent unless that check passes. The WebSocket library may
perform unauthenticated redirected handshakes before the final endpoint check,
so this is an authorization-destination guard, not a guarantee against every
redirect connection.

The collector does not retry authentication or reconnect a failed stream; use a
new directory for a separately reviewed attempt. A task sends protocol heartbeats independently
of incoming market traffic and acknowledgement waits; its failure interrupts the
observation rather than leaving a stalled receive running until the deadline.
If receive and heartbeat tasks fail together, both exceptions are retrieved so
an abandoned task cannot emit raw provider error text through orphan-task logs.

`status` is `failed`, `partial`, or `complete`; `outcome` explains the stop. A
normal bounded observation ends at `duration_limit` and is labeled truncated
because it is a finite sample. It can still have `status=complete`: that means the
bounded collection ran successfully, not that the full chain was captured or
validated. `complete` additionally requires completed subscriptions, an observed
quote joined to sampled option metadata, no omitted REST bodies/invalid frames
or unsafe/unsupported events, and completed cleanup. Expected protocol-control
and authorization exclusions are counted separately. An authentication success alone can
only support a partial run. Inspect the selection and per-event omissions even
on a complete run. The manifest always leaves its `review` decisions unapproved,
including `issue_4_may_close=false`; completeness is not mapping validation.

Unknown market-data fields remain useful shape evidence. The collector preserves
eligible provider data before normalization and records safety omissions. It is
not a byte-for-byte packet recorder: HTTP transport envelopes, authentication,
outgoing frames, and omitted unsafe material are not reproduced. Inspect the
manifest's omission accounting before interpreting absence as a provider fact.
The tool does not automatically sanitize a complete sample for publication.

## Review Before Sharing Or Closing #4

Keep the original directory private and unchanged. Create a separate reviewed
derivative only when the agreements permit it. Review all retained fields and
strings for credentials, tokens, account/user/subscription identifiers, private
paths, and other personal data. Automatic safeguards cannot establish that a
sample is free of all private information. Preserve contract relationships if
IDs need stable pseudonyms; do not change strikes, expiry semantics, JSON types,
timestamps, quantity semantics, or IV presence/absence to make a fixture pass.
Document every transformation and the source run/file identities.

For each of ES and NQ, retain enough actual evidence to join chain/contract and
maturity metadata to quotes for an underlying and representative call/put option
contracts. Review strike, expiry/timezone, side, contract/underlying identity,
price, volume versus OI, timestamps, multiplier, and IV availability/units. If
native IV is absent, record that finding and the resulting model limitation.
Record environment, observation time, permissions, subscriptions, omissions, and
observed gaps without including private identifiers.

After the permitted sanitized derivatives are reviewed, add explicit observed
fixtures under `gex_terminal/data/provider_fixtures/`, validate them through the
production adapter/consumer path, repair demonstrated mappings, and update
[Market-Data Adapters](adapters.md). Only that reviewed actual ES/NQ evidence can
satisfy #4. Broader coverage, latency, reconnect behavior, quantitative input
quality, and provider readiness require their own observation and decisions.

Raw capture is distinct from two existing workflows:

- [Captured Sessions](captured-sessions.md) records normalized consumer events
  for replay and Wind Tunnel intake. These raw files are not captured sessions
  and cannot be opened directly in Wind Tunnel or registered as a research
  corpus session.
- `tradovate-certify` emits a redacted bounded diagnostic report from the adapter
  and consumer. A transport pass neither supplies raw shape evidence nor proves
  quantitative options readiness.

Regression tests use mocked HTTP/WebSocket boundaries and constructed payloads.
They validate collection, bounded cleanup, exclusions and refusal gates; they
do not supply the actual ES/NQ observations required to close #4.

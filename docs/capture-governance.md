# Capture Governance

Live session capture is fail-closed. Before `gex-terminal` opens a live provider
connection for `--record-session` or `--capture-path`, the operator must supply
a valid, versioned policy that records explicit decisions about data rights,
retention, redaction, and research use.

The policy records the operator's decision. It does not grant provider rights,
enforce a provider agreement, automatically delete retained files, or make a
capture redistributable. Confirm those obligations outside the application.

## Policy Contract

The current schema is `gex-terminal.capture-policy.v1`. Unknown schemas,
missing or extra fields, pending/unknown statuses, invalid retention periods,
disabled redaction review, and empty decision text are rejected.

```json
{
  "schema": "gex-terminal.capture-policy.v1",
  "policy_id": "databento-es-certification-2026-08",
  "rights": {
    "status": "licensed",
    "basis": "Operator reviewed the applicable provider agreement.",
    "redistributable": false
  },
  "retention": {
    "mode": "time_limited",
    "days": 30,
    "storage": "owner-only local session store",
    "owner": "named capture operator"
  },
  "redaction": {
    "status": "required",
    "profile": "normalized-no-sensitive-identifiers-v1",
    "review_before_sharing": true
  },
  "research_use": {
    "status": "approved",
    "scope": "internal method comparison only"
  }
}
```

Allowed rights statuses are `owned`, `licensed`, and `public_domain`. Retention
must be either `time_limited` with `days` from 1 through 3650, or `indefinite`
with an explicit JSON `null` for `days`. Research use must be explicitly
`approved` or `prohibited`; both require a scope explaining the boundary.
Provider capture always requires redaction and review before sharing.

Policy files must not contain credentials, account or subscription identifiers,
or licensed payload samples. Store the policy separately from captured data.

## Validate Before Capture

Validate without opening a provider connection:

```bash
gex-terminal capture-policy-validate capture-policy.json
```

The validator prints the policy ID, schema, and SHA-256 identity. A live capture
must then provide that policy:

```bash
gex-terminal --mode live --provider databento \
  --record-session \
  --capture-policy capture-policy.json
```

The captured-session header retains only the policy ID, schema, and SHA-256—not
the policy's decision text. Replay capture does not require a policy because it
does not open a live feed, but supplying one records the same identity.

## Corpus Eligibility Is A Separate Gate

A valid policy permits the configured capture workflow; it does not by itself
make the result eligible for research. A policy with
`research_use.status=prohibited` can be attached to a private capture, but that
capture cannot enter a research corpus.

Register a captured session only with the exact policy used at capture time:

```bash
gex-terminal corpus-register /tmp/gex-corpus \
  session.gex-session.jsonl captured-session-metadata.json \
  --capture-policy capture-policy.json
```

Registration fails unless all of these conditions hold:

- the source is a complete, integrity-verified captured session and metadata
  declares `source_kind=captured_session`;
- the supplied policy's schema, policy ID, and computed SHA-256 exactly match
  the identity embedded in the capture header;
- `research_use.status` is `approved`;
- metadata rights status and `rights.redistributable` exactly match the policy;
- metadata declares `redaction_status=verified`.

The corpus event stores the policy identity and research-use decision, not the
policy's free-text basis. Passing this gate verifies declared authority and
identity consistency only; it does not grant rights, validate the provider
agreement, or prove that redaction review was substantively correct.

## Logging And Sharing Boundary

The command-line runtime defaults to `WARNING`. Set `GEX_LOG_LEVEL` or pass
`--log-level` with `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`. Unknown
values fail before runtime startup. Every configured CLI log handler recursively
redacts credential fields, account/subscription identifiers, provider payload
fragments, bearer tokens, and configured credential substrings.

Redacted logs do not make captured market data shareable. Captures preserve
normalized messages and may still contain licensed observations, so perform the
policy's required review before sharing, corpus registration, or publication.

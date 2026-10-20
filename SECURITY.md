# Security Policy

`gex-terminal` handles broker and market-data credentials through local
environment variables. Please do not commit credentials, account identifiers,
API tokens, session tokens, or private market-data entitlement details.

## Supported Versions

This project is pre-1.0. The current source/package version is `0.6.0`.
Annotated version tags identify their verified merged trees and remain
unchanged. Later fixes can share that package version, so retain the exact
source commit and wheel SHA-256 when reporting a problem or reproducing a
receipt. No published PyPI artifact or hosted GitHub Release is claimed.
Security fixes target the latest `main` branch.

## Reporting a Vulnerability

If you find a credential-handling issue, token exposure path, or unsafe logging
behavior, please do not open a public issue with sensitive details.

Instead, contact the maintainer privately through GitHub or by using GitHub's
private vulnerability reporting if it is enabled for the repository.

Include:

- A short description of the issue.
- The affected command or data mode.
- Steps to reproduce with sanitized inputs.
- Whether any credential, token, or account data could be exposed.

## Credential Safety

- Keep real credentials in `.env`, not `.env.example`.
- Confirm `.env` is not staged before committing.
- Remove tokens, account IDs, and private entitlement details from logs.
- Runtime logging defaults to `WARNING`. `GEX_LOG_LEVEL` and `--log-level`
  accept only `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`; configured CLI
  handlers apply central recursive redaction before formatting output.
- Prefer demo or replay mode when sharing screenshots or bug reports.
- Review redacted support bundles before sharing. Private research backups and
  retention plans are not support attachments; see [Local Support](docs/local-support.md)
  for their permissions, recovery and explicit-deletion boundaries.
- Treat captured sessions as potentially licensed market data. The capture
  format stores normalized messages rather than raw provider frames, but that
  does not make the data redistributable.
- Repository-local `*.gex-session.jsonl` captures and their `.partial` files are
  ignored by default. Review license and content before deliberately force-adding
  one.
- Do not share `.partial` captures as evidence; they are intentionally
  incomplete and cannot pass integrity verification.
- Live capture requires an explicit policy for rights, retention, redaction, and
  research use before the provider connection opens. A policy records an
  operator decision; it does not grant rights or make captured data shareable.
  See [Capture Governance](docs/capture-governance.md).
- Run `tradovate-certify` or `databento-certify` only with the explicit
  `--ack-live-network` flag. Their reports are designed to be redacted, but
  review every artifact before sharing it.
- Never paste Tradovate access tokens, market-data tokens, authorization frames,
  usernames, client secrets, or account identifiers into issues or fixtures.

## Local Wind Tunnel And Saved Data

- Wind Tunnel serves on IPv4 loopback (`127.0.0.1`) and requires the launch
  session's capability for API access. Host and origin checks reject other
  origins. Keep the full launch URL, its `#cap=` fragment, and capability headers
  private. A screenshot or browser address bar can expose the launch URL.
- Use the provided starter or CLI locally. The current server is not a remote
  deployment, shared authentication service, or authorization boundary against
  someone who controls your operating-system account.
- The browser can select server-registered sources or inspect a bounded local
  capture upload. It cannot request arbitrary server filesystem paths. Large
  saved sessions use operator-configured paths through the saved-data starter;
  this does not enable provider access or downloads.
- Checkpoints and full saved receipts embed calculation inputs, contract rows,
  source times, and assumptions. A compact comparison response is only a
  display projection; saving still creates a full portable receipt. Treat both
  checkpoints and receipts as potentially licensed private market data, even
  when an integrity or reproduction check passes.
- Saved-data registrations can contain private local paths and source hashes.
  Keep the adjacent research folder, receipt workspace, installation records,
  exported results, and backups out of public commits and support attachments
  unless their contents and sharing rights have been reviewed.
- Receipt storage rejects symlinks, unrecognized files, replacement writes,
  and exhausted quotas. These checks preserve existing research; they do not
  encrypt it, grant redistribution rights, or enforce a retention/deletion
  policy. See [Local Support](docs/local-support.md) and
  [Wind Tunnel](docs/wind-tunnel.md) for recovery and storage details.

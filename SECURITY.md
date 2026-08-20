# Security Policy

`gex-terminal` handles broker and market-data credentials through local
environment variables. Please do not commit credentials, account identifiers,
API tokens, session tokens, or private market-data entitlement details.

## Supported Versions

This project is pre-1.0. The source/package version is `0.3.0`, but this
repository does not claim a published PyPI artifact or release tag. Security
fixes target the latest `main` branch.

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
- Prefer demo or replay mode when sharing screenshots or bug reports.
- Treat captured sessions as potentially licensed market data. The capture
  format stores normalized messages rather than raw provider frames, but that
  does not make the data redistributable.
- Repository-local `*.gex-session.jsonl` captures and their `.partial` files are
  ignored by default. Review license and content before deliberately force-adding
  one.
- Do not share `.partial` captures as evidence; they are intentionally
  incomplete and cannot pass integrity verification.
- Run `tradovate-certify` only with the explicit `--ack-live-network` flag. Its
  report is designed to be redacted, but review any artifact before sharing it.
- Never paste Tradovate access tokens, market-data tokens, authorization frames,
  usernames, client secrets, or account identifiers into issues or fixtures.

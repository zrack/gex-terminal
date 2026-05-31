# Security Policy

`gex-terminal` handles broker and market-data credentials through local
environment variables. Please do not commit credentials, account identifiers,
API tokens, session tokens, or private market-data entitlement details.

## Supported Versions

This project is pre-1.0. Security fixes will target the latest `main` branch
until formal releases exist.

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

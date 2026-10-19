---
name: Provider adapter
about: Request or propose a market-data provider adapter
title: "[Adapter]: "
labels: adapter, enhancement
assignees: ""
---

## Provider

Name the broker, exchange, replay source, or market-data API.

## Data Availability

- Underlying price ticks:
- Options volume or trades:
- Open interest or statistics:
- Implied volatility:
- Strike/expiration/call-put metadata:
- Event-time and sequence fields:
- Stable contract identity and multiplier:
- Quantity semantics (incremental or cumulative):
- Live, delayed, demo, or historical:

## Authentication

Describe the required credentials or entitlements. Do not include secrets.

## Provenance And Rights

- Native, inverted, or configured-fallback IV:
- Data retention and redistribution rights:
- Required redaction:
- Known coverage, timing, or reconnect limitations:

## Payload Examples

If possible, include sanitized sample payloads with account IDs, tokens, and
private fields removed.

Do not attach licensed raw market data unless its redistribution rights are
explicit. A sanitized mapping note is usually sufficient.

## Notes

Link to official API docs or provider documentation.

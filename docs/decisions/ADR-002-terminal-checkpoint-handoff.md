# ADR-002 — Immutable Terminal Checkpoint Handoff

Date: 2026-10-18. Status: accepted for GEX-WIND-HANDOFF-001.

## Decision

Freeze a bounded, allowlisted copy of Terminal's demo/replay state under the
consumer lock. Bind copied rows, spot, event cutoff, source quality and effective
assumptions in a versioned checksummed artifact. Wind Tunnel calculates only
from that detached copy. Embed the artifact in saved scenario requests so a
fresh process can reproduce the result without an external source registry.

Terminal's explicit handoff action owns a loopback Wind Tunnel service and its
cleanup. The standalone CLI can instead read an explicitly supplied checkpoint
file. The browser selects a server-supplied source identifier; it cannot ask the
server to open filesystem paths. Existing capability, origin, request and
storage bounds remain in force. No continuous feed is attached.

Terminal's default row selection can use OI where a contract has no positive
trade volume. A named `terminal_selected` model preserves that exact choice;
the existing raw-volume, OI and directionalized models remain separate.
The checkpoint preserves the current expiry filter and cannot expand to rows
outside it. Unsupported states fail with a visible explanation.

## Alternatives And Consequences

Sharing the mutable consumer across interfaces risks baseline drift and changes
state ownership. Replaying a path inside the browser introduces filesystem
authority and may consume events beyond the intended cutoff. A server-only
registry makes portable reproduction depend on the original machine. Detached
embedded state avoids these dependencies at the cost of bounded receipt size.

Checksums establish internal identity, not authenticity, licensing or market
truth. Checkpoints and receipts contain market data: users must preserve the
source's retention/sharing rights. Initial capture supports demo/replay only;
live capture needs its separate governed authority. The new format does not
promote existing provider readiness or predictive claims. Original receipts
continue to require their matching reviewed calculation build.

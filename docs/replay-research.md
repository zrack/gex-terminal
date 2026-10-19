# Replay Research Mode

Replay mode lets contributors exercise normalized market events, GEX models,
terminal states, and reports without live market data or provider credentials.
This page is the routing overview; each detailed workflow has one canonical
guide.

## Start A Replay

List or run packaged sessions:

```bash
gex-terminal list-replays
gex-terminal --replay-session zero-gamma-flip
```

Start `gex-terminal --demo` and press `p` to browse the same catalog inside the
terminal. Use Up/Down to select, Enter to load, and Escape to close. Replay
switching is disabled in live mode and during active session capture so provider
tasks or two event streams cannot be mixed into one state history.

Use `x`, `d`, `m`, and `i` to change expiry selection, fallback DTE, contract
multiplier, and risk-free rate. Those controls recompute the current offline
snapshot through the same consumer and engine path.

## Bundled Sessions

| Session | Intended scenario |
| --- | --- |
| `demo` | Compact first-run and screenshot fixture |
| `full-session` | Synthetic ES 0DTE open, mid-session, and late-session path |
| `trend-day` | Rising spot with call-side accumulation |
| `chop-day` | Range-bound balanced call/put activity |
| `volatility-spike` | Downside move with higher IV and put-heavy activity |
| `gap-fade` | Gap-up rejection and rotation toward lower levels |
| `call-wall-breakout` | Upside path that moves the modeled call wall higher |
| `zero-gamma-flip` | Position-proxy rotation across the compatibility level |
| `expiration-compression` | Late 0DTE concentration around the modeled wall |
| `quality-stress` | Off-symbol drops and partial-chain feed-health states |

These sessions are synthetic software fixtures. Their labels describe intended
test behavior, not observed market regimes or predictive results.

## Choose The Right Workflow

| Goal | Canonical guide |
| --- | --- |
| Compare bundled final snapshots and replay alerts | [Replay Lab](replay-lab.md) |
| Create screenshots and a shareable artifact pack | [Demo Lab](demo-lab.md) |
| Save narrative study entries and compare them | [Research Journal](research-journal.md) |
| Store or report computed final snapshots | [Historical Session Store](historical-sessions.md) |
| Record, verify, and replay normalized events | [Captured Sessions](captured-sessions.md) |
| Inject provider-shaped input before normalization | [Provider Injection](provider-injection.md) |
| Validate time, adversarial cases, later prices, or position models | [Offline Validation](offline-validation.md) |
| Run sensitivity or numerical evidence | [Model Validation](model-validation.md) and [Model Assumptions](model-assumptions.md) |
| Register a corpus or reproduce a versioned experiment | [Research Governance](research-governance.md) |
| Inspect output schemas | [Export Formats](exports.md) |

## Fixture Choice

Use a normalized replay when testing the consumer, model, TUI, or report path
directly. Use provider injection when testing raw/provider-shaped parsing and
mapping. Use a captured session when event order, event-time pacing, integrity,
or a complete local stream matters. Use the session store only when the final
computed snapshot is sufficient.

Packaged `--replay-session` and `bundled:NAME` identities work from a source
checkout or installed wheel. A filesystem path is appropriate for a local
fixture under development and should not be committed when it contains private,
licensed, or unsanitized data.

## Evidence Boundary

Replay proves only the behavior exercised by its declared input and software
version. Synthetic sessions cannot certify live authentication, entitlements,
current contract coverage, latency, reconnects, dealer inventory, or predictive
validity. An integrity-checked capture detects internal corruption but is not an
authenticity signature or a governed historical corpus by itself.

# GEX-PREFLIGHT-001 — Offline Doctor And Privacy-Safe Preflight

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
adoption_context: team
change_rigor: L3
status: Ready for integration — contributor evidence passed
packet_owner: project maintainer
spec_steward: implementation agent
architecture_authority: project maintainer
evidence_reviewer: pull-request reviewer and hosted CI
baseline: codex/gex-health-002-config-truth@79a0a714de719ac7de3e015a36c3b80a670925d3
branch: codex/gex-preflight-001
created: 2026-09-04
external_outcome: "Not applicable — offline support diagnostics only"
```

## Authorization And Routing

The maintainer authorized a versioned, offline `doctor` command and reusable
report API after accepting the immutable GEX-HEALTH-002 contributor commit.
The command may inspect local runtime and package shape, but it may not open a
network connection, construct a live adapter, import an optional provider SDK,
read provider credential values, retain a storage probe, or claim provider
authentication, entitlement, capacity, or live readiness.

This is routed as `L3`: the bounded CLI workflow would otherwise qualify as
`L2`, but its durable support artifact, explicit privacy contract, and
automation-facing exit meanings make leakage and false-readiness failures
hard triggers. Work remains isolated for later reviewed integration. No push,
merge, tag, release, credentialed run, or publication is authorized here.

## Problem And Intended Outcome

Users currently discover broken Python/package setup, missing optional SDKs,
invalid configuration, absent bundled files, or unwritable temporary storage
only after selecting another workflow. Support also lacks a stable diagnostic
artifact that can be attached without leaking paths or account configuration.

After this change, `gex-terminal doctor` prints a concise offline preflight and
`gex-terminal doctor --json` prints the versioned equivalent. The report
distinguishes required failures from unselected optional-SDK warnings, reports
selected-provider structural runnability without starting it, and keeps live
authentication and entitlements explicitly unverified. Invalid `GexConfig`
input becomes a diagnostic result rather than a traceback or global
configuration crash.

## Scope

- Python, package metadata, required base-module, and bundled-resource checks.
- Configuration construction and shape reporting with field names and type
  names only; values and paths are omitted.
- Effective selected path, canonical readiness, structural provider
  runnability, and optional-SDK presence using metadata/spec lookup only.
- Explicit unverified authentication, entitlement, live transport, and
  provider-capacity status.
- A self-owned temporary write/read/delete probe with cleanup verification.
- macOS hidden editable `.pth` detection when filesystem flags are available,
  reported as a count and fixed recovery guidance without a raw path.
- Versioned JSON, human-readable text, stable exit semantics, reusable report
  functions, tests, and one canonical operator guide.

## Non-Goals

- Network, DNS, socket, HTTP, WebSocket, broker, or market-data requests.
- Live-adapter construction, validation, SDK import, login, subscription, or
  entitlement inspection.
- Credential presence reports, credential values, account identifiers,
  provider payloads, configured symbols, configured paths, hostnames, client
  IDs, current working directory, Python executable path, or site-package paths.
- Persistent support bundles, telemetry, uploads, automatic repair, package
  installation, environment mutation, or readiness promotion.
- Replacing command-specific validation, release certification, live
  certification, or predictive/outcome evidence.

## Invariants

This packet adopts `INV-01` through `INV-08` and `INV-21` through `INV-25` from
the active repository lineage and adds:

- `INV-31` — Doctor execution performs zero network operations and never
  constructs a market-data adapter or imports an optional provider SDK.
- `INV-32` — Public text and JSON contain no secret value, account setting, or
  absolute/user-derived path; configuration disclosure is names and types only.
- `INV-33` — Authentication, entitlements, provider capacity, and live
  transport remain `unverified` regardless of local package state.
- `INV-34` — Only the doctor's own temporary probe may be written, it is read
  back and removed, and no persistent application state is created.
- `INV-35` — A missing unselected optional SDK is a warning; an invalid config,
  broken required base/resource/storage check, unknown/scaffold selected live
  provider, missing selected SDK, or unreadable selected replay is blocking.
- `INV-36` — JSON schema and exit meanings are stable: `0` is locally usable
  with any warnings/unverified ceilings, `1` is a required runtime/package/
  resource/storage failure, and `2` is invalid configuration or a structurally
  non-runnable selected path.

## Requirements And Acceptance

| ID | Requirement / Acceptance Criterion | Evidence | Status |
| --- | --- | --- | --- |
| `REQ-01` | A reusable API returns a JSON-serializable `gex-terminal.doctor.v1` report with safe checks and summary. | API/schema tests | Verified |
| `AC-01` | Text and `--json` describe the same result and the process returns the report's documented exit code. | Public CLI subprocess tests | Verified |
| `REQ-02` | Python support, package/distribution metadata, required modules, and all declared bundled resources are checked without importing provider SDKs. | Injected probe and package tests | Verified |
| `REQ-03` | Valid configuration exposes field names/types only; `ConfigValidationError` becomes a safe blocking diagnostic. | Config/redaction tests | Verified |
| `REQ-04` | Demo/replay/live selection, readiness, selected SDK/scaffold/replay runnability, and unverified auth/entitlement ceilings are explicit. | Provider matrix tests | Verified |
| `AC-02` | Missing selected SDK or scaffold/unknown selected provider exits `2`; absent unselected extras only warn and keep exit `0`. | SDK/provider tests | Verified |
| `REQ-05` | Storage probe creates only a private temporary artifact, verifies round-trip/delete, cleans it, and reports no path. | Success/read-only/cleanup tests | Verified |
| `REQ-06` | Hidden editable `.pth` state is a warning with fixed recovery guidance and count only when detectable. | Filesystem-flag tests | Verified |
| `AC-03` | Secret-shaped config errors, raw paths, credential/account environment values, and probe exception text never appear in text or JSON. | Adversarial disclosure tests | Verified |
| `AC-04` | Socket/network sentinels, adapter-construction sentinels, and optional-module import sentinels remain untouched. | No-network/no-import tests | Verified |
| `AC-05` | Focused/full tests, source compilation, patch hygiene, build/Twine, and installed-wheel outside-checkout doctor smoke pass. | Contributor branch evidence | Verified |

## Architecture Delta

```text
CLI doctor / future support bundle
              |
              v
      build_doctor_report
       |      |       |
       |      |       +--> owned temporary round-trip, then removal
       |      +----------> import specs / package metadata / resource IDs
       +-----------------> GexConfig shape + static provider/readiness policy
              |
              v
   versioned safe report --> text or JSON --> exit 0 / 1 / 2

No edge reaches: adapter constructors, optional SDK imports, credentials,
accounts, live transport, or the network.
```

The report builder is the single diagnostic authority. Renderers consume that
report without re-probing, so later support-bundle work can reuse identical
safe summaries and evidence ceilings.

## Bounded Slices

| Slice | Deliverable | Evidence | Fallback / Stop Point |
| --- | --- | --- | --- |
| `S1` Route | Accepted packet, baseline, invariants, exit contract | Structural review | Stop before code if privacy scope changes |
| `S2` Report core | Probe/result model, safe aggregation, renderers | Unit/schema/redaction tests | Emit fixed summaries, never raw exceptions |
| `S3` Runtime/package | Python, metadata, modules, resources, hidden `.pth` | Injected and real-environment tests | Fail required checks; warn on visibility/extras |
| `S4` Config/provider | Safe config shape and structural selected-path checks | Provider/config matrix | Never validate credentials or instantiate adapters |
| `S5` Storage/CLI | Removed temp probe, CLI/JSON/exit wiring | Filesystem and subprocess tests | Fail closed and leave no artifact |
| `S6` Reconcile/verify | Canonical guide, package parity, contributor commit | Full and installed-wheel gates | Do not integrate on a failed critical gate |

## Risks And Controls

| ID | Risk | Control / Recovery |
| --- | --- | --- |
| `RISK-01` | A diagnostic leaks a path or secret through an exception. | Fixed result vocabulary; never serialize probe exceptions or environment values; adversarial tests. |
| `RISK-02` | SDK detection imports code with network or side effects. | `importlib.util.find_spec` and distribution metadata only; import sentinels in tests. |
| `RISK-03` | A local pass is mistaken for live readiness. | Unconditional unverified access/live ceilings and separate canonical readiness. |
| `RISK-04` | The storage check leaves data or tests a user directory. | Self-owned temporary context, fixed harmless payload, explicit cleanup verification. |
| `RISK-05` | Missing unselected extras make the base app look broken. | Warning classification unless the missing SDK is required by selected live mode. |
| `RISK-06` | Report and CLI status drift. | One report object drives both renderers and process exit. |

## Verification And Integration Plan

1. Run focused doctor API, privacy, resource, provider, storage, and public CLI
   tests, including injected failures and network/import sentinels.
2. Run source compilation, full unit discovery, and `git diff --check`.
3. Build source and wheel distributions, run Twine validation, install the
   wheel outside the checkout, and run text/JSON doctor commands with a clean
   environment and explicit installed-package import proof.
4. Commit explicit packet, implementation, tests, and canonical guide paths on
   this contributor branch. Do not push, merge, tag, call a provider, or write
   a support bundle in this slice.

Rollback is a Git revert of the contributor commit. The doctor creates no
persistent state and mutates no environment, credential, package, or provider.

## Amendments

None.

## Evidence

- Focused doctor, public CLI, configuration, safety, resource, and release
  contract suite: 52 tests passed.
- Full unit discovery: 335 tests passed. Source compilation and
  `git diff --check` passed.
- Manifest tests reconciled all 29 bundled resources and both required and
  optional dependency groups with the package declaration.
- Adversarial tests verified fixed output for secret-shaped configuration and
  logging errors, credentials, account identifiers, private replay paths,
  filesystem-probe exceptions, and hostile argument values.
- Network/socket, adapter-construction, and optional-SDK import sentinels were
  not touched. No provider call or credentialed run was made.
- A real storage round trip verified write/read/delete and context cleanup.
  A real environment probe detected one hidden project editable `.pth` while
  reporting only its count and bounded recovery guidance, never its path.
- Current source and wheel distributions built successfully and passed Twine
  validation. An isolated `--no-deps --target` wheel install was imported from
  the target directory outside the checkout. Text and JSON doctor paths
  returned `0`; invalid configuration, logging, provider, and replay cases
  returned `2` without raw values or tracebacks; `python -S` returned `1` with
  a required-module diagnostic and no import-time crash.

A successful doctor proves only the reported local preflight facts; it cannot
prove provider access, market-data quality, live reliability, or predictive
validity.

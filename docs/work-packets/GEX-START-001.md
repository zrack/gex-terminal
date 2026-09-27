# GEX-START-001 — Unified Offline Starter

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: active
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent contributor review
baseline: main@1332d90206762381a80115ca77683a65510f96d0
branch: codex/unified-starter
application_version: 0.6.0
created: 2026-09-27
```

## Authority And Scope

The maintainer requested one starter offering **Terminal**, **Wind Tunnel** or
**Both**, and an explanation of where that improvement fits the roadmap.
This packet covers setup-helper and launcher behavior, its focused tests and
its installation documentation. Existing authority for the reviewed contributor
workflow applies; integration still requires independent review, successful
final-head hosted checks and clean merged-tree verification.

Installation lifecycle changes receive L3 rigor, following
[GEX-UX-002](GEX-UX-002.md). The application wheel, version `0.6.0`, and immutable
`v0.6.0` tag remain unchanged. This enhancement is identified by the installer
source and new setup-bundle inventory, not by a new application release tag.
Retain the original 0.6.0 setup and the frozen September 20 study as separate,
unchanged artifacts.

The bounded outcome is a clear choice between the two existing interfaces.
Both starts an offline terminal and a local Wind Tunnel in one managed launch
session. Exiting the terminal stops the Wind Tunnel process owned by that
session. Independent shortcuts remain available. A terminal-only installed
wheel remains usable without claiming that Wind Tunnel is present.

This does not synchronize selected sessions, checkpoints, model assumptions,
receipts or in-memory state between the interfaces. It adds no market-data
connection, provider certification, participant observation, telemetry,
research migration, system-wide installation or package publication. Preserve
INV-01 through INV-08; predictive validity remains `unmeasured`.

## Design And Compatibility

Fresh setup folders provide the unified entry point and explicit interface
shortcuts. Existing installed shortcuts retain their verified bytes on an
in-place update. The ordinary terminal command remains a direct terminal path;
advanced CLI configuration stays separate from the isolated offline starter.

The combined launch owns only the Wind Tunnel child it creates. Cleanup must
run on normal terminal exit and interrupted or failed startup, without stopping
another separately started server. The combined session uses explicit synthetic
inputs, a separate research directory and a free loopback port. No shared state
or common market moment is inferred from launching both interfaces.

For a fresh Wind Tunnel-capable installation, `Start GEX.command` presents
`1 Terminal`, `2 Wind Tunnel`, `3 Both` and `q Cancel`, with no empty-response
default. `run-gex` keeps its direct terminal behavior; `Start Terminal.command`
adds the explicit macOS terminal shortcut. The existing `Start Wind
Tunnel.command` and `run-wind-tunnel` remain direct browser paths. Linux uses
`run-gex --choose` or `run-gex --both`; Wind Tunnel/Both automation can use
`--no-browser`. Interactive setup offers the validated starter. Existing three-
or five-file launcher sets retain their bytes; only fresh installs receive the
new shortcuts. [First Run](../first-run.md) owns the user-facing instructions. [Wind Tunnel](../wind-tunnel.md) owns the browser
workflow; [Architecture](../architecture.md) owns current process and state
boundaries. The roadmap keeps its existing evidence gates. Deeper context
transfer would require a separately authorized scope and is not implied here.

## Acceptance

1. A fresh reviewed installation offers Terminal, Wind Tunnel and Both when
   the installed application supports Wind Tunnel. Terminal-only wheels have a
   clear usable fallback. Existing direct terminal and Wind Tunnel shortcuts
   continue to work.
2. Tests exercise choice routing, invalid or cancelled input, noninteractive
   behavior, missing Wind Tunnel support, paths containing spaces and explicit
   shortcut arguments. No choice can silently select a live provider.
3. The combined path opens the local browser workbench and terminal, cleans up
   only its owned child on exit, and reports startup failures. Test child
   settlement, interruption and preservation of independently running servers.
4. Fresh installation and repeat verification preserve the selected wheel,
   separate research and installed-launcher identity. An in-place update leaves
   older shortcut bytes unchanged. No prior setup or frozen study is overwritten.
5. Compile, focused installer/bundle tests, documentation links, the complete
   source suite and independent review pass. Rehearse a fresh setup using the
   retained 0.6.0 wheel outside the checkout and record the exact installer,
   wheel, runtime, bundle and research identities.
6. Record final-head hosted results and clean merged-main verification before
   closing technical shipment. Local tests establish launcher behavior only;
   observed first-use acceptance remains an external gate.

## Verification Record

Pending implementation and verification. Expected focused coverage belongs in
`tests/test_install_app.py` and `tests/test_app_bundle.py`; documentation links
are checked by `tests.test_release_contract.DocumentationLinkContractTests`.
Do not treat this packet's acceptance list as completed evidence.

The maintainer will retain local rehearsal and bundle manifests outside Git,
then add the verified source, tests, integration outcome and handoff location to
this record before closeout. No new package version or tag is planned.

## Recovery

Use the retained standalone terminal or Wind Tunnel shortcut, or the previous
reviewed setup folder. Revert the bounded installer change if needed. Research
remains separate from the application environment; cleanup stops an owned
process and never deletes research. The original 0.6.0 wheel/tag and frozen
study continue to identify their original builds.

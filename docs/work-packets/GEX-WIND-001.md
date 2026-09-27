# GEX-WIND-001 — Market Wind Tunnel

```yaml
method: saed
method_version: "1.3"
profile: gex-terminal-team-v1
change_rigor: L3
status: closed
packet_owner: project maintainer
spec_steward: implementation agent
evidence_reviewer: independent contributor review
baseline: main@0ec8de85989584a2cc5c1b6b8333673e3acf954c
branch: codex/market-wind-tunnel
release: 0.6.0
created: 2026-09-26
```

## Authority And Scope

The maintainer explicitly requested the full Market Wind Tunnel, tests,
completed examples, a clean pull and a repository tag. The preceding authority
for commits, a pull request and merge to `origin/main` remains applicable.
The clean main checkout was pulled before creating this feature branch.
Release follows independent review, final-head hosted checks, merge, clean
merged-tree verification and an annotated `v0.6.0` tag. No package-registry or
hosted-release publication is requested.

This is the explicit owner-directed exception to the roadmap's previous
feature hold. It does not close the customer, observed-first-use or live-data
gates. Preserve INV-01 through INV-08 and the frozen September 20 study.

Deliver a packaged offline browser workbench with the existing Python model:
an exposure landscape, matched scenario comparison and sampled fragility map;
replay checkpoints; spot, absolute IV, clock and expiry changes; separated
position models; bounded break search; inspectable contract contributions;
saved, exported and reproducible experiment receipts; three worked examples;
and straightforward launch instructions. All initial sources are explicitly
synthetic bundled sessions. Live feeds, real participant observations, hosted
accounts, trading, telemetry and predictive claims are outside this release.

## Architecture And Compatibility

The existing consumer owns reconstructed market state. Wind Tunnel calculations
fork a declared checkpoint and reuse production pricing without mutating the
baseline. The new aiohttp service binds only IPv4 loopback and serves bundled
HTML, scripts, styles, fonts supplied by the system, and vendored chart assets.
The browser requires no build tool, external CDN or account. Capability and
origin checks protect local API requests. Research writes are confined to an
owned workspace and bounded, versioned receipts.

Fresh setup bundles add a Wind Tunnel shortcut. Previously installed launcher
bytes and separate research remain intact on an in-place update; the documented
handoff uses a fresh folder to obtain new shortcuts. Existing Demo Lab and
experiment contracts explicitly admit the new reader version only after
cross-version checks. No existing research is migrated or deleted.

## Acceptance And Release Gates

1. Independent numerical tests cover unchanged-scenario identity, production
   engine parity, point-in-time replay, absolute-IV semantics, model separation,
   expiry removal, finite input limits and deterministic bounded searches.
2. Real HTTP and persistence tests cover capability/origin/host checks, invalid
   input, resource limits, immutable save/export/reproduction, corrupt receipts,
   unsafe paths and server lifecycle.
3. Browser review exercises all three views, scenario edits, examples, save and
   reload, boundary search, keyboard access, responsive layout and fallback.
   Record actual screenshots and remaining limitations in `design-qa.md`.
4. Source regression, model/provider/property/performance gates, compilation,
   documentation links, build/Twine and installed-wheel checks pass. Hosted
   Ubuntu/macOS and Python 3.11/3.12 jobs must pass for the final PR head.
5. Generate and reproduce discovered-break, no-break and expiry-exclusion
   examples from the installed package. Verify old research compatibility and
   fresh installation without overwriting the frozen study or prior setup.
6. Tag only the checked merged commit. Record source identity, test evidence,
   local handoff paths and recovery instructions before reporting completion.

## Evidence

The integrated local source passes 512 tests, compilation and whitespace checks.
Wheel and source distributions pass build/Twine. The installed wheel passes the
numerical gate, offline Databento certification, seven model properties, seven
provider fault cases and the declared 100-contract performance budget. Actual
0.5.0 Demo Lab and experiment artifacts reproduce through the 0.6.0 installed
reader without changing their source bytes. The committed candidate at
`c6545c53268a37035167af2fba695f8cfd8bee96` passes a fresh offline installation
and repeat reuse with 21 supplied dependency wheels. All 117 installed
application files match the committed source and wheel. Both launcher chains,
doctor, terminal export and all three example/verify/reproduce cycles pass from
outside the checkout. The installed browser loads its packaged charts and
examples. The candidate wheel SHA-256 is
`f97af37248baca21bfac400d018c00d51bba6cd28cf752e3bc2ce7e24b4576cc`.

Independent review found and resolved cooperative cancellation, stale-save
ownership, exact surface/grid reopening, an unlisted installer-launcher hazard,
and signed JSON reserialization across Python/JavaScript. Their regression tests
exercise the failure mechanisms. Browser QA found and repaired narrow-screen
metric overflow and excessive desktop spacing. See [design QA](../../design-qa.md)
for actual rendered evidence and reviewed limitations.

The three executable examples demonstrate a 35-point discovered-break search,
a nine-point no-break neighborhood and front-expiry exclusion leaving six later
contracts. Browser save/reopen/import and CLI verification reproduce the exact
calculation. Local evidence is under `dist/wind-tunnel-development/`.

A chart or synthetic example establishes software behavior only. Search results
identify a nearest tested point under declared bounds and resolution, never a
global mathematical minimum or a market forecast. Predictive validity remains
`unmeasured`.

## Integration And Recovery

[PR #32](https://github.com/zrack/gex-terminal/pull/32) owns the final checked
source and merge identities. This packet closes technical implementation with
that authorized merge, conditional on all final-head Ubuntu/macOS and Python
3.11/3.12 hosted jobs passing. Documentation closeout changes must pass the same
matrix. Clean merged-main regression, remote equality, final build/install
identity and the annotated `v0.6.0` tag are recorded in the local release record
`dist/wind-tunnel-development/merged-closeout.json` after those gates complete.
The tag points to the checked merge; it is the durable release bookmark.

The final handoff is a fresh `dist/GEX Wind Tunnel 0.6.0 Setup/` folder with a
reviewed wheel and dependencies for macOS ARM64 / Python 3.12. Completed example
receipts and reproduction reports are retained separately from its owned research
workspace. The existing setup folder and frozen September 20 study remain intact.
The candidate rehearsal record is
`dist/wind-tunnel-development/committed-rehearsal/candidate-handoff.json`.

Recover by reinstalling a previously reviewed wheel into its owned application
folder, or use a fresh setup folder; retain the separate research directory.
No research migration is performed. Exact Wind Tunnel reproduction requires the
recorded application/source/runtime identities, so preserve its matching wheel
and receipts together. Package publication, real-user acceptance and live-data
certification remain outside this release.

# Offline Doctor

`gex-terminal doctor` is a local preflight for installation and configuration
problems. It does not contact a provider, open a socket, construct a live
adapter, import an optional provider SDK, or test credentials and entitlements.

Run the readable report:

```bash
gex-terminal doctor
```

For automation or a support attachment, print the versioned JSON report:

```bash
gex-terminal doctor --json
```

If the normal console command cannot import because a required dependency is
broken, use the lightweight module entry point:

```bash
python -m gex_terminal.doctor --json
```

Both formats are rendered from the same report and return its exit code.

For a reviewed setup bundle, use `"./GEX App/run-gex" --doctor` from its setup
folder. That checks the installed environment under the starter's offline
configuration. The direct CLI above reads the normal application configuration.
See [First Run](first-run.md#local-setup-options) for installation diagnostics.

## What It Checks

- the supported Python version and installed package-version agreement
- required runtime-module discoverability
- every declared bundled stylesheet, replay, and provider/research fixture
- validated runtime/logging configuration shape, reporting field names and type
  names only
- the effective demo, replay, or live provider path and canonical readiness
- optional provider-SDK presence through import metadata, without importing it
- selected replay readability without reading or reporting its contents
- a write/read/delete round-trip in the doctor's own temporary directory
- on platforms that expose the flag, hidden editable `.pth` files that Python
  can skip

Missing unselected provider extras are warnings: the base demo/replay product
does not require every provider SDK. A missing selected SDK, scaffold selected
for live mode, incompatible provider/instrument shape, or unreadable selected
replay is blocking.

The hidden editable-install warning reports only a count. Clear the hidden flag
only on the `gex-terminal` editable `.pth` file, then rerun the doctor. If the
flag returns, prefer the reviewed wheel in a dedicated virtual environment;
reinstalling editable metadata is not a durable repair for the observed
filesystem behavior. The report never prints the file's location, and it does
not recommend clearing flags broadly.

Doctor is not a capture or scenario validator. It does not verify the full
saved-data registry, replay a full trading day, reproduce Wind Tunnel receipts
or measure accepted-IV ages. A successful preflight can coexist with degraded
saved source health, partial pricing coverage or old IV observations. Use the
starter's source verification, [Wind Tunnel](wind-tunnel.md) diagnostics and
[offline validation](offline-validation.md#saved-esnq-product-regressions) for
those separate questions. Offloaded files in cloud-synchronized folders must
also be locally readable before a disconnected saved-data launch.

## Exit Codes

| Code | Meaning |
| ---: | --- |
| `0` | The selected local path is structurally usable. Warnings and explicit unverified live-access ceilings may remain. |
| `1` | A required runtime, package, bundled-resource, or temporary-storage check failed. |
| `2` | Configuration is invalid or the selected provider/replay path is structurally non-runnable. |

If multiple blocking classes occur, required runtime/package/storage failure
(`1`) takes precedence because later configuration conclusions may depend on a
sound base environment.

## JSON Contract

The schema identifier is `gex-terminal.doctor.v1`. Top-level fields are:

- `schema` and `generated_at`: contract identity and UTC generation time
- `application`: stable package name and version
- `execution`: explicit booleans for network, adapter, SDK-import, persistence,
  and sensitive-value behavior
- `checks`: ordered fixed-ID results with `pass`, `warning`, `fail`, or
  `unverified` status
- `summary`: overall status, exit code, and status counts
- `evidence_ceiling`: what the offline result does not establish

Configuration details contain field names and Python type names, never values.
The report omits the Python executable, current directory, replay path,
site-package paths, provider host/account settings, credentials, tokens, and
raw probe exceptions. Bundled package-relative resource identifiers are safe
and may be listed when a resource is missing.

Support tooling can reuse `gex_terminal.doctor.build_doctor_report` and either
renderer. It should preserve the returned report rather than reconstructing
checks from local environment values.

## Evidence Ceiling

A successful doctor is local structural evidence only. Authentication,
entitlements, provider capacity, live transport, current market-data quality,
and predictive validity always remain `unverified`. Use the separate governed
certification workflows for any stronger claim.

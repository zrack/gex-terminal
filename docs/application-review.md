# Application State And Health Review

Reviewed September 4, 2026 against source commit `8330319` and package version
`0.4.0`. This document owns the latest dated review findings and verification
record. [Architecture](architecture.md) owns current structure;
[Roadmap](../ROADMAP.md) owns work order and acceptance gates. Refresh this
review in place; Git preserves earlier assessments.

## Assessment

The application is a substantial offline research alpha. Its numerical,
provider-fixture, replay, packaging, and report checks pass, and a fresh wheel
installation works outside the checkout. Five correctness findings need repair
before expanding the affected workflows: instrument metadata, health reporting,
replay isolation, experiment metadata verification, and replay event chronology.
The instrument-identity repair is now implemented under `GEX-HEALTH-001`;
the remaining findings retain their open status below.
Small-terminal usability also needs attention. Passing the current tests does
not cover these cases.

No credentialed provider observation, real-user study, or commercial pilot was
performed in this review. Databento remains `live-uncertified`; predictive
validity remains `unmeasured`.

## Current State

| Area | Observed state | Practical meaning |
| --- | --- | --- |
| Research engine | Contract-aware Black-76/Black-Scholes and separate OI, raw-volume, and directionalized-volume paths exist; numerical/property checks pass | A working calculation and comparison foundation, with open workflow defects below |
| Offline experience | Ten bundled replay scenarios, provider fixture lab, snapshots, overlays, journals, session stores, experiments, corpus tools, and a 12-artifact Demo Lab | Extend these tools into one usable loop; a new evidence-pack subsystem is unnecessary |
| Terminal | Demo/replay renders, keyboard replay controls and model controls are covered by tests; smaller layouts lose key content | Usable large-terminal research surface; first-use and responsive-layout work remains |
| Distribution | Source and wheel build; fresh Python 3.12 wheel install and offline commands pass | Packaging exists; a supported installer/update channel and observed non-developer activation remain future work |
| Local checkout | Source-module invocation works; the existing `.venv/bin/gex-terminal` launcher raises `ModuleNotFoundError` | A local environment fault, distinguished from the successful fresh wheel installation |
| Live inputs | Databento implemented but uncertified; Tradovate and IBKR scaffolded; yfinance delayed; demo/replay offline-certified | No supported recurring live ES/NQ operating envelope is established |
| Commercial readiness | No customer/retention/payment evidence is supplied by the repository checks | Phase 0 discovery and the later beta gates remain necessary |

At review time, GitHub also has open provider-fixture issues #4/#5 and
[PR #10](https://github.com/zrack/gex-terminal/pull/10) for Tradovate payload
validation. The PR returned no check results in this inspection; its code has
not been accepted as part of this review. Reconcile that queue with current
source before assigning duplicate adapter work.

## Findings And Repair Status

P1 means a correctness repair should precede new work that depends on the
affected result. P2 means a material usability or maintainability issue. These
findings are open unless explicitly marked resolved with regression evidence.

### H1 — Resolved: Instrument identity and multiplier provenance

Repair: seeded non-ES demos fail before creating an artifact; bundled replays
resolve their instrument through one catalog contract. Snapshot v2 now labels
its compatibility multiplier as configured fallback and records the effective
multiplier(s), selected contract identities, and fallback use. Consumer,
snapshot, injection, and public replay-identity tests cover ES/NQ selection,
SPY ×100 and heterogeneous rows. The following describes the original defect;
it is not current behavior. See [GEX-HEALTH-001](work-packets/GEX-HEALTH-001.md).

`GEX_SYMBOL=NQ gex-terminal --demo --export nq-demo.json` exits successfully
with `symbol=NQ`, `spot=5943.25`, and `contract_multiplier=50`. The same fixed
ES demonstration prices and strikes are used regardless of the requested
symbol. The exported model is also explicitly `legacy_v1`/`black_scholes`, so
this does not exercise the contract-aware native NQ path.

The symbol and default multiplier are independently configured in
[`config.py`](../gex_terminal/config.py); the unconditional seed is in
[`seed_demo_session`](../gex_terminal/cli.py). Selecting a symbol must not relabel
another instrument's sample data. A synthetic fixture is still required to have
truthful identity.

Repair acceptance: reject unsupported demo symbols or provide symbol-specific
synthetic inputs and correct defaults. Exercise the public CLI, exports, and
screenshots for ES and NQ. Keep a dedicated schema-v2 NQ scenario distinct from
this legacy demo. Do not infer live NQ support from that fixture.

There is a separate schema-v2 metadata case in the same instrument-profile
boundary: `inject-provider bundled:yfinance-etf-options --export spy.json`
prices SPY contract rows with their multiplier 100 but exports the fallback
`contract_multiplier=50`. The row pricing is distinct from the incorrect
top-level description. See [`provider_injector.py`](../gex_terminal/provider_injector.py)
and [`yfinance_adapter.py`](../gex_terminal/adapters/yfinance_adapter.py).
Repair acceptance also requires exports to distinguish fallback assumptions
from the actual row multipliers, including mixed-contract cases.

### H2 — P1: Health output can misrepresent offline or stale inputs

The normal offline command
`inject-provider bundled:yfinance-etf-options --export spy.json` emits
`status=LIVE`, `data_mode=LIVE`, `connection_state=CONNECTED`, and
`health=healthy`. [`provider_injector.py`](../gex_terminal/provider_injector.py)
creates a live-mode consumer and marks it connected to exercise mapping, then
exports that simulated state without a distinct offline runtime label. No
network connection was opened; the artifact also contains fixture provenance.
Users should not have to resolve these contradictory status fields.

Repair acceptance: retain a visible offline/simulated origin in injection
artifacts and CLI summaries, and keep mapping quality separate from observed
live connection or provider readiness. Test the complete public export.

The second failure is stale detection under invalid configuration:

[`_env_float`](../gex_terminal/config.py) accepts `nan` and `inf`;
[`runtime_status`](../gex_terminal/consumer.py) uses the resulting stale limit
without a finite/domain check. With `GEX_STALE_AFTER_SECONDS=nan`, a simulated
connected live consumer whose last message is one day old reports `LIVE` and
`health=healthy`. This was reproduced offline through the installed wheel.

The integer/float parsers also silently replace malformed numeric strings with
defaults. Invalid input can therefore produce plausible behavior instead of a
clear configuration error.

Repair acceptance: validate finite values and allowed ranges before runtime or
export starts, including direct construction and CLI overrides where applicable.
Reject invalid timing, rate, multiplier, and expiry values with an actionable
error. A stale source must never become healthy because of an invalid setting.
Keep intentionally optional values distinct from malformed ones.

### H3 — P1: Switching replay can leave the previous stream writing state

The interactive CLI starts an adapter task in
[`cli.py`](../gex_terminal/cli.py), while the TUI's
[`_load_replay_session`](../gex_terminal/tui.py) resets the consumer and loads a
new replay without settling that task. Replay switching is enabled whenever
capture is inactive, including while the original replay is still streaming.

An offline reproduction starts a three-record slow ES replay whose final
record has a unique strike, switches to `zero-gamma-flip` after two records,
then lets the old task finish. The selected replay stays
`es_zero_gamma_flip.jsonl`, but the consumer message count rises from 13 to 14
and the old-only strike `9999` appears in its chain.

Repair acceptance: give replay lifecycle one owner. Cancel and await the old
writer before reset/replacement, or explicitly block switching while it owns
the consumer. A public interactive-path regression must prove that no prior
session record arrives after the new session is selected, including delayed
and event-clock replay. Existing idle-consumer switch tests are insufficient.

### H4 — P1: Reproduction accepts inconsistent experiment metadata

[`reproduce_experiment`](../gex_terminal/experiment_manifest.py) verifies the
input digest and resulting report digest, but does not compare the embedded
model profile against the recorded `profile_sha256` or bind the complete
experiment specification to an expected identity.

The minimal confirmed probe changes its embedded `profile_id` and changes
`split` from `test` to `train`, leaving the original profile hash unchanged.
Reproduction still reports `matched=true` and writes a different profile hash
alongside the same report digest. Metadata that does not
change the calculation can therefore be silently relabeled as a successful
reproduction. A matching report alone cannot establish an unchanged experiment.

Repair acceptance: verify recorded profile and full specification identities
before execution. Define which metadata is informational versus bound to the
experiment, and reject inconsistent records or require a new experiment
identity. Test profile, split, outcome, cost, and implementation compatibility
independently from input/result parity. These checks establish internal
consistency; authenticity still requires separate signed or anchored evidence.

### H5 — P1: Dropped events can advance replay report timestamps

[`analyze_replay_session`](../gex_terminal/replay_lab.py) records incoming
metadata before consumer validation and creates a timeline point after each
message once state exists, including rejected messages. Its final snapshot time
comes from the last input timestamp, independently of the model's accepted
`as_of`.

In a synthetic ES session valid through `2026-08-01T14:00:02Z`, a later NQ tick
at `2026-08-02T15:00:00Z` is correctly dropped by the consumer. The replay report
nevertheless adds a timeline row for that dropped event and dates the final
snapshot at the NQ timestamp; `model.as_of` still records the earlier ES time.

Repair acceptance: separate the raw input audit trail from accepted-state
timeline points. Use accepted event time for the analytical snapshot and do not
attribute model transitions to dropped events. Test late off-symbol, malformed,
and rejected records after a valid chain already exists, including downstream
journal/report use.

### H6 — P2: Small terminal layouts hide the core research view

Offline screenshots were inspected at 180×54, 120×40, and 80×24 terminal cells.
The large view shows the strike matrix. At 120×40 its headers remain but data
rows are clipped from the initial view; at 80×24 the matrix/structure area
disappears and metric labels truncate.

[`gex_terminal.tcss`](../gex_terminal/gex_terminal.tcss) fixes side columns at
20 and 40 cells and assigns 9, 10, and 7 rows around the remaining matrix row.
The fixed portions consume the available space at smaller sizes. Current
screenshot tests verify generation, not access to core content.

Repair acceptance: reflow or scroll the layout, or show a clear minimum-size
message. Test actual visibility/access to the strike table, quality, and replay
controls at declared supported sizes. A nonempty SVG alone is insufficient.

## Other Limits And Open Contract Questions

- **Portability:** experiment output records an absolute `source_root` and emits
  a report plus manifest, without bundling its input. Reproduction still needs
  access to that original source location. The portable research loop in
  Phase 1 must provide rights-aware source resolution and inspect manifests for
  local path disclosure before sharing. This is a product gap, not a new claim
  that local reproduction is broken.
- **Corpus cutoff scope:** registration accepts an omitted `as_of`, stores
  `null`, and passes corpus verification. The registration contract checks
  membership/integrity; the reviewed documentation does not clearly require a
  cutoff for every kind of registered source. Clarify the boundary with the
  point-in-time research invariant before empirical use. This is a contract
  question, not a confirmed instance of future data entering an evaluation.

## Verification Record

Local environment: macOS 26.6 ARM64, CPython 3.12.13. Commands used the source
environment for regression and a separate temporary virtual environment for
fresh-wheel checks. Temporary generated artifacts were kept outside the
repository. No production data, credentials, or provider connections were used.

| Check | Result | Boundary |
| --- | --- | --- |
| Compile and full regression suite | 297 tests passed | Existing tests do not cover H1–H6 |
| Dependency consistency | `pip check` passed in source and fresh environments | Dependency resolution consistency; no vulnerability audit claimed |
| Source/wheel build and metadata | Both distributions built; Twine passed | Build used installed build tools with `--no-isolation` |
| Fresh wheel, arbitrary working directory | Version, replay catalog, replay export, fixture lab, Demo Lab, and screenshot commands passed | Python 3.12 on this Mac; cross-platform UX/installer support is unmeasured |
| Provider fixture lab | 5/5 passed, 2 intentionally degraded | Provider-shaped offline fixtures only |
| Demo Lab | 12 artifacts generated | Existing pack baseline; no customer acceptance claim |
| Numerical evidence | Passed | Formula/pipeline checks; predictive validity unmeasured |
| Model property checks | 7/7 passed | Deterministic properties and input cases |
| Provider fault checks | 7/7 passed | Scripted faults; live transport false |
| Databento offline certification | Passed | Offline path only; live transport false |
| Generated-chain performance | Passed at 100 contracts | Broad regression budgets, not a capacity benchmark |
| Terminal inspection | Three sizes inspected; H6 observed | Automated synthetic rendering, not a user study |
| Adversarial review probes | H1–H5 reproduced | Targeted cases beyond the existing suite |

The 100-contract performance observation was approximately 1,609 normalized
records/second, 13.6 ms per snapshot, and 0.664 MiB peak traced memory, against
the existing smoke budgets of 5 records/second, 5,000 ms, and 512 MiB. This is a
single local generated workload; it does not establish exchange latency,
production memory use, sustained throughput, or live capacity.

## Reproduce The Review

Use the contributor setup and verification commands in
[Contributing](../CONTRIBUTING.md). In an installed environment outside the
checkout, the relevant offline public workflows are:

```bash
gex-terminal --version
gex-terminal list-replays
gex-terminal --replay-session trend-day --export snapshot.json
gex-terminal fixture-lab fixtures.json
gex-terminal demo-lab demo --replay-session zero-gamma-flip
gex-terminal model-evidence numerical.json
gex-terminal model-property-certify properties.json
gex-terminal provider-fault-certify faults.json
gex-terminal databento-offline-certify databento.json --symbol ES --multiplier 50
gex-terminal performance-certify performance.json --performance-contracts 100 \
  --minimum-ingest-rps 5 --maximum-snapshot-ms 5000 --maximum-peak-mb 512
gex-terminal --demo --screenshot compact.svg --screenshot-width 120 --screenshot-height 40
gex-terminal --demo --screenshot small.svg --screenshot-width 80 --screenshot-height 24
```

Run the commands in a new scratch directory so they do not overwrite existing
research. All confirmed H1–H5 probes should become regressions in their
respective repair changes; they are not covered by rerunning only the current
suite.

The [roadmap work order](../ROADMAP.md#current-work-order) places P1 correctness
repairs ahead of new features, then proceeds to offline preflight, a complete
research loop, guided installation, and supported live beta work. H6 belongs
to the guided-journey slice. Customer discovery can proceed alongside repairs.

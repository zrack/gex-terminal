# First Run — Offline Research

Start with synthetic data. No provider account, credential or live-market
subscription is needed. This guide owns local setup, wheel installation and the guided
Today → Explain → Compare → Replay → Review journey. Detailed pack contracts
belong in [Demo Lab](demo-lab.md).

## Choose Terminal, Wind Tunnel or Both

In a fresh setup folder whose reviewed wheel includes Wind Tunnel, open
**GEX App/Start GEX.command** on macOS. On Linux, run:

```bash
"./GEX App/run-gex" --choose
```

Choose `1` for **Terminal**, `2` for **Wind Tunnel**, `3` for **Both**, or `q`
to cancel. Pressing Return without a choice also cancels. The terminal opens a
bundled synthetic replay; Wind Tunnel opens the local browser workbench.

**Both** starts one managed session. Quitting the terminal with `q`, pressing
Control-C or closing its launcher window also stops the Wind Tunnel server
started by that session. A startup failure cancels the combined launch. Closing
only the browser tab closes the view; it does not stop the server. A separately
started Wind Tunnel server is independent and is not stopped by this session.

The two interfaces do not share their selected source, checkpoint, scenario or
in-memory state. Both makes them available together; choose and inspect each
interface's source explicitly. Terminal exports and Wind Tunnel receipts remain
separate artifacts in the research folder.

| Mode | macOS shortcut | Linux command |
| --- | --- | --- |
| Terminal | `GEX App/Start Terminal.command` | `"./GEX App/run-gex"` |
| Wind Tunnel | `GEX App/Start Wind Tunnel.command` | `"./GEX App/run-wind-tunnel"` |
| Both | Choose `3` in `GEX App/Start GEX.command` | `"./GEX App/run-gex" --both` |

A terminal-only installed wheel keeps its direct terminal path. Wind Tunnel
requires a reviewed wheel that includes that module. The independent browser
shortcut stays running until Control-C stops its server. Its receipts live in
the research folder's `wind-tunnel` subfolder. The three worked examples in
[Wind Tunnel](wind-tunnel.md) are a useful first browser session.

The chooser is a setup-helper enhancement after the `v0.6.0` release. It does
not change that application wheel or tag. Older installed shortcuts retain
their verified bytes during an in-place update, so use a **new reviewed setup
folder** to obtain the unified starter and explicit Terminal shortcut. Keep the
original 0.6.0 setup and your research. No data is moved or migrated.

## Market Wind Tunnel

For manual wheel installations, run `gex-terminal wind-tunnel`. No provider
credentials or network connection are needed after dependencies are installed.
Use [Wind Tunnel](wind-tunnel.md) for scenario controls, receipts and the direct
server command. Manual CLI commands do not add the setup folder's chooser.

## Install and open the reviewed bundle

Obtain the reviewed setup folder from your maintainer and put it in its
permanent location. It contains the application wheel, `install_app.py`,
`Install.command`, `START HERE.txt` and `bundle.json`. Use Python 3.11 or 3.12
on macOS or Linux. There is no PyPI publication, signed native installer or
hosted release download promised by this repository.

On **macOS**, open `Install.command`. On **Linux**, open a terminal in the
supplied folder and run:

```bash
sh Install.command
```

Setup creates `GEX App` and a separate `GEX App Research` folder, checks the
supplied wheel checksum, installs an isolated application environment, and
checks dependencies, offline doctor and a bundled replay. An interactive setup
then offers the starter choice when Wind Tunnel is available. No activation,
Git checkout, provider account or credentials are required. It does not change
system Python or shell profiles.

To return later, open **`GEX App/Start GEX.command`** on macOS, or run:

```bash
"./GEX App/run-gex" --choose
```

For a direct terminal launch, use `Start Terminal.command` or omit `--choose`
from `run-gex`. For Wind Tunnel or Both automation, `--no-browser` prints the
local launch URL instead of requesting a browser window. The macOS terminal
shortcut requests a 120×40 terminal for an interactive start;
resize guidance remains available when the terminal ignores that request.

Keep the installed application folder in place: Python environments contain
absolute paths. If you want another location, install into a new folder.
Research remains separately stored; reinstalling does not move or delete it.

The first setup normally downloads Python dependencies. A bundle with a complete
`wheelhouse/` uses only those local dependency wheels and fails if the selected
Python/platform is not covered. Application launches and bundled replay need no
network. Windows setup and unaided customer activation remain unverified.

The terminal path starts `zero-gamma-flip`, clears inherited application and
provider settings, and loads configuration before entering your research folder.
Caller and research-folder `.env` files therefore cannot select a live provider
or break this first-use path. The ordinary `gex-terminal` CLI remains available
inside the environment for separately configured advanced workflows.

The setup receipt, `GEX App/installation.json`, identifies the exact wheel,
supplied source commit, installed application payload, Python and dependency
versions. Application version `0.6.0` alone does not identify the setup helper
or its shortcuts; the reviewed bundle inventory identifies their exact bytes.
The expected checksum and source claim come from the maintainer; a matching
hash detects changed bytes and does not independently authenticate the sender.
[Study Build](study-build.md) owns the separate frozen cohort materials; this
new setup workflow does not replace that study bundle.

### Local setup options

Maintainers can use the standalone installer directly, substituting the reviewed
wheel identity and explicit destination:

```bash
python3 install_app.py --wheel PATH_TO_REVIEWED_WHEEL \
  --sha256 EXPECTED_WHEEL_SHA256 --source-commit FULL_SOURCE_COMMIT \
  --target "GEX App"
```

Use `--research-dir PATH` to select a separate research folder and
`--wheelhouse PATH` for installation without dependency downloads. The installer
refuses to adopt an existing unowned application folder. Repeating setup for the
same wheel verifies the installed payload against that wheel and runs the local
checks again without creating another environment or reinstalling dependencies.
It rejects changed application payload or launcher files instead of overwriting
them. A failed preparation can be retried if no launcher was published; an
incomplete or modified published installation requires a new application folder.

To diagnose the installed offline path without opening the terminal interface:

```bash
"./GEX App/run-gex" --doctor
"./GEX App/run-gex" --list-replays
```

Doctor exit 0 means the local path is structurally usable. Optional provider
warnings do not require installing extras. Exit 1 means a base installation,
resource or storage failure; exit 2 means invalid configuration or an unusable
selected path. See [Doctor](doctor.md) for the complete diagnostic contract.

### Manual wheel installation

The regular wheel remains the installation mechanism. Substitute the supplied
wheel's actual path below. These commands avoid shell activation:

```bash
python3 -m venv gex-app
gex-app/bin/python -m pip install /path/to/gex_terminal-0.6.0-py3-none-any.whl
gex-app/bin/gex-terminal --demo
```

Keep research outside `gex-app` and invoke that environment's `gex-terminal`
again to return. An editable development install is not needed for end-user
operation. [Contributing](../CONTRIBUTING.md#verification) owns build verification.

## Today: open one declared session

Use a terminal at least 100 columns by 32 rows. Essential columns keep strike,
call/put quantities and net exposure visible in the smaller layout. At 140×42
the full table has more room; 180×54 exposes more context. Below the minimum,
the app shows resize guidance. Press `c` to switch between essential and full
columns; horizontal scrolling reaches extra columns in a smaller window.

```bash
"./GEX App/run-gex" --list-replays
"./GEX App/run-gex" --session nq-research-loop
```

Confirm that the selected session identifies NQ, its multiplier is 20, and its
origin is synthetic replay. The ES scenarios remain separate instruments; do
not interpret a cross-symbol dollar difference as model disagreement. A replay
timestamp is historical fixture time, not “the market now.”

## Explain: inspect what a level means

Read one wall or strike-profile level alongside quality, model and source
information. Ask which contracts and quantity produced it, whether IV is
observed or assumed, and what is unavailable. OI, raw traded volume and
directionalized volume are proxies, not observed dealer positions. Definitions
and units are in [Model Assumptions](model-assumptions.md).

On the dashboard, press `p` to open the replay browser. `Up`/`Down` move through
sessions and wrap at either end; `Enter` loads the selected session. `Escape`
or `p` closes it without loading. When the browser is closed, the strike table
keeps its normal arrow-key and `Enter` behavior. An overlay retains its own
keyboard controls. Replay replacement is available only in demo/replay mode
and is blocked during capture. Press `q` to quit when finished.

Press `?` for the short research loop and keyboard guide. Press `v` to inspect
source, fallback assumptions, quality, recent events and the last export path;
these details remain reachable at every supported size. Press `e` to save the
current snapshot. The app confirms its destination and uses a distinct filename
for each save. The bundle launcher saves in its research folder; a direct CLI
launch saves in its current working directory. Sorting, refreshes and column
changes retain the selected strike when it is still present.

## Compare, Replay and Review

For these advanced commands, use the installed CLI. Bundle setup does not add a
command to your shell's search path. From the setup folder, locate its current
CLI once, then generate the NQ pack in your separate research folder:

```bash
GEX_CLI=$(python3 -c 'import json,pathlib; app=pathlib.Path("GEX App").resolve(); receipt=json.loads((app/"installation.json").read_text()); print(app/"environments"/receipt["active"]["environment"]/"bin"/"gex-terminal")')
"$GEX_CLI" demo-lab "GEX App Research/nq_demo_lab" --replay-session nq-research-loop
"$GEX_CLI" demo-lab verify "GEX App Research/nq_demo_lab"
```

In the linked Demo Lab examples, replace `gex-terminal` with `"$GEX_CLI"`.
For the manual wheel setup above, use `./gex-app/bin/gex-terminal` instead.
These commands need no shell activation; unlike the offline dashboard launcher,
the advanced CLI reads ordinary application configuration from its environment.

Generate a new pack in a separate research folder. Use a new output directory
for each run; do not overwrite a prior result. The exact receipt verification
and reproduction commands, file inventory, interpretation and compatibility
rules are in [Demo Lab](demo-lab.md). Follow its NQ example to:

1. Compare OI, raw-volume and directionalized-volume results on identical input.
   Read disagreement and direction-coverage limits instead of summing models.
2. Replay the included synthetic source and inspect the accepted-state timeline.
3. Verify the receipt, copy the entire pack, and reproduce into a new directory.

Success means an unchanged authorized input and supported implementation yield
the same semantic results. It does not establish real-time provider operation,
forecasting skill, execution quality or profit. Never share a private capture
just because a synthetic pack is shareable.

## Update, recover and uninstall

Close the terminal and stop any standalone Wind Tunnel launcher before updating,
retain the previous reviewed bundle, and
keep a verified private backup of your research. The simplest update is to
install the new reviewed bundle in a new permanent folder; the previous Start
launcher remains available. The new bundle's default research folder starts
separately. Use the standalone installer's `--research-dir` option if you intend
to reopen the existing research folder; no data is moved or migrated by setup.

For an update within an installer-owned application folder, run the standalone
installer with the new wheel, its checksum/source identity, the same `--target`
and the same research destination. It creates a separate environment, validates
it, and only then changes the active installation receipt. Existing launcher
bytes remain unchanged. A failed dependency install, application check or final
receipt update leaves the previous completed selection available. Older and
failed candidate environments remain in place; setup never deletes them.

To return to an older application, use its retained bundle and Start launcher.
Older versions may reject newer research formats; reinstalling does not migrate
or relabel research. Keep both builds until you have verified the needed path.

There is no automatic updater or automatic cleanup. To stop using an application,
close it and remove its installer-owned `GEX App` folder only after confirming
its location. The separate research folder and original bundle are not part of
the application environment. Do not delete research as an installation fix.
[Local Support](local-support.md) owns backup, recovery and deliberate retention.

Manual virtual-environment installations can still use `python -m pip install`
or `python -m pip uninstall gex-terminal` with that environment's Python. Do not
use those commands to mutate a checksum-verified bundle environment: its next
setup verification should reject a changed application payload.

## Verification boundary

The release lifecycle check installs a retained 0.4.0 wheel, creates synthetic
research, upgrades to 0.5.0, rejects a corrupt update, rolls back, reinstalls and
uninstalls while comparing every research-file byte identity. The repeatable
maintainer check is `scripts/verify_distribution_lifecycle.py`; the latest
platforms and results are recorded in [Application Review](application-review.md).
The setup wrapper adds a reviewed local handoff around the same wheel mechanism.
It verifies package bytes before import, checks repeat installation and failed
updates, and keeps research separate. These checks do not establish every
interrupted-install failure mode or a customer-selected distribution channel.
Real users must still demonstrate the roadmap's unaided activation targets.

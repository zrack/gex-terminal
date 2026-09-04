# First Run — Offline Research

Start with synthetic data. No provider account, credential or live-market
subscription is needed. This guide owns the wheel installation and the guided
Today → Explain → Compare → Replay → Review journey. Detailed pack contracts
belong in [Demo Lab](demo-lab.md).

## Install one reviewed wheel

Use Python 3.11 or 3.12 for the tested baseline. Obtain the exact reviewed wheel
from your maintainer, with its version and digest. There is no PyPI publication
or hosted release download promised by this repository. Contributors can build
the wheel using [Contributing](../CONTRIBUTING.md); end users do not need a Git
checkout. Dependency installation may use the network; the application journey
below does not.

Create a dedicated application folder outside your research folder. Substitute
the actual supplied wheel path; do not type the placeholder literally:

```bash
python3 -m venv gex-app
source gex-app/bin/activate
python -m pip install /path/to/gex_terminal-0.5.0-py3-none-any.whl
gex-terminal --version
gex-terminal doctor
```

These shell instructions cover macOS/Linux. Windows activation/installer and
unaided customer setup are not verified by this release. A regular wheel is the
supported technical baseline; an editable development install is not required.

Doctor exit 0 means the selected local path is structurally usable, not live
certified. Optional provider warnings do not require installing every extra.
Exit 1 means a base installation/resource/storage failure; exit 2 means invalid
configuration or a structurally unusable selected path. See [Doctor](doctor.md)
for diagnosis and safe text/JSON output. Do not add credentials to make the
offline walkthrough work.

## Today: open one declared session

Use a terminal at least 140 columns by 42 rows; 180×54 exposes more context.
Smaller windows show resize guidance instead of a clipped research view.

```bash
gex-terminal list-replays
gex-terminal --replay-session nq-research-loop
```

Confirm that the selected session identifies NQ, its multiplier is 20, and its
origin is synthetic replay. The ES scenarios remain separate instruments; do
not interpret a cross-symbol dollar difference as model disagreement. A replay
timestamp is historical fixture time, not “the market now.”

## Explain: inspect what a level means

Read one wall or strike-profile level alongside quality, model and source
information. Ask which contracts and quantity produced it, whether IV is
observed or assumed, and what is unavailable. OI, raw traded volume and
directionalized volume are proxies, not observed dealer positions. Use the
in-app replay browser (`p`) and quit (`q`) when finished. Definitions and units
are in [Model Assumptions](model-assumptions.md).

## Compare, Replay and Review

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

Keep research outside `gex-app`. Retain your previous reviewed wheel and a
verified private backup before changing versions. Close the terminal first.

```bash
python -m pip install --upgrade /path/to/new-reviewed-wheel.whl
gex-terminal --version
gex-terminal doctor
```

If an update fails, check version and doctor before reopening research. A
corrupt-wheel rejection is tested; every possible interrupted installation is
not. Recreate the virtual environment from the retained wheel if its integrity
is uncertain. Reinstalling an earlier release does not migrate newer research
formats backwards; unsupported versions must fail, not be relabeled.

To roll back within a working environment:

```bash
python -m pip install --force-reinstall --no-deps /path/to/previous-reviewed-wheel.whl
gex-terminal --version
```

`--no-deps` is suitable only when that prior wheel's declared dependency versions
are still satisfied; otherwise rebuild a clean environment from it. To uninstall
the package in this dedicated environment:

```bash
python -m pip uninstall gex-terminal
```

Uninstall does not delete separately stored research or credentials. Use
[Local Support](local-support.md) for private backup/recovery, safe support
diagnostics and explicit retention/deletion. Do not remove an entire research
folder as an installation troubleshooting step.

## Verification boundary

The release lifecycle check installs a retained 0.4.0 wheel, creates synthetic
research, upgrades to 0.5.0, rejects a corrupt update, rolls back, reinstalls and
uninstalls while comparing every research-file byte identity. The repeatable
maintainer check is `scripts/verify_distribution_lifecycle.py`; the latest
platforms and results are recorded in [Application Review](application-review.md).
The wheel is not yet a customer-selected commercial distribution channel.
Real users must still demonstrate the roadmap's unaided activation targets.

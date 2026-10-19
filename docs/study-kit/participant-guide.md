# Guided Session Intake — Participant Guide

Use the exact kit assigned by the moderator. Its `build-manifest.json` identifies
the source commit, wheel checksum, runtime and two synthetic captures. This is
an offline research task; no provider login or live feed is required. Use the
assigned ES or NQ capture rather than personal or licensed data.

The moderator obtains consent and assigns a de-identified participant ID before
the session. Recording needs separate consent. Keep account details and personal
information out of task notes. You may stop at any point.

Use a fresh virtual environment and the supplied wheel:

```bash
python3 -m venv study-env
source study-env/bin/activate
python -m pip install -c requirements-lock.txt ./@WHEEL_FILENAME@
gex-terminal --version
gex-terminal doctor --json
gex-terminal wind-tunnel --port 0 --workspace ./study-research
```

The kit freezes version `@APPLICATION_VERSION@` with its exact wheel checksum; that version alone
does not identify the build. Dependency installation may download packages.
The dependency lock is a set of version constraints, not an offline installer.
Use the OS/architecture and Python version recorded for this cohort, or have the
moderator record the difference before starting.

The launch prints a local browser URL. Keep its capability token private. Use
shipped help whenever useful and think aloud about what you understand or find
unclear. The moderator records assistance and failed attempts.

| Task | Goal |
| --- | --- |
| GI-01 | Install the frozen build and explain the offline readiness result. |
| GI-02 | Open the assigned capture through local session intake. Explain its source, instrument, multiplier, time range and assumptions before opening a checkpoint. |
| GI-03 | Choose the final event checkpoint and open it in Wind Tunnel. Explain one structural level and a quality or model limitation. |
| GI-04 | Inspect the separate model views and change one scenario parameter. Explain what changed. |
| GI-05 | Save and export your scenario receipt. Stop the server, launch a fresh server with a new empty workspace and reproduce the exported receipt there. |
| GI-06 | Open the assigned bundled replay in Terminal, use `w` to hand a checkpoint to Wind Tunnel and explain what this offline exercise establishes. |

For the last task, use the catalog name assigned by the moderator:

```bash
gex-terminal --replay-session zero-gamma-flip
# NQ assignment instead: gex-terminal --replay-session nq-research-loop
```

The bundled fixtures are synthetic. Their dates are fixture event dates. The
application's model guide explains its units and assumptions; the
[frozen First Run guide](../first-run.md) and
[Wind Tunnel guide](../wind-tunnel.md) contain the shipped workflows.
Save your exported receipt outside the server workspace before starting a fresh
server. Follow the moderator's retention instructions for study artifacts.

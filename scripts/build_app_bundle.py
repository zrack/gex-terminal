#!/usr/bin/env python3
"""Package an explicit wheel and the local installer for a simple user handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


INSTALLER = Path(__file__).with_name("install_app.py")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return path


def build_bundle(wheel: Path, output: Path, source_commit: str,
                 wheelhouse: Path | None = None) -> Path:
    """Create a new folder only; neither install nor run any supplied code."""
    regular_file(wheel)
    regular_file(INSTALLER)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_commit):
        raise ValueError("source-commit must be the full 40-character reviewed Git commit")
    if not re.fullmatch(r"gex_terminal-[A-Za-z0-9_.+]+-py3-none-any\.whl", wheel.name):
        raise ValueError("Expected a gex_terminal universal Python wheel")
    with zipfile.ZipFile(wheel) as archive:
        if "gex_terminal/cli.py" not in archive.namelist():
            raise ValueError("Wheel is missing the GEX application")
        has_wind_tunnel = "gex_terminal/wind_tunnel_cli.py" in archive.namelist()
    dependencies: list[Path] = []
    if wheelhouse is not None:
        if wheelhouse.is_symlink() or not wheelhouse.is_dir():
            raise ValueError("wheelhouse must be a regular directory of dependency wheels")
        dependencies = sorted(wheelhouse.glob("*.whl"))
        if not dependencies:
            raise ValueError("wheelhouse contains no dependency wheels")
        for dependency in dependencies:
            regular_file(dependency)
    output = output.absolute()
    # Never adopt, erase, or overwrite an existing handoff, including a symlink.
    output.mkdir(parents=True, exist_ok=False)
    (output / "INCOMPLETE").write_text("Bundle preparation has not completed.\n")
    shutil.copyfile(wheel, output / wheel.name)
    shutil.copyfile(INSTALLER, output / "install_app.py")
    if wheelhouse is not None:
        (output / "wheelhouse").mkdir()
        for dependency in dependencies:
            shutil.copyfile(dependency, output / "wheelhouse" / dependency.name)
    wheel_sha = file_hash(output / wheel.name)
    shell = '''#!/bin/sh
# Open this file on macOS, or run: sh Install.command
set -eu
BUNDLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -e "$BUNDLE_DIR/INCOMPLETE" ]; then
    printf '%s\\n' 'This setup folder is incomplete. Ask for a fresh reviewed bundle.' >&2
    exit 1
fi
GEX_PYTHON=''
for candidate in python3 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -I -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)' 2>/dev/null; then
        GEX_PYTHON=$(command -v "$candidate")
        break
    fi
done
if [ -z "$GEX_PYTHON" ]; then
    printf '%s\\n' 'Install Python 3.11 or 3.12 from https://www.python.org/downloads/ and reopen Install.command.' >&2
    if [ -t 0 ]; then printf '%s' 'Press Return to close: '; read -r reply; fi
    exit 1
fi
printf '%s\\n' 'Setting up GEX Terminal. Your research stays in GEX App Research.'
'''
    shell += ('"$GEX_PYTHON" -I "$BUNDLE_DIR/install_app.py"'
              f' --wheel "$BUNDLE_DIR/{wheel.name}" --sha256 {wheel_sha}'
              f' --source-commit {source_commit.lower()}'
              ' --target "$BUNDLE_DIR/GEX App"')
    if wheelhouse is not None:
        shell += ' --wheelhouse "$BUNDLE_DIR/wheelhouse"'
    shell += '\n'
    shell += '''printf '\\n%s\\n' 'Setup complete. Open a launcher in GEX App any time to return.'
if [ -t 0 ] && [ -t 1 ]; then
'''
    # Use the validated setup helper, not an optional file that an older
    # three-launcher installation might leave outside its receipt inventory.
    if has_wind_tunnel:
        shell += '    exec "$GEX_PYTHON" -I "$BUNDLE_DIR/install_app.py" --launch --wind-tunnel --target "$BUNDLE_DIR/GEX App"\n'
    else:
        shell += '    exec "$BUNDLE_DIR/GEX App/Start GEX.command"\n'
    shell += 'fi\n'
    launch = output / "Install.command"
    launch.write_text(shell, encoding="utf-8")
    launch.chmod(0o755)
    dependencies_note = (
        "Dependency wheels are included. Setup uses only the supplied wheelhouse; "
        "it fails if dependencies for your platform/Python are missing."
        if wheelhouse is not None else
        "First setup downloads Python dependencies. Later launches need no network."
    )
    wind_note = (
        "MARKET WIND TUNNEL\n"
        "Open GEX App/Start Wind Tunnel.command on macOS or GEX App/run-wind-tunnel on Linux.\n"
        "The first interactive setup opens the Wind Tunnel in your browser.\n"
        "Choose Examples for three worked synthetic experiments.\n"
        "Use Save experiment to retain results in GEX App Research/wind-tunnel.\n"
        "Keep the launcher window open while exploring. Control-C stops the local server.\n"
        "Charts and calculations work offline; the browser connects only to this computer.\n\n"
        if has_wind_tunnel else ""
    )
    (output / "START HERE.txt").write_text(
        "GEX TERMINAL — LOCAL RESEARCH\n\n"
        "1. Keep this folder in its permanent location before setup.\n"
        "2. Install Python 3.11 or 3.12 if needed (python.org/downloads).\n"
        "3. On macOS, open Install.command. On Linux, run: sh Install.command\n"
        "4. Return using GEX App/Start GEX.command on macOS or GEX App/run-gex on Linux.\n\n"
        + wind_note +
        "The terminal launcher opens a bundled synthetic replay.\n"
        "Press p to choose a replay, ? for help, e to export, q to quit.\n"
        "Exports are saved in the separate GEX App Research folder.\n\n"
        f"{dependencies_note}\n"
        "No provider account or credentials are needed. No system Python or shell profile is changed.\n"
        "Keep this folder in place after setup: Python environments contain absolute paths.\n"
        "For an update, retain your old folder and install a new reviewed bundle separately.\n"
        "This is a local Python application, not a signed native app or a live-market service.\n"
        "The checksum establishes file identity, not publisher trust; obtain the bundle from your maintainer.\n\n"
        f"Source commit: {source_commit.lower()}\nWheel SHA-256: {wheel_sha}\n",
        encoding="utf-8",
    )
    inventory = {
        str(path.relative_to(output)): {"sha256": file_hash(path), "bytes": path.stat().st_size}
        for path in sorted(output.rglob("*")) if path.is_file() and path.name != "INCOMPLETE"
    }
    (output / "bundle.json").write_text(json.dumps({
        "schema": "gex-terminal.app-bundle.v1",
        "source_commit": source_commit.lower(),
        "wheel": wheel.name,
        "wheel_sha256": wheel_sha,
        "dependencies_included": wheelhouse is not None,
        "files": inventory,
        "scope": "Local installation handoff; source identity supplied by maintainer, not independently attested.",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "INCOMPLETE").unlink()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    try:
        output = build_bundle(args.wheel, args.output, args.source_commit, args.wheelhouse)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Bundle not completed: {exc}\n")
    print(f"Prepared {output}\nOpen Install.command to set up the app.")


if __name__ == "__main__":
    main()

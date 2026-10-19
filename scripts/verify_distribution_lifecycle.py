"""Exercise two local wheels in a disposable environment, never a user's install.

The first install may download normal package dependencies. Every application
command is offline. Research lives outside the disposable virtual environment.
Requires the maintainer tools documented in CONTRIBUTING.md, including packaging.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

from packaging.version import Version


def wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("wheel must contain one package metadata record")
        metadata = email.message_from_bytes(archive.read(names[0]))
        if metadata["Name"] != "gex-terminal":
            raise ValueError("lifecycle checks accept only gex-terminal wheels")
        return str(metadata["Version"])


def tree_identity(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify(previous: Path, candidate: Path) -> dict:
    old_version, new_version = wheel_version(previous), wheel_version(candidate)
    if Version(new_version) <= Version(old_version):
        raise ValueError("upgrade evidence requires candidate version newer than previous")
    wheel_hashes = {
        "previous": hashlib.sha256(previous.read_bytes()).hexdigest(),
        "candidate": hashlib.sha256(candidate.read_bytes()).hexdigest(),
    }
    environment = {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG",
                   "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"}
    }
    environment.update({"PYTHONNOUSERSITE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    steps = []
    with tempfile.TemporaryDirectory(prefix="gex-lifecycle-") as directory:
        workspace = Path(directory).resolve()
        install = workspace / "environment"
        research = workspace / "research"
        research.mkdir()
        venv.EnvBuilder(with_pip=True).create(install)
        binary = install / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        app = binary / ("gex-terminal.exe" if os.name == "nt" else "gex-terminal")

        def run(*args: str | Path, expect_failure: bool = False) -> str:
            completed = subprocess.run(
                [str(arg) for arg in args], cwd=workspace, env=environment,
                text=True, capture_output=True, timeout=240,
            )
            if (completed.returncode != 0) != expect_failure:
                # Inputs and output here contain disposable synthetic state only.
                raise RuntimeError(
                    f"lifecycle command exit {completed.returncode}: "
                    f"{completed.stdout[-1500:]} {completed.stderr[-1500:]}"
                )
            return completed.stdout

        def installed_version(expected: str) -> None:
            actual = json.loads(run(python, "-c", (
                "import json, gex_terminal; from pathlib import Path; "
                "print(json.dumps([gex_terminal.__version__, str(Path(gex_terminal.__file__).resolve())]))"
            )))
            if actual[0] != expected or not Path(actual[1]).is_relative_to(install):
                raise AssertionError("wheel version or isolated import location mismatch")
            if expected not in run(app, "--version"):
                raise AssertionError("console version mismatch")

        run(python, "-m", "pip", "install", "--quiet", previous)
        installed_version(old_version)
        run(app, "--demo", "--export", research / "snapshot.json")
        run(app, "corpus-init", research / "corpus", "--corpus-id", "lifecycle-synthetic")
        run(app, "demo-lab", research / "legacy-pack", "--replay-session", "gap-fade")
        before = tree_identity(research)
        steps.append("install_previous_and_create_synthetic_research")

        def preserved() -> None:
            if tree_identity(research) != before:
                raise AssertionError("installation lifecycle changed research artifacts")

        run(python, "-m", "pip", "install", "--quiet", "--upgrade", candidate)
        installed_version(new_version)
        run(python, "-m", "pip", "check")
        doctor = json.loads(run(app, "doctor", "--json"))
        if doctor.get("schema") != "gex-terminal.doctor.v1":
            raise AssertionError("doctor schema missing from installed wheel")
        run(app, "corpus-verify", research / "corpus", workspace / "corpus-check.json")
        preserved()
        steps.append("upgrade_and_verify_prior_artifact_bytes")

        broken = workspace / "invalid-wheel" / candidate.name
        broken.parent.mkdir()
        broken.write_bytes(b"invalid synthetic wheel for rollback testing\n")
        run(python, "-m", "pip", "install", "--no-deps", "--force-reinstall",
            broken, expect_failure=True)
        installed_version(new_version)
        run(python, "-m", "pip", "check")
        run(app, "doctor", "--json")
        run(app, "--demo", "--export", workspace / "failed-upgrade-snapshot.json")
        preserved()
        steps.append("reject_corrupt_upgrade_without_replacing_working_install")

        run(python, "-m", "pip", "install", "--quiet", "--no-deps",
            "--force-reinstall", previous)
        installed_version(old_version)
        preserved()
        run(python, "-m", "pip", "check")
        run(app, "--demo", "--export", workspace / "rollback-snapshot.json")
        steps.append("rollback_previous_wheel_without_rewriting_research")

        run(python, "-m", "pip", "install", "--quiet", "--no-deps",
            "--force-reinstall", candidate)
        installed_version(new_version)
        run(python, "-m", "pip", "uninstall", "--yes", "gex-terminal")
        if run(python, "-c", "import importlib.util; print(importlib.util.find_spec('gex_terminal'))").strip() != "None":
            raise AssertionError("uninstall left an importable package")
        metadata_absent = run(python, "-c", (
            "from importlib.metadata import version, PackageNotFoundError\n"
            "try:\n version('gex-terminal')\nexcept PackageNotFoundError:\n print('absent')"
        )).strip()
        if metadata_absent != "absent" or app.exists() or app.is_symlink():
            raise AssertionError("uninstall left package metadata or the console launcher")
        preserved()
        steps.append("uninstall_preserves_separate_research")

        if wheel_hashes != {
            "previous": hashlib.sha256(previous.read_bytes()).hexdigest(),
            "candidate": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        }:
            raise AssertionError("wheel inputs changed during lifecycle verification")

        return {
            "schema": "gex-terminal.distribution-lifecycle.v1",
            "previous_version": old_version, "candidate_version": new_version,
            "wheel_sha256": wheel_hashes,
            "platform": platform.system(), "machine": platform.machine(),
            "python": platform.python_version(), "steps": steps,
            "preserved_artifact_count": len(before), "passed": True,
            "evidence_ceiling": (
                "disposable offline installation and byte-preservation checks; "
                "corrupt-wheel failure only, not arbitrary interrupted-install recovery; "
                "no live-data, user-activation or prior-format reader compatibility claim"
            ),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-wheel", type=Path, required=True)
    parser.add_argument("--candidate-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not already exist")
    result = verify(args.previous_wheel.resolve(), args.candidate_wheel.resolve())
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

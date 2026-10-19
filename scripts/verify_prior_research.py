"""Verify actual 0.5.0 research using the candidate installed-wheel reader.

Creates only disposable environments/research; never edits the supplied wheel.
Dependencies are inherited from the caller's tested environment. The producer
package is installed separately without dependency or network resolution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import venv


def verify(previous: Path, reader: Path) -> dict:
    previous, reader = previous.resolve(), reader.absolute()
    with tempfile.TemporaryDirectory(prefix="gex-prior-research-") as directory:
        root = Path(directory)
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("GEX_", "DATABENTO_", "TRADOVATE_", "PYTHON"))}
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

        def run(python, *arguments):
            result = subprocess.run([str(python), "-I", *map(str, arguments)],
                                    cwd=root, env=environment, capture_output=True,
                                    text=True, timeout=180)
            if result.returncode:
                raise RuntimeError(f"Prior-research check failed: {result.stderr[-3000:]}")
            return result.stdout

        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(root / "producer")
        producer = root / "producer/bin/python"
        # Nested venvs inherit the base interpreter's packages, not the
        # invoking venv's dependencies. Add that tested dependency directory
        # behind the producer's own site-packages; version checks below ensure
        # the separately installed historical application wins import lookup.
        producer_library = Path(run(producer, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))").strip())
        caller_libraries = sorted({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
        (producer_library / "gex-tested-dependencies.pth").write_text("\n".join(caller_libraries) + "\n")
        run(producer, "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", previous)
        old = run(producer, "-c", "import gex_terminal; print(gex_terminal.__version__)").strip()
        new = run(reader, "-c", "import gex_terminal; print(gex_terminal.__version__)").strip()
        if old != "0.5.0" or new != "0.6.0":
            raise ValueError("This gate requires a real 0.5.0 producer and 0.6.0 installed reader")
        run(producer, "-m", "gex_terminal.cli", "demo-lab", root / "pack", "--replay-session", "nq-research-loop")
        fixture = run(producer, "-c", "from gex_terminal.package_data import provider_fixture_path; print(provider_fixture_path('experiment_spec_example.json'))").strip()
        run(producer, "-m", "gex_terminal.cli", "experiment-run", fixture, root / "experiment")

        def identity():
            return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for folder in (root / "pack", root / "experiment")
                    for path in folder.rglob("*") if path.is_file()}

        before = identity()
        for arguments in (
            ("demo-lab", "verify", root / "pack"),
            ("demo-lab", "reproduce", root / "pack", root / "reproduced-pack"),
            ("experiment-reproduce", root / "experiment/manifest.json", root / "reproduced-experiment"),
        ):
            run(reader, "-m", "gex_terminal.cli", *arguments)
        if identity() != before:
            raise AssertionError("Prior research bytes changed")
        return {"schema": "gex-terminal.prior-research-check.v1", "passed": True,
                "producer_version": old, "reader_version": new,
                "producer_wheel_sha256": hashlib.sha256(previous.read_bytes()).hexdigest(),
                "preserved_files": len(before), "input_sha256": before,
                "checks": ["demo_receipt_verify", "demo_receipt_reproduce", "experiment_reproduce", "input_preservation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-wheel", type=Path, required=True)
    parser.add_argument("--reader-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.previous_wheel, args.reader_python)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print("Prior 0.5.0 Demo Lab and experiment research verified by the installed 0.6.0 reader.")


if __name__ == "__main__":
    main()

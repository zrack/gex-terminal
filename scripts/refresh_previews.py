"""Stage synthetic documentation previews from this checkout and interpreter.

No application imports occur in the maintainer process. Application commands run
in isolated Python processes from a new temporary directory with a small
environment allowlist, so neither caller configuration nor a checkout .env is
used. Generated study bundles and existing research directories are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from typing import Mapping
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SESSION = "zero-gamma-flip"
WIDTH, HEIGHT = 180, 54
ONBOARDING_HEIGHT = 64
ASSETS = {
    "demo.svg": "gex-terminal-demo-lab.svg",
    "onboarding.svg": "gex-terminal-onboarding.svg",
}
BOOTSTRAP = (
    "import runpy,sys; source=sys.argv.pop(1); sys.path.insert(0,source); "
    "runpy.run_module('gex_terminal.cli',run_name='__main__')"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def clean_environment(environment: Mapping[str, str]) -> dict[str, str]:
    # Drop GEX_*, provider credentials, Python overrides, HOME and every other
    # ambient application setting rather than maintaining a credential denylist.
    result = {
        key: value for key, value in environment.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TMPDIR", "TEMP", "TMP"}
    }
    result.update({"LANG": "C.UTF-8", "TZ": "UTC", "PYTHONNOUSERSITE": "1"})
    return result


def source_command(root: Path, arguments: list[str]) -> list[str]:
    # -I ignores PYTHONPATH/user site; insert only the explicitly selected source.
    return [sys.executable, "-I", "-c", BOOTSTRAP, str(root), *arguments]


def source_identity(root: Path, environment: Mapping[str, str]) -> dict:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments], env=environment,
            text=True, capture_output=True, check=True, timeout=30,
        ).stdout.strip()

    status = git("status", "--porcelain", "--untracked-files=normal")
    paths = [root / "main.py", root / "pyproject.toml",
             root / "scripts" / "refresh_previews.py"]
    paths.extend(sorted((root / "gex_terminal").rglob("*.py")))
    paths.extend(sorted((root / "gex_terminal").rglob("*.tcss")))
    source_hashes = {path.relative_to(root).as_posix(): sha256(path) for path in paths}
    input_hashes = {
        path.relative_to(root).as_posix(): sha256(path)
        for folder in ("replays", "provider_fixtures")
        for path in sorted((root / "gex_terminal" / "data" / folder).rglob("*"))
        if path.is_file() and path.suffix in {".json", ".jsonl", ".csv"}
    }
    return {
        "commit": git("rev-parse", "HEAD"), "dirty": bool(status),
        "worktree_status_sha256": hashlib.sha256(status.encode()).hexdigest(),
        "source_sha256": source_hashes, "bundled_input_sha256": input_hashes,
        "input_scope": "bundled replay catalog and provider-fixture files; not all are consumed",
    }


def runtime_identity(root: Path) -> dict:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = {}
    # Include the rendering dependency explicitly as well as application requirements.
    for requirement in [*project["dependencies"], "rich"]:
        name = requirement.split("[", 1)[0]
        for delimiter in ("=", "<", ">", "!", "~", ";", " "):
            name = name.split(delimiter, 1)[0]
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = {"version": None, "metadata_sha256": None}
        else:
            dependencies[name] = {
                "version": distribution.version,
                "metadata_sha256": hashlib.sha256(
                    (distribution.read_text("METADATA") or "").encode()
                ).hexdigest(),
            }
    return {
        "source_version": project["version"], "python": platform.python_version(),
        "executable": sys.executable, "platform": platform.system(),
        "machine": platform.machine(), "dependencies": dependencies,
        "dependencies_sha256": json_sha256(dependencies),
        "dependency_scope": "direct requirements and Rich metadata; not an environment lock",
    }


def svg_identity(path: Path) -> dict:
    root = ET.parse(path).getroot()
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("preview must be an SVG document")
    return {"sha256": sha256(path), "bytes": path.stat().st_size,
            "width": root.get("width"), "height": root.get("height"),
            "viewBox": root.get("viewBox")}


def write_assets(output: Path, root: Path) -> list[str]:
    pairs = []
    for staged, name in ASSETS.items():
        source = output / staged
        if not source.exists():
            continue
        target = root / "assets" / name
        if target.is_symlink() or not target.is_file():
            raise ValueError("asset destination must be an existing regular file")
        pairs.append((source, target))
    copied = []
    for source, target in pairs:
        shutil.copyfile(source, target)
        copied.append(target.relative_to(root).as_posix())
    return copied


def refresh(output: Path, *, include_onboarding: bool = False,
            update_assets: bool = False, root: Path = ROOT) -> dict:
    output = output.absolute()
    # Never reuse or empty an existing directory, including a symlink or bundle.
    output.mkdir(parents=True, exist_ok=False)
    environment = clean_environment(os.environ)
    manifest: dict = {
        "schema": "gex-terminal.documentation-previews.v1", "status": "running",
        "session": SESSION,
        "terminal_dimensions": {
            "demo_pack": {"columns": WIDTH, "rows": HEIGHT},
            **({"onboarding": {"columns": WIDTH, "rows": ONBOARDING_HEIGHT}}
               if include_onboarding else {}),
        },
        "commands": [], "assets": {}, "updated_repository_assets": [],
        "evidence_ceiling": "synthetic source-build previews; no participant or live-market evidence",
        "reproduction_limit": (
            "snapshot metrics and inputs are reproducible; report generation/as-of times for "
            "this legacy fixture, SVG identifiers and UI timing may vary"
        ),
    }
    try:
        manifest["source"] = source_identity(root, environment)
        manifest["runtime"] = runtime_identity(root)
        with tempfile.TemporaryDirectory(prefix="gex-preview-") as scratch_dir:
            scratch = Path(scratch_dir).resolve()
            manifest["working_directory"] = str(scratch)

            def run(arguments: list[str]) -> None:
                command = source_command(root, arguments)
                step = {"argv": command, "status": "running"}
                manifest["commands"].append(step)
                try:
                    result = subprocess.run(command, cwd=scratch, env=environment,
                                            capture_output=True, text=True, timeout=180)
                except (OSError, subprocess.SubprocessError) as exc:
                    step.update({"status": "failed", "failure_type": type(exc).__name__})
                    raise
                step.update({"exit_code": result.returncode,
                             "status": "passed" if result.returncode == 0 else "failed"})
                if result.returncode:
                    # Do not retain arbitrary subprocess diagnostics in public artifacts.
                    raise RuntimeError(f"preview command {len(manifest['commands'])} failed with exit {result.returncode}")

            pack = scratch / "demo-pack"
            dimensions = ["--screenshot-width", str(WIDTH), "--screenshot-height", str(HEIGHT)]
            run(["demo-lab", str(pack), "--replay-session", SESSION, *dimensions])
            run(["demo-lab", "verify", str(pack)])
            receipt = json.loads((pack / "review-receipt.json").read_text(encoding="utf-8"))
            manifest["demo_review_receipt_sha256"] = sha256(pack / "review-receipt.json")
            manifest["demo_receipt_content_sha256"] = receipt["content"]
            manifest["demo_source"] = receipt["source"]
            manifest["demo_model_profile_sha256"] = receipt["model"]["profile_sha256"]
            shutil.copyfile(pack / "gex-terminal-color.svg", output / "demo.svg")
            manifest["assets"]["demo.svg"] = svg_identity(output / "demo.svg")
            if include_onboarding:
                run(["--replay-session", SESSION, "--screenshot", str(output / "onboarding.svg"),
                     "--screenshot-view", "replay-browser", "--screenshot-width", str(WIDTH),
                     "--screenshot-height", str(ONBOARDING_HEIGHT)])
                manifest["assets"]["onboarding.svg"] = svg_identity(output / "onboarding.svg")
        after = source_identity(root, environment)
        before = manifest["source"]
        stable = all(before[key] == after[key] for key in ("commit", "source_sha256", "bundled_input_sha256"))
        manifest["source_unchanged_during_generation"] = stable
        if not stable:
            raise RuntimeError("source or bundled input changed during generation; rerun after edits settle")
        if update_assets:
            manifest["updated_repository_assets"] = write_assets(output, root)
        manifest["status"] = "passed"
        return manifest
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["failure_type"] = type(exc).__name__
        raise
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        help="new staging directory; defaults to ignored dist/previews-<unique-id>")
    parser.add_argument("--include-onboarding", action="store_true",
                        help="also capture the bundled replay picker")
    parser.add_argument("--write-assets", action="store_true",
                        help="copy generated previews to their repository assets after successful checks")
    args = parser.parse_args()
    output = args.output_dir or ROOT / "dist" / f"previews-{uuid.uuid4().hex[:12]}"
    try:
        refresh(output, include_onboarding=args.include_onboarding, update_assets=args.write_assets)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Preview generation failed: {exc}\n")
    print(f"Synthetic previews and manifest: {output.absolute()}")


if __name__ == "__main__":
    main()

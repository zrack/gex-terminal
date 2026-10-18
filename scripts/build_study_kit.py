"""Freeze one offline intake study kit from an explicitly reviewed Git commit.

Requires the contributor build tools in the invoking Python environment. No
dependency downloads, installation, participant observations or provider access
are performed. Generated files belong under ignored dist/study/.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version


SCHEMA = "gex-terminal.study-kit.v1"
PROTOCOL = "guided-intake-v1"
FIXTURES = ("zero-gamma-flip", "nq-research-loop")
TASK_IDS = tuple(f"GI-{index:02d}" for index in range(1, 7))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_requirements(raw: str) -> str:
    """Accept exact portable version constraints, never editable/local URLs."""
    requirements: dict[str, str] = {}
    for line in raw.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)", value)
        if not match:
            raise ValueError("dependency lock requires one exact name==version pin per line")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in requirements:
            raise ValueError("dependency lock contains a duplicate package")
        try:
            Version(match[2])
        except InvalidVersion:
            raise ValueError("dependency lock contains an invalid version") from None
        requirements[name] = match[2]
    if not requirements:
        raise ValueError("dependency lock must not be empty")
    return "".join(f"{name}=={version}\n" for name, version in sorted(requirements.items()))


def safe_export(raw: bytes, destination: Path) -> None:
    """Extract regular committed files, rejecting traversal and links."""
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for entry in archive:
            relative = Path(entry.name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("source archive contains an unsafe path")
            target = destination / relative
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not entry.isfile():
                raise ValueError("study source archive requires regular files")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(entry)
            if source is None:
                raise ValueError("source archive member has no content")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if entry.mode & 0o111 else 0o644)
            os.utime(target, (entry.mtime, entry.mtime))


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("study kit must not contain links")
        if path.is_file() and path != root / "SHA256SUMS":
            result[path.relative_to(root).as_posix()] = sha256(path)
    return result


def write_inventory(root: Path) -> dict[str, str]:
    files = inventory(root)
    (root / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in files.items()), encoding="utf-8"
    )
    return files


def verify_inventory(root: Path) -> dict[str, str]:
    expected = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[a-f0-9]{64}", digest) or name in expected:
            raise ValueError("invalid study inventory")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name == "SHA256SUMS":
            raise ValueError("invalid study inventory path")
        expected[name] = digest
    if not expected or inventory(root) != expected:
        raise ValueError("study inventory does not match the exact kit files")
    return expected


def _run(args: list[str], *, cwd: Path, env: dict | None = None) -> bytes:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=240)
    if result.returncode:
        raise RuntimeError(f"study preparation command failed: {args[0]}\n" +
                           (result.stdout + result.stderr).decode("utf-8", errors="replace")[-4000:])
    return result.stdout


def _build_wheel(export: Path, destination: Path, epoch: str, log: Path) -> Path:
    environment = {key: value for key, value in os.environ.items()
                   if key in {"PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG"}}
    environment.update({"SOURCE_DATE_EPOCH": epoch, "PYTHONNOUSERSITE": "1",
                        "PIP_NO_INDEX": "1", "PYTHONPATH": str(export)})
    result = subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--wheel", "--outdir", str(destination)],
        cwd=export, env=environment, capture_output=True, timeout=240,
    )
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("clean source wheel build failed; inspect retained build log")
    wheels = list(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("source build must produce exactly one wheel")
    return wheels[0]


def _wheel_metadata(path: Path) -> email.message.Message:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("study wheel must contain one package identity")
        metadata = email.message_from_bytes(archive.read(names[0]))
    if metadata["Name"] != "gex-terminal":
        raise ValueError("study wheel must be gex-terminal")
    return metadata


def _check_lock(metadata: email.message.Message, lock: str) -> None:
    pins = dict(line.split("==", 1) for line in lock.splitlines())
    if "gex-terminal" in pins and pins["gex-terminal"] != metadata["Version"]:
        raise ValueError("dependency lock application version differs from study wheel")
    for dependency in metadata.get_all("Requires-Dist", []):
        requirement = Requirement(dependency)
        # Provider extras are outside this offline kit. Evaluate any normal
        # Python/platform marker for the declared build/rehearsal runtime.
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = re.sub(r"[-_.]+", "-", requirement.name).lower()
        if name not in pins:
            raise ValueError("dependency lock does not cover the wheel's direct dependencies")
        if not requirement.specifier.contains(pins[name], prereleases=True):
            raise ValueError("dependency lock pin conflicts with a wheel dependency")


# Run this in the exported source so fixtures use exactly the frozen writer and
# catalog, rather than importing whichever checkout invoked this helper.
_CAPTURE_SCRIPT = r'''
import asyncio, hashlib, json, sys
from datetime import datetime
from pathlib import Path
from gex_terminal.replay_catalog import replay_session_for_name
from gex_terminal.session_capture import CapturedSessionWriter, inspect_captured_session

async def prepare(root):
    output = []
    for name in ("zero-gamma-flip", "nq-research-loop"):
        session = replay_session_for_name(name)
        raw = Path(session.path).read_bytes()
        messages = [json.loads(line) for line in raw.splitlines() if line.strip()]
        when = [datetime.fromisoformat((message.get("event_time") or message["timestamp"]).replace("Z", "+00:00")) for message in messages]
        current = [when[0]]
        target = root / (name + ".gex-session.jsonl")
        writer = CapturedSessionWriter(target, source={
            "name": "bundled-study-fixture", "provider": "synthetic", "mode": "replay", "symbol": session.symbol,
            "source_ref": session.source_ref, "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_kind": session.source_kind, "rights_status": session.rights_status,
            "redistributable": session.redistributable,
        }, model_inputs={"symbol": session.symbol, "contract_multiplier": session.contract_multiplier,
                         "risk_free_rate": 0.045, "days_to_expiry": 0.25, "expiry_filter": "all"},
        label="Synthetic study fixture: " + name,
        clock=lambda: current[0], monotonic_ns=lambda: 0)
        await writer.start()
        for message, timestamp in zip(messages, when):
            current[0] = timestamp
            await writer.append(message)
        await writer.finalize()
        verified = inspect_captured_session(target)
        output.append({"name": name, "symbol": session.symbol,
            "contract_multiplier": session.contract_multiplier,
            "source_ref": session.source_ref, "source_kind": session.source_kind,
            "rights_status": session.rights_status, "redistributable": session.redistributable,
            "replay_path": "gex_terminal/data/replays/" + Path(session.path).name,
            "replay_sha256": hashlib.sha256(raw).hexdigest(),
            "capture_path": "fixtures/" + target.name,
            "capture_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "content_sha256": verified["content_sha256"], "event_count": verified["event_count"],
            "first_as_of": verified["first_event_time"], "last_as_of": verified["last_event_time"],
            "selected_checkpoint": len(messages)-1, "event_time_fallback_count": verified["event_time_fallback_count"]})
    print(json.dumps(output, sort_keys=True))
asyncio.run(prepare(Path(sys.argv[1])))
'''


def _prepare_fixtures(export: Path, destination: Path) -> list[dict]:
    destination.mkdir()
    environment = {key: value for key, value in os.environ.items()
                   if key in {"PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG"}}
    environment.update({"PYTHONPATH": str(export), "PYTHONNOUSERSITE": "1"})
    return json.loads(_run([sys.executable, "-c", _CAPTURE_SCRIPT, str(destination)],
                           cwd=export, env=environment))


def rehearsal_record(path: Path, commit: str, wheel_hash: str) -> dict:
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("rehearsal record exceeds 2 MiB")
    report = json.loads(raw)
    if not isinstance(report, dict) or report.get("schema") != "gex-terminal.study-rehearsal.v1":
        raise ValueError("unsupported rehearsal record schema")
    if report.get("source_commit") != commit or report.get("wheel_sha256") != wheel_hash:
        raise ValueError("rehearsal record does not identify the exact source and wheel")
    if type(report.get("participant_sessions")) is not int or report["participant_sessions"] != 0:
        raise ValueError("automated rehearsal must not contain participant observations")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("rehearsal record must declare executed checks")
    for check in checks:
        if (not isinstance(check, dict) or not isinstance(check.get("name"), str)
                or not check["name"].strip() or check.get("status") not in {"passed", "failed", "not_run"}):
            raise ValueError("rehearsal check requires a name and explicit outcome")
    return report


def prepare(repo: Path, commit: str, study_id: str, lock_path: Path, output_root: Path,
            rehearsal_path: Path | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{3,79}", study_id):
        raise ValueError("study ID requires 4-80 lowercase letters, digits or hyphens")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("freeze an explicit full reviewed commit SHA")
    target = output_root / study_id
    zip_target = output_root / f"{study_id}.zip"
    checksum_target = zip_target.with_suffix(".zip.sha256")
    if any(path.exists() or path.is_symlink() for path in (target, zip_target, checksum_target)):
        raise FileExistsError("study identity already exists; use a new cohort ID")
    lock = pinned_requirements(lock_path.read_text(encoding="utf-8"))
    actual = _run(["git", "rev-parse", f"{commit}^{{commit}}"], cwd=repo).decode().strip()
    tree = _run(["git", "rev-parse", f"{commit}^{{tree}}"], cwd=repo).decode().strip()
    if actual != commit:
        raise ValueError("source commit identity mismatch")
    epoch = _run(["git", "show", "-s", "--format=%ct", commit], cwd=repo).decode().strip()
    source_archive = _run(["git", "archive", "--format=tar", commit], cwd=repo)
    output_root.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700)  # Reserve identity before any expensive work.
    try:
        with tempfile.TemporaryDirectory(prefix="gex-study-export-") as scratch:
            scratch_path = Path(scratch)
            exports = [scratch_path / "first-source", scratch_path / "second-source"]
            for export in exports:
                export.mkdir()
                safe_export(source_archive, export)
            source = exports[0]
            project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            rehearsal = target / "rehearsal"
            rehearsal.mkdir()
            wheels = [_build_wheel(export, scratch_path / f"wheel-{index}", epoch,
                                   rehearsal / f"build-{index}.log")
                      for index, export in enumerate(exports, start=1)]
            hashes = [sha256(wheel) for wheel in wheels]
            if hashes[0] != hashes[1] or wheels[0].name != wheels[1].name:
                raise ValueError("independent clean exports produced different wheel bytes")
            metadata = _wheel_metadata(wheels[0])
            if metadata["Version"] != project["version"]:
                raise ValueError("wheel version differs from committed source")
            _check_lock(metadata, lock)
            shutil.copyfile(wheels[0], target / wheels[0].name)
            (target / "source.tar").write_bytes(source_archive)
            (target / "requirements-lock.txt").write_text(lock, encoding="utf-8")
            materials = target / "materials"
            shutil.copytree(source / "docs", materials / "docs")
            for name in ("README.md", "LICENSE", "CONTRIBUTING.md", "ROADMAP.md"):
                shutil.copyfile(source / name, materials / name)
            fixtures = _prepare_fixtures(source, target / "fixtures")
            template_root = source / "docs" / "study-kit"
            for name in ("participant-guide.md", "moderator-guide.md", "scorecard.csv", "protocol.json"):
                if name.endswith(".md"):
                    content = (template_root / name).read_text(encoding="utf-8")
                    content = (content.replace("](../", "](materials/docs/")
                               .replace("@WHEEL_FILENAME@", wheels[0].name)
                               .replace("@APPLICATION_VERSION@", project["version"]))
                    (target / name).write_text(content, encoding="utf-8")
                else:
                    shutil.copyfile(template_root / name, target / name)
            protocol = json.loads((target / "protocol.json").read_text(encoding="utf-8"))
            if protocol.get("protocol_id") != PROTOCOL or tuple(task["id"] for task in protocol["tasks"]) != TASK_IDS:
                raise ValueError("study protocol identity or task IDs differ from the build recipe")
            tools = {}
            for name in ("build", "setuptools", "wheel"):
                tools[name] = importlib.metadata.version(name)
            rehearsal_status = {"status": "build_and_capture_integrity_only", "participant_sessions": 0,
                                "installation": "not_run", "guided_browser_flow": "not_run",
                                "records": "rehearsal/; maintainer must freeze separate execution evidence before handoff"}
            if rehearsal_path is not None:
                report = rehearsal_record(rehearsal_path, commit, hashes[0])
                shutil.copyfile(rehearsal_path, rehearsal / "execution.json")
                rehearsal_status = {"status": "maintainer_recorded_automated_rehearsal", "participant_sessions": 0,
                                    "path": "rehearsal/execution.json", "sha256": sha256(rehearsal / "execution.json"),
                                    "checks": report["checks"],
                                    "limits": "provided execution record; builder validates identity, not the truth of reported observations"}
            manifest = {
                "schema": SCHEMA, "study_id": study_id, "protocol_id": PROTOCOL,
                "source_commit": commit, "source_tree": tree, "source_date_epoch": int(epoch),
                "application_version": project["version"],
                "wheel": {"path": wheels[0].name, "sha256": hashes[0], "independent_build_sha256": hashes[1]},
                "source_archive": {"path": "source.tar", "sha256": sha256(target / "source.tar")},
                "dependency_lock": {"path": "requirements-lock.txt", "sha256": sha256(target / "requirements-lock.txt"),
                                    "status": "provided exact version constraints; installation not verified by builder"},
                "build_environment": {"python": platform.python_version(), "os": platform.system(),
                                      "os_version": platform.release(), "architecture": platform.machine(), "tools": tools},
                "fixtures": fixtures, "task_ids": list(TASK_IDS),
                "frozen_materials": {name: digest for name, digest in inventory(target).items()
                                     if name.startswith("materials/") or name in {"protocol.json", "participant-guide.md", "moderator-guide.md", "scorecard.csv"}},
                "rehearsal": rehearsal_status,
                "evidence_ceiling": "synthetic offline preparation; no participant results, live reliability or predictive-validity evidence",
            }
            (target / "build-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (target / "fixture-answer-key.json").write_text(json.dumps({"protocol_id": PROTOCOL, "fixtures": fixtures}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (rehearsal / "README.md").write_text(
                "# Automated preparation evidence\n\nTwo independent clean-source wheel builds and capture integrity checks completed.\n"
                "Installation, actual guided browser interaction and fresh-server receipt reproduction are not run by this builder.\n"
                + ("The maintainer's identity-bound execution record is frozen in execution.json.\n" if rehearsal_path else
                   "Retain their commands/outcomes separately before freezing the handoff.\n")
                + "Zero participants have been observed.\n",
                encoding="utf-8")
            (target / "HANDOFF.md").write_text(
                f"# {study_id}\n\nSource: `{commit}`; tree: `{tree}`; version: `{project['version']}`.\n\n"
                f"Wheel SHA-256: `{hashes[0]}`. Verify every file against `SHA256SUMS`.\n"
                "Checksums detect changed bytes; obtain the reviewed checksum through a trusted channel.\n\n"
                "Read `participant-guide.md`; the moderator retains `moderator-guide.md`, `protocol.json`, "
                "`fixture-answer-key.json` and the blank `scorecard.csv`. Consult `build-manifest.json` "
                "for the precise rehearsal status and any frozen execution record.\n\n"
                "Choose the owner-controlled observation retention/deletion date and obtain consent before recruitment. "
                "Keep identities and observations outside this bundle. This new cohort does not amend the September study.\n",
                encoding="utf-8")
            write_inventory(target)
            verify_inventory(target)
            with zipfile.ZipFile(zip_target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(target.rglob("*")):
                    if path.is_file():
                        archive.write(path, f"{study_id}/{path.relative_to(target).as_posix()}")
            with checksum_target.open("x", encoding="utf-8") as checksum:
                checksum.write(f"{sha256(zip_target)}  {zip_target.name}\n")
    except Exception:
        # Retain the reserved directory and any build logs after a failed build;
        # silently reusing a cohort identity would obscure failed preparation.
        (target / "PREPARATION_FAILED.txt").write_text("Preparation failed. Preserve this attempt and choose a new study ID for a corrected build.\n", encoding="utf-8")
        raise
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="full reviewed source commit SHA")
    parser.add_argument("--study-id", required=True, help="new cohort ID; existing targets are never reused")
    parser.add_argument("--requirements-lock", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("dist/study"))
    parser.add_argument("--rehearsal-record", type=Path, help="identity-bound automated execution JSON; never participant observations")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        target = prepare(args.repo.resolve(), args.commit, args.study_id,
                         args.requirements_lock.resolve(), args.output_root.resolve(),
                         args.rehearsal_record.resolve() if args.rehearsal_record else None)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Study kit preparation failed: {error}", file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

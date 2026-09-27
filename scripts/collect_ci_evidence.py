"""Stage only bounded, named synthetic CI outputs and an integrity manifest.

This is a maintainer tool, not a general workspace archiver or redaction tool.
Its input directory must belong to the disposable offline CI run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
CHECK_IDS = (
    "paths", "checkout", "python", "dependencies", "compile", "hygiene", "tests",
    "cli", "previews", "numerical", "distributions", "wheel", "lifecycle", "tag",
)
OUTCOMES = {"success", "failure", "cancelled", "skipped", "unknown"}
# No globs, recursion, logs, environment files, backups, or user research folders.
# The producer name explains absence when an earlier step failed or was skipped.
ARTIFACTS = {
    "previews/demo.svg": "previews",
    "previews/onboarding.svg": "previews",
    "previews/manifest.json": "previews",
    "gex-model-evidence.json": "numerical",
    "gex-wheel-doctor.json": "wheel",
    "gex-wheel-snapshot.json": "wheel",
    "gex-wheel-fixtures.json": "wheel",
    "gex-wheel-injection.json": "wheel",
    "gex-wheel-demo/manifest.json": "wheel",
    "gex-wheel-demo/review-receipt.json": "wheel",
    "gex-wheel-demo/replay_lab.json": "wheel",
    "gex-wheel-demo/terminal-screenshot.svg": "wheel",
    "gex-wheel-nq/manifest.json": "wheel",
    "gex-wheel-nq/review-receipt.json": "wheel",
    "gex-wheel-nq/replay_lab.json": "wheel",
    "gex-wheel-nq/terminal-screenshot.svg": "wheel",
    "gex-wheel-nq-reproduced/review-receipt.json": "wheel",
    "gex-wheel-support.json": "wheel",
    "gex-wheel-databento.json": "wheel",
    "gex-wheel-databento-cert.json": "wheel",
    "gex-wheel-price-action.json": "wheel",
    "gex-wheel-position.json": "wheel",
    "gex-wheel-properties.json": "wheel",
    "gex-wheel-faults.json": "wheel",
    "gex-wheel-performance.json": "wheel",
    "gex-wheel-experiment/manifest.json": "wheel",
    "gex-wheel-experiment/report.json": "wheel",
    "gex-wheel-reproduction/manifest.json": "wheel",
    "gex-wheel-reproduction/report.json": "wheel",
    "gex-wheel-batch.json": "wheel",
    "gex-wheel-corpus.json": "wheel",
    "gex-lifecycle.json": "lifecycle",
}
RUN_FIELDS = {
    "repository": "GITHUB_REPOSITORY", "workflow": "GITHUB_WORKFLOW",
    "id": "GITHUB_RUN_ID", "attempt": "GITHUB_RUN_ATTEMPT",
    "job": "GITHUB_JOB", "event": "GITHUB_EVENT_NAME",
    "ref": "GITHUB_REF", "event_sha": "GITHUB_SHA",
}


def source_identity(source_root: Path) -> dict:
    """Record commit and dirtiness, without filenames or command/error logs."""
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(source_root), *args], check=True,
            text=True, capture_output=True, timeout=10,
        ).stdout.strip()

    try:
        return {
            "commit": git("rev-parse", "HEAD"),
            "dirty_worktree": bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty_worktree": None}


def run_identity() -> dict:
    # Deliberately do not serialize os.environ, step outputs, or event payloads.
    def bounded(key: str) -> str | None:
        value = os.environ.get(key)
        if value is None:
            return None
        return value if len(value) <= 300 and value.isprintable() else "invalid"

    return {name: bounded(key) for name, key in RUN_FIELDS.items()}


def _read_artifact(root: Path, relative: str, remaining: int) -> tuple[bytes | None, str]:
    path = root
    try:
        for component in Path(relative).parts:
            path = path / component
            if path.is_symlink():
                return None, "rejected_symlink"
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return None, "rejected_nonregular"
        if info.st_size > MAX_FILE_BYTES:
            return None, "rejected_file_limit"
        if info.st_size > remaining:
            return None, "rejected_total_limit"
        # Bound the read too: a file growing after stat cannot bypass the cap.
        with path.open("rb") as stream:
            data = stream.read(min(MAX_FILE_BYTES, remaining) + 1)
        if len(data) > MAX_FILE_BYTES:
            return None, "rejected_file_limit"
        if len(data) > remaining:
            return None, "rejected_total_limit"
        if not data:
            return None, "rejected_empty"
        return data, "retained"
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "read_error"


def collect(input_root: Path, output_dir: Path, source_root: Path, outcomes: dict) -> dict:
    if not isinstance(outcomes, dict) or set(outcomes) - set(CHECK_IDS):
        raise ValueError("step outcomes must contain only known CI check identifiers")
    if any(not isinstance(value, str) or value not in OUTCOMES for value in outcomes.values()):
        raise ValueError("step outcomes must use success/failure/cancelled/skipped/unknown")
    if input_root.is_symlink():
        raise ValueError("input root must not be a symlink")
    input_root = input_root.resolve()
    output_dir = output_dir.absolute()
    if output_dir.resolve().is_relative_to(input_root):
        raise ValueError("evidence staging must be outside the input directory")
    # Exclusive staging prevents stale reports or an unrelated existing file
    # from being included by the later directory upload.
    output_dir.mkdir(parents=True, exist_ok=False)
    checks = {name: outcomes.get(name, "unknown") for name in CHECK_IDS}
    entries = []
    total = 0
    for relative, producer in ARTIFACTS.items():
        data, status = _read_artifact(input_root, relative, MAX_TOTAL_BYTES - total)
        entry = {"path": relative, "producer": producer,
                 "producer_outcome": checks[producer], "status": status}
        if data is not None:
            destination = output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            entry.update({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            total += len(data)
        entries.append(entry)
    summary = {
        "expected_files": len(entries),
        "retained_files": sum(item["status"] == "retained" for item in entries),
        "missing_files": sum(item["status"] == "missing" for item in entries),
        "rejected_files": sum(item["status"] not in {"retained", "missing"} for item in entries),
        "retained_bytes": total,
        "collection_complete": all(item["status"] == "retained" for item in entries),
        "failed_checks": [name for name, outcome in checks.items() if outcome == "failure"],
        "cancelled_checks": [name for name, outcome in checks.items() if outcome == "cancelled"],
        "skipped_checks": [name for name, outcome in checks.items() if outcome == "skipped"],
        "unknown_checks": [name for name, outcome in checks.items() if outcome == "unknown"],
    }
    manifest = {
        "schema": "gex-terminal.ci-evidence.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_identity(source_root),
        "run": run_identity(),
        "runtime": {"platform": platform.system(), "machine": platform.machine(),
                    "python": platform.python_version()},
        "limits": {"per_file_bytes": MAX_FILE_BYTES, "total_file_bytes": MAX_TOTAL_BYTES},
        "checks": checks, "summary": summary, "artifacts": entries,
        "evidence_ceiling": (
            "synthetic offline software and disposable installation checks only; "
            "no participant, live-provider, predictive-validity or platform-support claim; "
            "retained subsets are not complete portable research packs"
        ),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--step-outcomes", default="{}", help="JSON map of known check IDs to outcomes")
    parser.add_argument("--github-output", type=Path, help="GitHub step output file for the safe staging marker")
    args = parser.parse_args()
    try:
        manifest = collect(args.input_root, args.output_dir, args.source_root, json.loads(args.step_outcomes))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.github_output is not None:
        # Upload only after this invocation exclusively created its staging
        # directory and completed its manifest, including partial collections.
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("staged=true\n")
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0 if manifest["summary"]["collection_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

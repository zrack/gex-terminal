"""Prepare a participant-only delivery from an unchanged frozen study kit.

No dependencies are installed and no PDF is generated here. Supply a separately
reviewed blank consent PDF; rendering/form checks remain a separate preparation
step. Generated deliveries and completed records belong outside source control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import unquote, urlsplit
import zipfile

try:
    from scripts.build_study_kit import verify_inventory, write_inventory
except ModuleNotFoundError:  # Direct ``python scripts/build_participant_delivery.py``.
    from build_study_kit import verify_inventory, write_inventory


COHORT = "guided-intake-2026-10-18-r1"
DELIVERY = COHORT + "-participant-v1"
TEMPLATES = Path(__file__).resolve().parents[1] / "docs/study-kit/recruitment"
HELP = (
    "first-run.md", "wind-tunnel.md", "demo-lab.md", "doctor.md",
    "model-assumptions.md", "model-comparison.md", "captured-sessions.md",
    "capture-governance.md", "local-support.md",
)
RECRUITER = (
    "START-HERE.md", "invitation.txt", "scheduling-confirmation.txt", "reminder.txt",
    "session-plan.csv", "organizer-checklist.md", "consent-template.txt",
)
LINK = re.compile(r'(!?)\[([^\]]*)\]\(([^\s)]+)(?:\s+"[^"]*")?\)')
INTERNAL = ("answer-key", "moderator", "scorecard", "rehearsal", "work-packet")
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")
DIGEST = re.compile(r"[a-f0-9]{64}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("delivery requires safe relative file paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("delivery requires safe relative file paths")
    if ":" in value or any(ord(char) < 32 for char in value):
        raise ValueError("delivery requires safe relative file paths")
    return value


def regular(root: Path, relative: str) -> Path:
    relative_path(relative)
    current = root
    if root.is_symlink() or not root.is_dir():
        raise ValueError("delivery source must be a regular directory")
    for part in PurePosixPath(relative).parts:
        current = current / part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError("delivery sources must not contain links or special files")
    if not current.is_file():
        raise ValueError("delivery source must be a regular file")
    return current


def tree_files(root: Path) -> set[str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("delivery requires a regular directory")
    files = set()
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError("delivery must not contain links or special files")
        if stat.S_ISREG(mode):
            files.add(relative_path(path.relative_to(root).as_posix()))
    return files


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def _public_environment(raw: dict) -> dict:
    result = {key: raw[key] for key in ("architecture", "os", "os_version", "python")}
    result["tools"] = {key: raw["tools"][key] for key in ("build", "setuptools", "wheel")}
    for value in (*[result[key] for key in result if key != "tools"], *result["tools"].values()):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.+ -]{1,80}", value):
            raise ValueError("invalid public build environment")
    return result


def parent_manifest(frozen: Path) -> tuple[dict, dict[str, str]]:
    tree_files(frozen)
    inventory = verify_inventory(frozen)
    parent = json.loads(regular(frozen, "build-manifest.json").read_text(encoding="utf-8"))
    if parent.get("schema") != "gex-terminal.study-kit.v1" or parent.get("protocol_id") != "guided-intake-v1":
        raise ValueError("delivery requires the frozen guided-intake-v1 protocol")
    if not isinstance(parent.get("study_id"), str) or not ID.fullmatch(parent["study_id"]):
        raise ValueError("invalid study identity")
    for key in ("source_commit", "source_tree"):
        if not isinstance(parent.get(key), str) or not re.fullmatch(r"[a-f0-9]{40}", parent[key]):
            raise ValueError("invalid frozen source identity")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?", parent["application_version"]):
        raise ValueError("invalid application version")
    for item in (parent["wheel"], parent["dependency_lock"]):
        name = relative_path(item["path"])
        if not isinstance(item.get("sha256"), str) or not DIGEST.fullmatch(item["sha256"]) or inventory.get(name) != item["sha256"]:
            raise ValueError("frozen artifact identity differs from inventory")
    if "/" in parent["wheel"]["path"] or not parent["wheel"]["path"].endswith(".whl") or parent["dependency_lock"]["path"] != "requirements-lock.txt":
        raise ValueError("unexpected frozen wheel or lock path")
    expected = {"zero-gamma-flip": ("ES", 50), "nq-research-loop": ("NQ", 20)}
    fixtures = parent["fixtures"]
    if len(fixtures) != 2 or {item["name"] for item in fixtures} != set(expected):
        raise ValueError("delivery requires the two declared synthetic fixtures")
    for item in fixtures:
        name = item["name"]
        capture = relative_path(item["capture_path"])
        if (capture != f"fixtures/{name}.gex-session.jsonl" or
                (item["symbol"], item["contract_multiplier"]) != expected[name] or
                item.get("redistributable") is not True or item.get("rights_status") != "owned" or
                item.get("source_kind") != "synthetic_fixture" or item.get("source_ref") != f"bundled:{name}" or
                not DIGEST.fullmatch(item.get("content_sha256", "")) or
                inventory.get(capture) != item.get("capture_sha256")):
            raise ValueError("invalid frozen synthetic fixture identity")
    _public_environment(parent["build_environment"])
    return parent, inventory


def render_help(text: str, relative: str) -> tuple[str, list[dict]]:
    allowed = {f"materials/docs/{name}" for name in HELP}
    removed = []

    def render(match: re.Match) -> str:
        image, label, target = match.groups()
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto"} or target.startswith("#"):
            return match.group(0)
        if parsed.scheme or parsed.netloc or "\\" in target:
            raise ValueError("unsupported user-help link")
        parts = list(PurePosixPath(relative).parent.parts)
        for part in unquote(parsed.path).split("/"):
            if part == "..":
                if not parts:
                    raise ValueError("user-help link escapes delivery")
                parts.pop()
            elif part not in {"", "."}:
                parts.append(part)
        if parsed.path.startswith("/"):
            raise ValueError("user-help link escapes delivery")
        if "/".join(parts) in allowed:
            return match.group(0)
        removed.append({"label": label, "target": target})
        return label

    return LINK.sub(render, text), removed


def expected_files(parent: dict) -> set[str]:
    return {
        parent["wheel"]["path"], "requirements-lock.txt", "participant-guide.md",
        "materials/LICENSE", "START-HERE.txt", "build-manifest.json", "consent.pdf",
        "consent.txt", "SHA256SUMS",
        *[item["capture_path"] for item in parent["fixtures"]],
        *[f"materials/docs/{name}" for name in HELP],
    }


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(source.read_bytes())


def _wheel_safety(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set()
        for info in archive.infolist():
            name = relative_path(info.filename.rstrip("/"))
            mode = info.external_attr >> 16
            if name in names or stat.S_ISLNK(mode) or any(word in name.lower() for word in INTERNAL):
                raise ValueError("wheel contains unsafe or excluded internal material")
            names.add(name)


def anchors(text: str) -> set[str]:
    result: set[str] = set()
    duplicates: dict[str, int] = {}
    fence = None
    for line in text.splitlines():
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if delimiter:
            if fence is None:
                fence = delimiter[1][0]
            elif delimiter[1][0] == fence:
                fence = None
            continue
        if fence is not None or not re.match(r"^#{1,6}\s+", line):
            continue
        heading = re.sub(r"^#{1,6}\s+", "", line).strip().lower()
        heading = re.sub(r"\s+#+$", "", heading)
        heading = re.sub(r"<[^>]+>", "", heading)
        slug = re.sub(r"[^\w\-\s]", "", heading).replace(" ", "-")
        count = duplicates.get(slug, 0)
        duplicates[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


def verify_links(root: Path, files: set[str]) -> int:
    checked = 0
    for name in sorted(files):
        if not name.endswith(".md"):
            continue
        for match in LINK.finditer((root / name).read_text(encoding="utf-8")):
            target = match[3]
            parsed = urlsplit(target)
            if parsed.scheme in {"http", "https", "mailto"}:
                continue
            if parsed.scheme or parsed.netloc:
                raise ValueError("unsupported participant link")
            path = (((root / name).parent / unquote(parsed.path)) if parsed.path else root / name).resolve()
            try:
                relative = path.relative_to(root.resolve()).as_posix()
            except ValueError:
                raise ValueError("participant link escapes delivery") from None
            if relative not in files:
                raise ValueError("broken participant local link")
            if (parsed.fragment and path.suffix == ".md" and
                    unquote(parsed.fragment) not in anchors(path.read_text(encoding="utf-8"))):
                raise ValueError("broken participant local anchor")
            checked += 1
    return checked


def public_manifest(parent: dict, delivery_id: str, guide_sha256: str) -> dict:
    fixture_keys = ("name", "symbol", "contract_multiplier", "capture_path", "capture_sha256",
                    "content_sha256", "source_kind", "source_ref", "redistributable", "rights_status")
    return {"schema": "gex-terminal.participant-build.v1", "study_id": parent["study_id"],
              "delivery_id": delivery_id, "parent_protocol_id": "guided-intake-v1",
              **{key: parent[key] for key in ("source_commit", "source_tree", "application_version")},
              "build_environment": _public_environment(parent["build_environment"]),
              "wheel": {key: parent["wheel"][key] for key in ("path", "sha256")},
              "dependency_lock": {**{key: parent["dependency_lock"][key] for key in ("path", "sha256")},
                                  "note": "Exact version constraints; dependency downloads may require internet."},
              "fixtures": [{key: value for key, value in item.items() if key in fixture_keys} for item in parent["fixtures"]],
              "participant_guide": {"path": "participant-guide.md", "sha256": guide_sha256},
              "help_delivery": "Included user-help copies retain shipped prose. Links to omitted maintainer/study documents are displayed as plain text.",
              "evidence_ceiling": "Synthetic offline exercise; no live provider access, trading or predictive validity is established."}


def verify_delivery(frozen: Path, output: Path) -> dict:
    parent, _ = parent_manifest(frozen)
    participant = output / "participant"
    actual = tree_files(participant)
    if actual != expected_files(parent):
        raise ValueError("participant delivery has missing or unexpected files")
    verify_inventory(participant)
    public = json.loads((participant / "build-manifest.json").read_text())
    amendment = json.loads((output / "delivery-amendment.json").read_text())
    delivery_id = public.get("delivery_id", "")
    if (not isinstance(delivery_id, str) or not ID.fullmatch(delivery_id) or
            parent["study_id"] != COHORT or delivery_id != DELIVERY or
            public != public_manifest(parent, delivery_id, sha(frozen / "participant-guide.md"))):
        raise ValueError("public identity differs from frozen study")
    required_copies = {parent["wheel"]["path"], "requirements-lock.txt", "participant-guide.md",
                       "materials/LICENSE", *[item["capture_path"] for item in parent["fixtures"]]}
    if (set(amendment["unchanged_files"]) != required_copies or
            amendment.get("study_id") != parent["study_id"] or
            amendment.get("delivery_id") != delivery_id or
            type(amendment.get("observations_at_amendment")) is not int or
            amendment["observations_at_amendment"] != 0 or
            len(amendment["derived_help"]) != len(HELP) or
            {item["path"] for item in amendment["derived_help"]} != {f"materials/docs/{name}" for name in HELP}):
        raise ValueError("delivery amendment does not match its declared exact materials")
    for name, digest in amendment["unchanged_files"].items():
        relative_path(name)
        if sha(regular(frozen, name)) != digest or sha(regular(participant, name)) != digest:
            raise ValueError("exact frozen copy identity differs")
    for item in amendment["derived_help"]:
        name = relative_path(item["path"])
        rendered, removed = render_help(regular(frozen, name).read_text(), name)
        if (regular(participant, name).read_text() != rendered or
                item["links_rendered_as_text"] != removed or sha(frozen / name) != item["frozen_sha256"] or
                sha(participant / name) != item["participant_sha256"]):
            raise ValueError("derived help differs from its amendment")
    for name in actual:
        if name.endswith((".md", ".txt", ".json")):
            if re.search(r"/Users/|/private/(?:tmp|var)/|file://", (participant / name).read_text()):
                raise ValueError("private maintainer path in participant text")
    checked_links = verify_links(participant, actual)
    _wheel_safety(participant / parent["wheel"]["path"])
    return {"status": "passed", "study_id": parent["study_id"], "delivery_id": public["delivery_id"],
            "participant_files": len(actual), "relative_markdown_links_checked": checked_links,
            "exact_copies": len(amendment["unchanged_files"]),
            "help_pages": len(HELP), "participant_sessions": 0}


def _zip(root: Path, destination: Path) -> str:
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(tree_files(root)):
            # Stable ZIP metadata keeps the same inputs reproducible.
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, (root / name).read_bytes())
    digest = sha(destination)
    with destination.with_suffix(destination.suffix + ".sha256").open("x") as output:
        output.write(f"{digest}  {destination.name}\n")
    return digest


def build(frozen_kit: Path, output: Path, consent_pdf: Path, delivery_id: str,
          *, templates: Path = TEMPLATES) -> dict:
    if not ID.fullmatch(delivery_id):
        raise ValueError("invalid delivery identity")
    resolved_output = output.resolve()
    if any(resolved_output.is_relative_to(source.resolve()) for source in (frozen_kit, templates)):
        raise ValueError("delivery output must remain outside frozen inputs and template sources")
    parent, _ = parent_manifest(frozen_kit)
    if parent["study_id"] != COHORT or delivery_id != DELIVERY:
        raise ValueError("blank consent/templates support only the October guided-intake cohort and participant-v1; a new cohort or revision requires a reviewed template and PDF amendment")
    for name in (*RECRUITER, "participant-start.txt"):
        regular(templates, name)
    if consent_pdf.is_symlink() or not stat.S_ISREG(consent_pdf.lstat().st_mode) or not consent_pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("supply a separately reviewed blank consent PDF")
    _wheel_safety(frozen_kit / parent["wheel"]["path"])
    if output.exists() or output.is_symlink():
        raise FileExistsError("delivery output already exists; choose a new identity")
    for ancestor in output.parents:
        if ancestor.is_symlink():
            raise ValueError("delivery output must not use linked directories")
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    participant = output / "participant"
    participant.mkdir()
    unchanged = [parent["wheel"]["path"], "requirements-lock.txt", "participant-guide.md",
                 "materials/LICENSE", *[item["capture_path"] for item in parent["fixtures"]]]
    for name in unchanged:
        _copy(regular(frozen_kit, name), participant / name)
    transformations = []
    for name in HELP:
        relative = f"materials/docs/{name}"
        source = regular(frozen_kit, relative)
        rendered, removed = render_help(source.read_text(encoding="utf-8"), relative)
        target = participant / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="") as stream:
            stream.write(rendered)
        transformations.append({"path": relative, "frozen_sha256": sha(source),
                                "participant_sha256": sha(target), "links_rendered_as_text": removed})
    public = public_manifest(parent, delivery_id, sha(participant / "participant-guide.md"))
    write_json(participant / "build-manifest.json", public)
    start = regular(templates, "participant-start.txt").read_text(encoding="utf-8")
    start = re.sub(r"^Study: .*$", "Study: " + parent["study_id"], start, flags=re.MULTILINE)
    start = re.sub(r"^Delivery: .*$", "Delivery: " + delivery_id, start, flags=re.MULTILINE)
    start = start.replace("gex_terminal-0.6.0-py3-none-any.whl", parent["wheel"]["path"])
    (participant / "START-HERE.txt").write_text(start, encoding="utf-8")
    _copy(consent_pdf, participant / "consent.pdf")
    _copy(regular(templates, "consent-template.txt"), participant / "consent.txt")
    write_inventory(participant)
    amendment = {"schema": "gex-terminal.participant-delivery-amendment.v1",
                 "study_id": parent["study_id"], "delivery_id": delivery_id,
                 "frozen_kit_modified": False, "observations_at_amendment": 0,
                 "use_for_all_six_sessions": True,
                 "unchanged_files": {name: sha(participant / name) for name in unchanged},
                 "derived_help": transformations,
                 "limits": "Delivery amendment only; application, fixtures, task text and scoring remain unchanged. No participant outcomes are established.",
                 "consent_pdf": {"sha256": sha(consent_pdf), "validation": "supplied separately; PDF form/content review is not performed by this builder"},
                 "template_sha256": {name: sha(templates / name) for name in (*RECRUITER, "participant-start.txt")}}
    write_json(output / "delivery-amendment.json", amendment)
    recruiter = output / "recruiter"
    recruiter.mkdir()
    for name in RECRUITER:
        source = regular(templates, name)
        if name == "session-plan.csv":
            # Preserve the reviewed organizer CSV delivery while keeping LF source.
            text = source.read_text(encoding="utf-8")
            with (recruiter / name).open("x", encoding="utf-8", newline="") as stream:
                stream.write(text.replace("\n", "\r\n"))
        else:
            _copy(source, recruiter / name)
    _copy(consent_pdf, recruiter / "consent-template.pdf")
    write_inventory(recruiter)
    report = verify_delivery(frozen_kit, output)
    report["archives"] = {name: _zip(root, output / name) for name, root in (
        ("gex-participant-package.zip", participant), ("gex-organizer-pack.zip", recruiter))}
    report["frozen_inventory_sha256"] = sha(frozen_kit / "SHA256SUMS")
    write_json(output / "summary.json", report)
    write_inventory(output)
    verify_inventory(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-kit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--consent-pdf", type=Path, required=True)
    parser.add_argument("--delivery-id", required=True)
    args = parser.parse_args()
    try:
        report = build(args.frozen_kit, args.output, args.consent_pdf, args.delivery_id)
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Participant delivery preparation failed: {error}\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

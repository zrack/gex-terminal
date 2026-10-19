"""Install a reviewed local wheel and create an activation-free offline launcher.

Uses Python's standard library. Application dependencies may be downloaded unless
--wheelhouse is supplied. Existing research and unowned destinations are kept.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import email
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import venv
import zipfile


OWNER = ".gex-owner.json"
RECEIPT = "installation.json"
SCHEMA = "gex-terminal.local-install.v1"
SESSION = "zero-gamma-flip"
LAUNCH_FILES = ("launcher.py", "run-gex", "Start GEX.command")
WIND_LAUNCH_FILES = ("run-wind-tunnel", "Start Wind Tunnel.command")
STARTER_LAUNCH_FILES = ("Start Terminal.command",)
BOOTSTRAP = (
    "import os,runpy,sys; import gex_terminal.config; "
    "os.chdir(sys.argv.pop(1)); runpy.run_module('gex_terminal.cli',run_name='__main__')"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_environment() -> dict[str, str]:
    result = {key: value for key, value in os.environ.items() if key in {
        "PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE",
        "TERM", "COLORTERM", "NO_COLOR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
    }}
    result.update({"PYTHONNOUSERSITE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                   "PIP_CONFIG_FILE": os.devnull})
    return result


def wheel_identity(wheel: Path, expected_sha256: str, source_commit: str) -> dict:
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("Expected wheel SHA-256 must contain 64 hexadecimal characters.")
    if not re.fullmatch(r"[a-fA-F0-9]{40}", source_commit):
        raise ValueError("Source commit must be the full 40-character Git commit supplied with the wheel.")
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise ValueError("Choose the reviewed .whl file supplied with this installer.")
    actual = digest(wheel)
    if actual != expected_sha256.lower():
        raise ValueError("Wheel checksum does not match. Installation has not started.")
    try:
        with zipfile.ZipFile(wheel) as archive:
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError("Wheel contains duplicate file entries.")
            records = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(records) != 1:
                raise ValueError("Wheel must contain exactly one package metadata record.")
            metadata = email.message_from_bytes(archive.read(records[0]))
            payload = {}
            for member in archive.infolist():
                if not member.filename.startswith("gex_terminal/") or member.is_dir():
                    continue
                if ".." in Path(member.filename).parts or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Wheel application payload contains an unsafe file path.")
                payload[member.filename] = hashlib.sha256(archive.read(member)).hexdigest()
    except zipfile.BadZipFile as exc:
        raise ValueError("The supplied wheel is not a valid wheel archive.") from exc
    if str(metadata.get("Name", "")).lower().replace("_", "-") != "gex-terminal":
        raise ValueError("This installer accepts only gex-terminal wheels.")
    version = str(metadata.get("Version", ""))
    if not version or len(version) > 100 or not version.isprintable():
        raise ValueError("Wheel version metadata is invalid.")
    if "gex_terminal/__init__.py" not in payload:
        raise ValueError("Wheel application payload is missing.")
    return {"wheel_name": wheel.name, "wheel_sha256": actual,
            "source_commit": source_commit.lower(), "version": version,
            "payload_sha256": payload}


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected an ordinary installer-owned file: {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid installer record: {path.name}")
    return data


def owned_target(target: Path) -> dict | None:
    if target.is_symlink():
        raise ValueError("Application folder must not be a symlink.")
    if not target.exists():
        return None
    if not target.is_dir():
        raise ValueError("Application destination is not a folder.")
    try:
        owner = read_json(target / OWNER)
    except (OSError, ValueError) as exc:
        raise ValueError("Application folder already exists and is not owned by this installer. Choose a new folder.") from exc
    if owner.get("schema") != SCHEMA or owner.get("root") != str(target.resolve()):
        raise ValueError("Application folder identity does not match. Choose a new installation folder.")
    receipt_path = target / RECEIPT
    if not receipt_path.exists() and not receipt_path.is_symlink():
        if any((target / name).exists() or (target / name).is_symlink()
               for name in (*LAUNCH_FILES, *WIND_LAUNCH_FILES, *STARTER_LAUNCH_FILES)):
            raise ValueError("Incomplete installation has published launcher files. Choose a new application folder to preserve them.")
        # An owned preparation that failed before launcher publication may be
        # retried; its failed environment and unrelated files remain untouched.
        return {}
    receipt = read_json(receipt_path)
    active = receipt.get("active")
    research = receipt.get("research_dir")
    hashes = receipt.get("launcher_sha256")
    if (receipt.get("schema") != SCHEMA or receipt.get("root") != str(target.resolve())
            or not isinstance(active, dict) or not isinstance(research, str)
            or not Path(research).is_absolute() or not isinstance(hashes, dict)):
        raise ValueError("Installation receipt is invalid. Choose a new application folder to preserve this state.")
    if (not isinstance(active.get("version"), str) or not active["version"]
            or not re.fullmatch(r"[a-f0-9]{64}", str(active.get("wheel_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{40}", str(active.get("source_commit", "")))):
        raise ValueError("Installation receipt has an invalid build identity.")
    payload = active.get("payload_sha256")
    if (not isinstance(payload, dict) or "gex_terminal/__init__.py" not in payload
            or any(not isinstance(name, str) or not name.startswith("gex_terminal/")
                   or ".." in Path(name).parts or not isinstance(value, str)
                   or not re.fullmatch(r"[a-f0-9]{64}", value) for name, value in payload.items())):
        raise ValueError("Installation receipt has an invalid application payload identity.")
    active_environment(target, receipt)
    if set(hashes) not in (set(LAUNCH_FILES), set((*LAUNCH_FILES, *WIND_LAUNCH_FILES)),
                          set((*LAUNCH_FILES, *WIND_LAUNCH_FILES, *STARTER_LAUNCH_FILES))):
        raise ValueError("Installation receipt has an invalid launcher inventory.")
    for name in hashes:
        path = target / name
        if path.is_symlink() or not path.is_file() or digest(path) != hashes.get(name):
            raise ValueError("An installed launcher has changed. Choose a new application folder to preserve it.")
    return receipt


def active_environment(target: Path, receipt: dict) -> Path:
    if receipt.get("schema") != SCHEMA or receipt.get("root") != str(target.resolve()):
        raise ValueError("Installation receipt does not match this application folder.")
    name = receipt.get("active", {}).get("environment", "")
    if not isinstance(name, str) or not re.fullmatch(r"env-[a-f0-9]{12}-[a-f0-9]{12}", name):
        raise ValueError("Installation receipt has an invalid environment identity.")
    parent = target / "environments"
    environment = parent / name
    if parent.is_symlink() or environment.is_symlink() or not environment.is_dir():
        raise ValueError("The recorded application environment is unavailable.")
    return environment


def atomic_write(path: Path, data: bytes, *, executable: bool = False) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Refusing to replace an unexpected installer path: {path.name}")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as output:
            output.write(data)
        temporary.chmod(0o755 if executable else 0o644)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run(command: list[str], *, cwd: Path, stage: str) -> str:
    result = subprocess.run(command, cwd=cwd, env=clean_environment(),
                            text=True, capture_output=True, timeout=600)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1500:]
        raise RuntimeError(f"{stage} failed. {detail}")
    return result.stdout


def verify_payload(environment: Path, expected: dict[str, str], scratch: Path) -> str:
    python = str(environment / "bin" / "python")
    purelib = Path(run([python, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                       cwd=scratch, stage="Application payload location check").strip())
    if not purelib.resolve().is_relative_to(environment.resolve()):
        raise ValueError("Installed package location is outside the application environment.")
    package = purelib / "gex_terminal"
    if package.is_symlink() or not package.is_dir():
        raise ValueError("Installed application payload is unavailable.")
    actual = {}
    for path in package.rglob("*"):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("Installed application payload contains a symlink.")
        if path.is_file():
            actual[path.relative_to(purelib).as_posix()] = digest(path)
    if actual != expected:
        raise ValueError("Installed application payload differs from the reviewed wheel. Choose a new application folder to repair it.")
    return hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


def verify_environment(environment: Path, expected_version: str, payload: dict[str, str]) -> dict:
    python = str(environment / "bin" / "python")
    with tempfile.TemporaryDirectory(prefix="gex-install-check-") as directory:
        scratch = Path(directory).resolve()
        payload_identity = verify_payload(environment, payload, scratch)
        run([python, "-I", "-m", "pip", "--isolated", "check"], cwd=scratch, stage="Dependency check")
        identity = json.loads(run([python, "-I", "-c", (
            "import json,sys,gex_terminal; from pathlib import Path; "
            "from importlib.metadata import distributions; "
            "print(json.dumps({'version':gex_terminal.__version__,"
            "'module':str(Path(gex_terminal.__file__).resolve()),'python':sys.version.split()[0],"
            "'dependencies':{d.metadata['Name']:d.version for d in distributions()}}))"
        )], cwd=scratch, stage="Installed application check"))
        if identity["version"] != expected_version or not Path(identity["module"]).is_relative_to(environment.resolve()):
            raise ValueError("Installed application identity does not match the reviewed wheel.")
        doctor = json.loads(run([python, "-I", "-m", "gex_terminal.cli", "doctor", "--json"],
                                cwd=scratch, stage="Offline doctor"))
        if doctor.get("schema") != "gex-terminal.doctor.v1" or doctor.get("execution", {}).get("network_used") is not False:
            raise ValueError("Offline doctor did not return the expected local-only report.")
        snapshot = scratch / "snapshot.json"
        run([python, "-I", "-m", "gex_terminal.cli", "--replay-session", SESSION,
             "--export", str(snapshot)], cwd=scratch, stage="Bundled replay check")
        exported = read_json(snapshot)
        if exported.get("schema") != "gex-terminal.snapshot.v2" or exported.get("symbol") != "ES":
            raise ValueError("Bundled replay did not produce the expected ES snapshot.")
        return {"python": identity["python"], "dependencies": identity["dependencies"],
                "doctor": "passed", "bundled_replay": SESSION, "replay_export": "passed",
                "payload_identity_sha256": payload_identity, "payload_files": len(payload)}


def launcher_contents(target: Path, *, wind_tunnel: bool = False) -> dict[str, bytes]:
    base_python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    command = " ".join(shlex.quote(part) for part in (
        base_python, "-I", str(target / "launcher.py"), "--launch", "--target", str(target),
    ))
    contents = {
        "launcher.py": Path(__file__).read_bytes(),
        "run-gex": f'#!/bin/sh\nexec {command} "$@"\n'.encode(),
        "Start GEX.command": (
            '#!/bin/sh\n'
            'if [ "$#" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then\n'
            "    printf '\\033[8;40;120t'\n"
            'fi\n'
            f'exec {shlex.quote(str(target / "run-gex"))} "$@"\n'
        ).encode(),
    }
    if wind_tunnel:
        contents["Start Terminal.command"] = contents["Start GEX.command"]
        contents["Start GEX.command"] = (
            '#!/bin/sh\n'
            'if [ "$#" -eq 0 ]; then\n'
            f'    exec {command} --choose\n'
            'fi\n'
            f'exec {shlex.quote(str(target / "run-gex"))} "$@"\n'
        ).encode()
        contents["run-wind-tunnel"] = f'#!/bin/sh\nexec {command} --wind-tunnel "$@"\n'.encode()
        contents["Start Wind Tunnel.command"] = (
            '#!/bin/sh\n'
            f'exec {shlex.quote(str(target / "run-wind-tunnel"))} "$@"\n'
        ).encode()
    return contents


def install(wheel: Path, expected_sha256: str, source_commit: str, target: Path,
            *, research_dir: Path | None = None, wheelhouse: Path | None = None) -> dict:
    if os.name != "posix" or sys.version_info[:2] not in {(3, 11), (3, 12)}:
        raise ValueError("Use Python 3.11 or 3.12 on macOS or Linux for this installer.")
    wheel = wheel.resolve()
    identity = wheel_identity(wheel, expected_sha256, source_commit)
    target = target.absolute()
    previous = owned_target(target)
    target = target.resolve()
    research = (research_dir or (target.parent / f"{target.name} Research")).absolute()
    if research.is_symlink() or (research.exists() and not research.is_dir()):
        raise ValueError("Research destination must be an ordinary folder.")
    research = research.resolve()
    if research.is_relative_to(target) or target.is_relative_to(research):
        raise ValueError("Choose a research folder separate from the application folder.")
    if previous and previous.get("research_dir") != str(research):
        raise ValueError("This installation already uses another research folder. Preserve it or choose a new application folder.")
    if wheelhouse is not None:
        wheelhouse = wheelhouse.resolve()
        if not wheelhouse.is_dir():
            raise ValueError("Wheelhouse must be a folder containing the required dependency wheels.")
    if previous:
        active = previous["active"]
        if all(active.get(key) == value for key, value in identity.items()):
            verify_environment(active_environment(target, previous), identity["version"], identity["payload_sha256"])
            return {**previous, "reused": True}
    else:
        if not target.exists():
            target.mkdir(parents=True, exist_ok=False)
        if not (target / OWNER).exists():
            atomic_write(target / OWNER, json.dumps({"schema": SCHEMA, "root": str(target)}).encode())
    environments = target / "environments"
    if environments.is_symlink() or (environments.exists() and not environments.is_dir()):
        raise ValueError("Unexpected environment storage path; choose a new application folder.")
    environments.mkdir(exist_ok=True)
    name = f"env-{identity['wheel_sha256'][:12]}-{uuid.uuid4().hex[:12]}"
    environment = environments / name
    environment.mkdir(exist_ok=False)
    print("Preparing a separate application environment...", flush=True)
    venv.EnvBuilder(with_pip=True).create(environment)
    python = str(environment / "bin" / "python")
    command = [python, "-I", "-m", "pip", "--isolated", "install", "--no-input"]
    if wheelhouse is not None:
        command.extend(["--no-index", "--find-links", str(wheelhouse)])
    command.append(str(wheel))
    with tempfile.TemporaryDirectory(prefix="gex-install-") as directory:
        run(command, cwd=Path(directory), stage="Application installation")
    print("Checking dependencies, offline setup and a bundled replay...", flush=True)
    verification = verify_environment(environment, identity["version"], identity["payload_sha256"])
    if digest(wheel) != identity["wheel_sha256"]:
        raise ValueError("Wheel changed during installation; the active application was not changed.")
    research.mkdir(parents=True, exist_ok=True)
    # Existing launchers remain byte-identical across application updates.
    # Their v1 selection contract reads the active environment from the receipt.
    contents = ({name: (target / name).read_bytes() for name in previous["launcher_sha256"]}
                if previous else launcher_contents(target, wind_tunnel="gex_terminal/wind_tunnel_cli.py" in identity["payload_sha256"]))
    if not previous:
        for filename, data in contents.items():
            atomic_write(target / filename, data, executable=filename != "launcher.py")
    receipt = {
        "schema": SCHEMA, "root": str(target), "research_dir": str(research),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "active": {**identity, "environment": name, "verification": verification},
        "previous": previous.get("active") if previous else None,
        "launcher_sha256": {filename: hashlib.sha256(data).hexdigest() for filename, data in contents.items()},
        "evidence_ceiling": "Local installation and synthetic replay checks; no live provider or observed-user evidence.",
    }
    # Commit selection last; failed installs keep the previous selection intact.
    atomic_write(target / RECEIPT, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    return {**receipt, "reused": False}


def choose_action(wind_tunnel: bool) -> str | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("The starter needs an interactive terminal. Use run-gex for Terminal, "
                         "run-wind-tunnel for Wind Tunnel, or run-gex --both in a terminal.")
    print("\nGEX — Choose your workspace\n\n  1  Terminal", flush=True)
    if wind_tunnel:
        print("  2  Market Wind Tunnel\n  3  Both\n", flush=True)
        print("Both opens two independent views. Quitting Terminal stops that Wind Tunnel session.")
    else:
        print("\nThis installed version supports Terminal only.")
    print("  q or Return  Cancel\n", flush=True)
    choices = {"1": "terminal", "q": None, "": None}
    if wind_tunnel:
        choices.update({"2": "wind", "3": "both"})
    while True:
        try:
            answer = input("Choose an option: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled. No application was started.", flush=True)
            return None
        if answer in choices:
            return choices[answer]
        print("Choose 1, 2, 3 or q." if wind_tunnel else "Choose 1 or q.", flush=True)


def stop_child(process: subprocess.Popen | None) -> None:
    """Settle only the child we created; never signal a shared process group."""
    if process is None:
        return
    for signum, timeout in ((signal.SIGINT, 3), (signal.SIGTERM, 2), (signal.SIGKILL, 2)):
        if process.poll() is not None:
            return
        try:
            process.send_signal(signum)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError("A launched process did not stop; close its launch window.")


def open_browser(url: str) -> bool:
    # A browser controller can fail or hang. Keep that optional action bounded;
    # its helper owns no application process and never closes a user's browser.
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys,webbrowser; sys.exit(0 if webbrowser.open(sys.argv[1]) else 1)", url],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def run_both(command: list[str], wind_command: list[str], *, cwd: Path,
             no_browser: bool = False, startup_timeout: float = 20.0) -> int:
    """Own two children for one launch session, keeping server output off the TUI."""
    wind = terminal = None
    previous_handlers = {}
    interrupted = None
    output = bytearray()
    stream_closed = False
    ready_url = None

    def interrupt(signum, _frame):
        nonlocal interrupted
        # Do not raise inside Popen before its new child has been assigned.
        # The loop observes this immediately after each bounded startup step.
        if interrupted is None:
            interrupted = signum

    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous_handlers[signum] = signal.signal(signum, interrupt)
        wind = subprocess.Popen(wind_command, cwd=cwd, env=clean_environment(),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        os.set_blocking(wind.stdout.fileno(), False)
        deadline = time.monotonic() + startup_timeout
        with selectors.DefaultSelector() as selector:
            selector.register(wind.stdout, selectors.EVENT_READ)
            while True:
                if interrupted is not None:
                    return 128 + interrupted
                for _, _events in selector.select(timeout=0.1):
                    block = os.read(wind.stdout.fileno(), 65536)
                    if block:
                        output.extend(block)
                        if ready_url is None:
                            match = re.search(rb"(?m)^http://127\.0\.0\.1:([0-9]{1,5})/#cap=[A-Za-z0-9_-]{32,128}\r?\n", output)
                            if match and 0 < int(match.group(1)) < 65536:
                                ready_url = match.group().decode().strip()
                        del output[:-32768]
                    else:
                        selector.unregister(wind.stdout)
                        stream_closed = True
                if interrupted is not None:
                    return 128 + interrupted
                if terminal is None:
                    if wind.poll() is not None or stream_closed:
                        raise RuntimeError("Wind Tunnel could not start. Terminal was not opened. "
                                           "Use its individual shortcut to inspect the problem.")
                    if ready_url is not None:
                        url = ready_url
                        print("Wind Tunnel is ready locally.\n" + url, flush=True)
                        print("Opening Terminal. Quit Terminal to stop this combined session.\n"
                              "The two views have independent replay and scenario selections.", flush=True)
                        if not no_browser:
                            browser_opened = open_browser(url)
                            if interrupted is not None:
                                return 128 + interrupted
                            if not browser_opened:
                                raise RuntimeError("The browser could not open, so Both was cancelled. "
                                                   "Use the Wind Tunnel shortcut to open its URL manually, "
                                                   "or run-gex --both --no-browser to manage the browser yourself.")
                        if interrupted is not None:
                            return 128 + interrupted
                        if wind.poll() is not None:
                            raise RuntimeError("Wind Tunnel stopped during startup. Terminal was not opened.")
                        terminal = subprocess.Popen(command, cwd=cwd, env=clean_environment())
                    elif time.monotonic() >= deadline:
                        raise RuntimeError("Wind Tunnel did not become ready in time. No Terminal was opened; "
                                           "the combined session was stopped.")
                else:
                    if terminal.poll() is not None:
                        return terminal.returncode
                    if wind.poll() is not None:
                        raise RuntimeError("Wind Tunnel stopped unexpectedly. The combined session was stopped; "
                                           "saved research remains available.")
    except KeyboardInterrupt:
        return 130
    finally:
        # Ignore repeated launch-window signals until both owned children settle.
        interrupted = interrupted or signal.SIGINT
        try:
            try:
                stop_child(terminal)
            finally:
                stop_child(wind)
                if wind is not None and wind.stdout is not None:
                    wind.stdout.close()
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def launch(target: Path, *, doctor: bool = False, list_replays: bool = False,
           export: Path | None = None, session: str = SESSION, wind_tunnel: bool = False,
           choose: bool = False, both: bool = False, no_browser: bool = False) -> int:
    receipt = owned_target(target)
    if not receipt:
        raise ValueError("No completed application installation exists here. Run Install first.")
    environment = active_environment(target.resolve(), receipt)
    research = Path(receipt["research_dir"])
    if research.is_symlink() or not research.is_dir():
        raise ValueError("Research folder is unavailable. Restore its location before starting GEX.")
    has_wind_tunnel = "gex_terminal/wind_tunnel_cli.py" in receipt["active"]["payload_sha256"]
    if choose:
        choice = choose_action(has_wind_tunnel)
        if choice is None:
            return 0
        wind_tunnel, both = choice == "wind", choice == "both"
        if choice in {"terminal", "both"}:
            print("\033[8;40;120t", end="", flush=True)
    if wind_tunnel or both:
        if not has_wind_tunnel:
            raise ValueError("This installed version has no Wind Tunnel. Install a reviewed 0.6.0 or later bundle.")
    if both and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise ValueError("Both needs an interactive terminal. Open Start GEX.command and choose Both.")
    args = ["doctor", "--json"] if doctor else (["list-replays"] if list_replays else ["--replay-session", session])
    wind_args = ["wind-tunnel", "serve", "--port", "0", "--workspace", str(research / "wind-tunnel")]
    if wind_tunnel:
        args = [*wind_args, *(["--no-browser"] if no_browser else [])]
    if export is not None:
        args.extend(["--export", str(export.absolute())])
    # Import config in a newly created directory before entering research, so
    # neither a caller nor research .env can change this offline launcher.
    with tempfile.TemporaryDirectory(prefix="gex-launch-") as directory:
        verify_payload(environment, receipt["active"]["payload_sha256"], Path(directory))
        command = [str(environment / "bin" / "python"), "-I", "-c", BOOTSTRAP, str(research)]
        if both:
            return run_both([*command, *args], [*command, *wind_args, "--no-browser"],
                            cwd=Path(directory), no_browser=no_browser)
        result = subprocess.run(
            [*command, *args],
            cwd=directory, env=clean_environment(),
        )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--source-commit")
    parser.add_argument("--research-dir", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--launch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--session", default=SESSION, help="Bundled offline replay for launch")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--doctor", action="store_true", help="Run local doctor through the installed launcher")
    mode.add_argument("--list-replays", action="store_true", help="List bundled sessions through the installed launcher")
    mode.add_argument("--export", type=Path, help="Export a synthetic snapshot through the installed launcher")
    mode.add_argument("--wind-tunnel", action="store_true", help="Open the offline Market Wind Tunnel in your browser")
    mode.add_argument("--choose", action="store_true", help="Choose Terminal, Wind Tunnel or Both interactively")
    mode.add_argument("--both", action="store_true", help="Run Terminal and Wind Tunnel in one managed session")
    parser.add_argument("--no-browser", action="store_true", help="Print the Wind Tunnel URL without opening a browser")
    args = parser.parse_args()
    try:
        if args.launch:
            return launch(args.target, doctor=args.doctor, list_replays=args.list_replays,
                          export=args.export, session=args.session, wind_tunnel=args.wind_tunnel,
                          choose=args.choose, both=args.both, no_browser=args.no_browser)
        if not all((args.wheel, args.sha256, args.source_commit)):
            parser.error("installation requires --wheel, --sha256 and --source-commit")
        receipt = install(args.wheel, args.sha256, args.source_commit, args.target,
                          research_dir=args.research_dir, wheelhouse=args.wheelhouse)
        print("Existing installation verified." if receipt["reused"] else "Installation ready.")
        print(f"Start: {Path(receipt['root']) / 'Start GEX.command'}")
        if "Start Wind Tunnel.command" in receipt["launcher_sha256"]:
            print(f"Wind Tunnel: {Path(receipt['root']) / 'Start Wind Tunnel.command'}")
        if "Start Terminal.command" in receipt["launcher_sha256"]:
            print(f"Terminal: {Path(receipt['root']) / 'Start Terminal.command'}")
        print(f"Research folder: {receipt['research_dir']}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"GEX setup: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Loopback-only, capability-protected offline Wind Tunnel and receipt storage.

The browser can select bundled sources and receipt identifiers, never paths.
The workspace is an explicitly owned directory of immutable, bounded JSON files.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
from typing import Any

from aiohttp import web

from . import __version__
from .session_intake import IntakeError, MAX_CAPTURE_BYTES, SessionIntake


RECEIPT_SCHEMA = "gex-terminal.wind-tunnel.receipt.v1"
WORKSPACE_SCHEMA = "gex-terminal.wind-tunnel.workspace.v1"
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_WORKSPACE_BYTES = 64 * 1024 * 1024
MAX_RECEIPTS = 100
CALCULATION_TIMEOUT_SECONDS = 60
MODELS_TIMEOUT_SECONDS = 300
SAVED_REPLAY_TIMEOUT_SECONDS = 300
SAVED_INVESTIGATION_MARKETS = {"investigate-saved": "ES", "investigate-saved-nq": "NQ"}
SAVED_FLIP_COMPARISON = "compare-saved-flips"
SAVED_SESSION_COMPARISON = "compare-saved-sessions"
BLIND_REVIEW = "blind-review"
BLIND_COMPARISON = "blind-comparison"
BLIND_SESSION_COMPARISON = "blind-session-comparison"
BLIND_STUDY = "blind-study"
BLIND_SAVED_STUDY = "blind-saved-study"
BLIND_STUDY_COMPARISON = "blind-study-comparison"
BLIND_SAVED_STUDY_COMPARISON = "blind-saved-study-comparison"
STUDY_COMPARISONS = (BLIND_STUDY_COMPARISON, BLIND_SAVED_STUDY_COMPARISON)
BLIND_OPERATIONS = (BLIND_REVIEW, BLIND_COMPARISON, BLIND_SESSION_COMPARISON,
                    BLIND_STUDY, BLIND_SAVED_STUDY, *STUDY_COMPARISONS)
COMPARISONS = (SAVED_FLIP_COMPARISON, SAVED_SESSION_COMPARISON)
OPERATIONS = ("calculate", "surface", "search", "models", "investigate", *SAVED_INVESTIGATION_MARKETS,
              *COMPARISONS)
RECEIPT_OPERATIONS = (*OPERATIONS, *BLIND_OPERATIONS)
ID_PATTERN = re.compile(r"[0-9a-f]{64}")
OWNER_FILE = ".wind-tunnel-workspace.json"
CORE_KEY = web.AppKey("core", object)
STORE_KEY = web.AppKey("store", object)
TOKEN_KEY = web.AppKey("capability", str)
ORIGIN_KEY = web.AppKey("origin", str)
LOCK_KEY = web.AppKey("calculation_lock", asyncio.Lock)
ASSETS_KEY = web.AppKey("assets", dict)
INTAKE_KEY = web.AppKey("session_intake", object)


class ReceiptError(ValueError):
    """A safe, deliberately path-free receipt/workspace error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def decode_json(data: bytes) -> dict:
    if len(data) > MAX_JSON_BYTES:
        raise ReceiptError("JSON exceeds the 32 MiB limit.")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReceiptError("Duplicate JSON keys are not allowed.")
            result[key] = value
        return result

    def reject_constant(_):
        raise ReceiptError("JSON numbers must be finite.")

    try:
        result = json.loads(data, object_pairs_hook=unique_pairs,
                            parse_constant=reject_constant)
        if not isinstance(result, dict):
            raise ReceiptError("JSON must contain one object.")
        canonical_bytes(result)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ReceiptError("Invalid JSON object.") from exc
    return result


def core_module():
    # Import only when needed; this entry point does not construct provider config.
    from . import wind_tunnel
    return wind_tunnel


def operation_core(kind: str, core=None):
    if kind == "investigate":
        # This operation always uses the bundled replay, even when the server
        # started from a saved Terminal checkpoint.
        from . import wind_tunnel_investigation
        return wind_tunnel_investigation
    if kind in SAVED_INVESTIGATION_MARKETS:
        from . import wind_tunnel_saved_investigation
        return wind_tunnel_saved_investigation
    if kind == SAVED_FLIP_COMPARISON:
        from . import wind_tunnel_flip_comparison
        return wind_tunnel_flip_comparison
    if kind == SAVED_SESSION_COMPARISON:
        from . import wind_tunnel_session_comparison
        return wind_tunnel_session_comparison
    if kind == BLIND_REVIEW:
        from . import wind_tunnel_blind_review
        return wind_tunnel_blind_review
    if kind == BLIND_COMPARISON:
        from . import wind_tunnel_blind_comparison
        return wind_tunnel_blind_comparison
    if kind == BLIND_SESSION_COMPARISON:
        from . import wind_tunnel_blind_session_comparison
        return wind_tunnel_blind_session_comparison
    if kind == BLIND_STUDY:
        from . import wind_tunnel_blind_study
        return wind_tunnel_blind_study
    if kind == BLIND_SAVED_STUDY:
        from . import wind_tunnel_blind_saved_study
        return wind_tunnel_blind_saved_study
    if kind == BLIND_STUDY_COMPARISON:
        from . import wind_tunnel_blind_study_comparison
        return wind_tunnel_blind_study_comparison
    if kind == BLIND_SAVED_STUDY_COMPARISON:
        from . import wind_tunnel_blind_saved_study_comparison
        return wind_tunnel_blind_saved_study_comparison
    return core or core_module()


async def calculate_operation(kind: str, request: dict, *, core=None, saved_replay=None,
                              comparison_replays=None, session_replays=None, study_captures=None) -> dict:
    producer = operation_core(kind, core)
    if kind == BLIND_STUDY:
        try:
            return await producer.blind_study(request)
        except producer.BlindStudyError as exc:
            raise ReceiptError(str(exc)) from exc
    if kind in (BLIND_SAVED_STUDY, *STUDY_COMPARISONS):
        try:
            return await getattr(producer, kind.replace("-", "_"))(request, study_captures)
        except producer.BlindStudyError as exc:
            raise ReceiptError(str(exc)) from exc
    if kind in BLIND_OPERATIONS:
        from .wind_tunnel_blind_review import BlindReviewError

        try:
            if kind == BLIND_COMPARISON:
                return await producer.blind_comparison(request, comparison_replays)
            if kind == BLIND_SESSION_COMPARISON:
                return await producer.blind_session_comparison(request, session_replays)
            return await producer.blind_review(request, saved_replay)
        except BlindReviewError as exc:
            raise ReceiptError(str(exc)) from exc
    if kind in COMPARISONS:
        compare = getattr(producer, kind.replace("-", "_"))
        replays = session_replays if kind == SAVED_SESSION_COMPARISON else comparison_replays
        try:
            return await compare(request, replays)
        except producer.FlipComparisonError as exc:
            raise ReceiptError(str(exc)) from exc
    market = SAVED_INVESTIGATION_MARKETS.get(kind)
    if market is not None:
        if (saved_replay is None or saved_replay.symbol != market
                or (saved_replay.capture_sha256 is not None
                    and saved_replay.capture_sha256 != request.get("capture_sha256"))):
            raise ReceiptError(f"Open the original saved {market} capture to run or reproduce this investigation.")
        try:
            await saved_replay.verify_capture(request.get("capture_sha256"))
        except (ValueError, OSError) as exc:
            raise ReceiptError(f"The saved {market} capture could not be verified. Select the original completed capture.") from exc
        return await producer.investigate_saved(request, saved_replay)
    return await getattr(producer, kind)(request)


def validate_name(name: Any) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ReceiptError("Use a scenario name of 1 to 80 characters.")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ReceiptError("Scenario names cannot contain control characters.")
    return name.strip()


async def make_receipt(name: str, kind: str, request: dict, *, core=None, saved_replay=None,
                       comparison_replays=None, session_replays=None) -> dict:
    name = validate_name(name)
    if kind not in RECEIPT_OPERATIONS or not isinstance(request, dict):
        raise ReceiptError("Unknown calculation kind or invalid request.")
    if kind == "models" and request.get("detail_level") == "compact":
        # Compact display payloads omit contract contributions and the embedded
        # checkpoint echo. Receipts always recompute complete portable evidence
        # from the original request, rather than storing that display projection.
        request = {**request, "detail_level": "full"}
    result = await calculate_operation(kind, request, core=core, saved_replay=saved_replay,
                                       comparison_replays=comparison_replays, session_replays=session_replays)
    return assemble_receipt(name, kind, result)


def assemble_receipt(name: str, kind: str, result: dict) -> dict:
    """Wrap an authoritative calculated result in the standard receipt envelope."""
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "name": validate_name(name),
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "application_version": __version__,
        "request": result["request"],
        "result": result,
    }
    receipt["receipt_sha256"] = digest(receipt)
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt: Any) -> dict:
    fields = {"schema", "name", "kind", "created_at", "application_version",
              "request", "result", "receipt_sha256"}
    if not isinstance(receipt, dict) or set(receipt) != fields:
        raise ReceiptError("Unknown receipt fields.")
    if receipt["schema"] != RECEIPT_SCHEMA or receipt["kind"] not in RECEIPT_OPERATIONS:
        raise ReceiptError("Unsupported receipt schema or calculation kind.")
    validate_name(receipt["name"])
    if not isinstance(receipt["application_version"], str) or not 1 <= len(receipt["application_version"]) <= 80:
        raise ReceiptError("Invalid receipt application identity.")
    try:
        if not isinstance(receipt["created_at"], str) or len(receipt["created_at"]) > 40:
            raise ValueError
        if datetime.fromisoformat(receipt["created_at"]).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ReceiptError("Invalid receipt creation time.") from exc
    if not isinstance(receipt["request"], dict) or not isinstance(receipt["result"], dict):
        raise ReceiptError("Receipt request and result must be objects.")
    if receipt["kind"] == "models" and receipt["request"].get("detail_level") == "compact":
        raise ReceiptError("Model receipts require full portable detail.")
    if receipt["result"].get("request") != receipt["request"]:
        raise ReceiptError("Receipt request differs from its result.")
    expected = receipt["receipt_sha256"]
    if not isinstance(expected, str) or not ID_PATTERN.fullmatch(expected):
        raise ReceiptError("Invalid receipt identity.")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    try:
        if not secrets.compare_digest(expected, digest(unsigned)):
            raise ReceiptError("Receipt checksum does not match its content.")
        if len(canonical_bytes(receipt)) > MAX_JSON_BYTES:
            raise ReceiptError("Receipt exceeds the 32 MiB limit.")
    except (TypeError, RecursionError, OverflowError) as exc:
        raise ReceiptError("Invalid receipt content.") from exc
    return receipt


async def reproduce_receipt(receipt: dict, *, core=None, saved_replay=None, comparison_replays=None,
                            session_replays=None, study_captures=None) -> dict:
    validate_receipt(receipt)
    kind = receipt["kind"]
    producer = operation_core(kind, core)
    identity = producer.calculation_identity()
    expected = receipt["result"]
    recorded = expected.get("calculation")
    identity_error = "Receipt calculation identity differs; use its original reviewed build, Python and NumPy versions."
    if (receipt["application_version"] != __version__
            or not isinstance(recorded, dict)
            or expected.get("calculation_fingerprint") != digest(recorded)):
        raise ReceiptError(identity_error)
    es_only_build = recorded != identity
    if es_only_build:
        from .wind_tunnel_saved_receipt_compat import matches_es_only_build, with_recorded_identity
        if (not matches_es_only_build(kind, recorded, identity)
                or (saved_replay is not None and saved_replay.symbol != "ES")):
            raise ReceiptError(identity_error)
        if kind == BLIND_SAVED_STUDY:
            try:
                market = producer.capture_market(receipt["request"])
            except producer.BlindStudyError as exc:
                raise ReceiptError(str(exc)) from exc
            if market != "ES":
                raise ReceiptError(identity_error)
    result = await calculate_operation(kind, receipt["request"], core=core, saved_replay=saved_replay,
                                       comparison_replays=comparison_replays, session_replays=session_replays,
                                       study_captures=study_captures)
    if es_only_build:
        result = with_recorded_identity(result, recorded)
    exact = (canonical_bytes(result) == canonical_bytes(receipt["result"])
             and receipt["application_version"] == __version__)
    return {
        "schema": "gex-terminal.wind-tunnel.reproduction.v1",
        "status": "verified" if exact else "mismatch",
        "receipt_sha256": receipt["receipt_sha256"],
        "expected_result_sha256": digest(receipt["result"]),
        "actual_result_sha256": digest(result),
        "application_version_matches": receipt["application_version"] == __version__,
        "result": result,
        "evidence_ceiling": "Deterministic offline reproduction only; predictive validity unmeasured.",
    }


class ReceiptStore:
    """Keep a directory descriptor so requests cannot escape via path changes."""

    def __init__(self, directory: Path | str):
        self.path = Path(directory).expanduser().absolute()
        self.fd = -1
        if self.path.is_symlink():
            raise ReceiptError("Workspace cannot be a symbolic link.")
        self.path.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            names = os.listdir(self.fd)
            if OWNER_FILE not in names:
                if names:
                    raise ReceiptError("Choose an empty folder or an existing Wind Tunnel workspace.")
                self._write_new(OWNER_FILE, canonical_bytes({"schema": WORKSPACE_SCHEMA}))
            marker = decode_json(self._read(OWNER_FILE))
            if marker != {"schema": WORKSPACE_SCHEMA}:
                raise ReceiptError("Unknown workspace ownership marker.")
            self._inventory()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def _read(self, name: str) -> bytes:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
                raise ReceiptError("Workspace contains an invalid or oversized file.")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_JSON_BYTES + 1)
            if len(data) > MAX_JSON_BYTES:
                raise ReceiptError("Workspace file exceeds the size limit.")
            return data
        finally:
            os.close(fd)

    def _write_new(self, name: str, data: bytes):
        # No replacement: a failed/interrupted write is never mistaken for a receipt.
        temporary = ".pending-" + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
            os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd,
                    follow_symlinks=False)
        finally:
            os.close(fd)
            os.unlink(temporary, dir_fd=self.fd)

    def _inventory(self) -> tuple[list[str], int]:
        names = os.listdir(self.fd)
        if len(names) > MAX_RECEIPTS + 1:
            raise ReceiptError("Workspace exceeds the 100 receipt limit.")
        receipts = []
        total = 0
        for name in names:
            if name != OWNER_FILE and not re.fullmatch(r"[0-9a-f]{64}\.json", name):
                raise ReceiptError("Workspace contains an unrecognized file; preserve it and choose a new folder.")
            info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
                raise ReceiptError("Workspace contains an invalid or oversized file.")
            total += info.st_size
            if name != OWNER_FILE:
                receipts.append(name)
        if total > MAX_WORKSPACE_BYTES:
            raise ReceiptError("Workspace exceeds the 64 MiB limit.")
        return receipts, total

    def load(self, receipt_id: str) -> dict:
        if not ID_PATTERN.fullmatch(receipt_id):
            raise ReceiptError("Invalid scenario identifier.")
        self._inventory()
        receipt = validate_receipt(decode_json(self._read(receipt_id + ".json")))
        if receipt["receipt_sha256"] != receipt_id:
            raise ReceiptError("Saved scenario identity differs from its filename.")
        return receipt

    def list(self, *, matches=None) -> list[dict]:
        names, _ = self._inventory()
        result = []
        for filename in names:
            receipt = self.load(filename[:-5])
            if matches is not None and not matches(receipt):
                continue
            result.append({"id": receipt["receipt_sha256"], "name": receipt["name"],
                           "kind": receipt["kind"], "created_at": receipt["created_at"],
                           "result_sha256": receipt["result"].get("result_sha256")})
        return sorted(result, key=lambda row: (row["created_at"], row["id"]), reverse=True)

    def save(self, receipt: dict) -> dict:
        validate_receipt(receipt)
        data = canonical_bytes(receipt)
        names, total = self._inventory()
        name = receipt["receipt_sha256"] + ".json"
        if name in names:
            if self.load(receipt["receipt_sha256"]) != receipt:
                raise ReceiptError("Saved scenario identity conflict.")
            return receipt
        if len(names) >= MAX_RECEIPTS or total + len(data) > MAX_WORKSPACE_BYTES:
            raise ReceiptError("Workspace is full; choose a new workspace to preserve existing research.")
        self._write_new(name, data)
        return receipt


def packaged_assets() -> dict[str, tuple[bytes, str]]:
    root = resources.files("gex_terminal").joinpath("wind_tunnel_web")
    result = {}
    fixed = {"index.html": "text/html", "app.js": "text/javascript", "app.css": "text/css",
             "vendor/plotly.min.js": "text/javascript", "vendor/plotly-LICENSE.txt": "text/plain",
             "vendor/phosphor-LICENSE.txt": "text/plain", "vendor/manifest.json": "application/json"}
    for filename, mime in fixed.items():
        resource = root.joinpath(filename)
        if resource.is_file():
            route = "/" if filename == "index.html" else "/static/" + filename
            result[route] = (resource.read_bytes(), mime)
    icons = root.joinpath("icons")
    if icons.is_dir():
        for resource in icons.iterdir():
            if re.fullmatch(r"[a-z0-9-]+\.svg", resource.name) and resource.is_file():
                result["/static/icons/" + resource.name] = (resource.read_bytes(), "image/svg+xml")
    return result


def error_response(status: int, code: str, message: str):
    return web.json_response({"error": {"code": code, "message": message}}, status=status)


@web.middleware
async def security_boundary(request, handler):
    origin = request.app[ORIGIN_KEY]
    if request.headers.get("Host") != origin.removeprefix("http://"):
        return error_response(403, "host", "Use this session's loopback launch URL.")
    if request.headers.get("Origin", origin) != origin:
        return error_response(403, "origin", "Cross-origin requests are not allowed.")
    if request.path.startswith("/api/"):
        token = request.headers.get("X-GEX-Capability", "")
        if not secrets.compare_digest(token.encode("utf-8"), request.app[TOKEN_KEY].encode("utf-8")):
            return error_response(403, "capability", "Reopen the launch URL from your local terminal.")
    try:
        response = await handler(request)
    except web.HTTPRequestEntityTooLarge:
        message = ("Captured-session upload exceeds the 4 MiB limit."
                   if request.path == "/api/intake" else "Request exceeds the 32 MiB limit.")
        response = error_response(413, "size", message)
    except web.HTTPException as exc:
        response = error_response(exc.status, "http", "Request is not supported.")
    except IntakeError as exc:
        response = error_response(400, "intake", str(exc))
    except ReceiptError as exc:
        response = error_response(400, "receipt", str(exc))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        response = error_response(400, "input", "Invalid or unsupported scenario input.")
    except FileNotFoundError:
        response = error_response(404, "missing", "Saved scenario was not found.")
    except TimeoutError:
        response = error_response(408, "timeout", "Calculation exceeded its time limit; try a smaller grid.")
    except Exception:
        response = error_response(500, "internal", "Local operation could not complete; existing research was preserved.")
    response.headers.update({
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; worker-src 'self' blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "Cross-Origin-Resource-Policy": "same-origin",
    })
    return response


async def read_body(request) -> dict:
    if request.content_type != "application/json":
        raise ReceiptError("Send an application/json request.")
    return decode_json(await request.read())


async def read_intake_body(request) -> bytes:
    """Keep browser capture intake small even when portable receipts are larger."""
    if request.content_length is not None and request.content_length > MAX_CAPTURE_BYTES:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_CAPTURE_BYTES, actual_size=request.content_length)
    data = bytearray()
    async for block in request.content.iter_chunked(64 * 1024):
        if len(data) + len(block) > MAX_CAPTURE_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_CAPTURE_BYTES, actual_size=len(data) + len(block))
        data.extend(block)
    return bytes(data)


async def run_bounded(request, operation, *, kind=None, locks=()):
    locks = locks or (request.app[LOCK_KEY],)
    if any(lock.locked() for lock in locks):
        return error_response(429, "busy", "A calculation is running; wait for it to finish.")
    async with AsyncExitStack() as held:
        for lock in locks:
            await held.enter_async_context(lock)
        # The explicitly requested two-model 54-cell grid can include thousands
        # of American-option lattice rows. Keep it bounded and cancellable while
        # allowing the same operation to finish when saved or reproduced.
        if kind in (*COMPARISONS, BLIND_COMPARISON, BLIND_SESSION_COMPARISON):
            deadline = 2 * SAVED_REPLAY_TIMEOUT_SECONDS
        elif kind in (BLIND_SAVED_STUDY, *STUDY_COMPARISONS):
            from .wind_tunnel_blind_saved_study import MAX_STUDY_CAPTURES

            study_count = 2 if kind in STUDY_COMPARISONS else 1
            deadline = study_count * MAX_STUDY_CAPTURES * SAVED_REPLAY_TIMEOUT_SECONDS
        elif kind in ("investigation-timeline", BLIND_REVIEW, *SAVED_INVESTIGATION_MARKETS):
            deadline = SAVED_REPLAY_TIMEOUT_SECONDS
        else:
            deadline = MODELS_TIMEOUT_SECONDS if kind == "models" else CALCULATION_TIMEOUT_SECONDS
        async with asyncio.timeout(deadline):
            return web.json_response(await operation(), dumps=lambda value: canonical_bytes(value).decode())


def create_app(workspace: Path | str, *, token: str | None = None,
               origin: str = "http://127.0.0.1:8765", core=None,
               assets: dict | None = None, saved_replay=None, saved_replays=None,
               comparison_workspace: Path | str | None = None) -> web.Application:
    from .wind_tunnel_saved_switching import SavedReplayRegistry

    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", origin):
        raise ValueError("Wind Tunnel only serves a loopback origin.")
    app = web.Application(middlewares=[security_boundary], client_max_size=MAX_JSON_BYTES)
    app[CORE_KEY] = core or core_module()
    app[TOKEN_KEY] = token or secrets.token_urlsafe(32)
    app[ORIGIN_KEY] = origin
    app[LOCK_KEY] = asyncio.Lock()
    app[ASSETS_KEY] = packaged_assets() if assets is None else assets
    app[INTAKE_KEY] = SessionIntake()
    replays = SavedReplayRegistry(app[CORE_KEY], saved_replays, single=saved_replay)
    if comparison_workspace is not None and replays.comparison_symbol is None:
        raise ValueError("A comparison receipt workspace requires both saved capture bindings.")

    def calculation_sources(kind, selection):
        if kind == SAVED_FLIP_COMPARISON and isinstance(selection, dict):
            pair = {}
            for market in ("ES", "NQ"):
                replay = replays.select(selection.get(market.lower()))
                if replay is not None and replay.symbol == market:
                    pair[market] = replay
            locks = tuple(replays.lock(replay) for replay in pair.values()) if len(pair) == 2 else ()
            return {"comparison_replays": pair}, locks
        if kind == SAVED_SESSION_COMPARISON and isinstance(selection, dict):
            pair = {}
            for side in ("left", "right"):
                choice = selection.get(side)
                replay = replays.select(choice)
                if replay is not None and replay.symbol == choice.get("symbol"):
                    pair[side] = replay
            # A repeated digest is invalid. Do not try to acquire its lock twice.
            locks = tuple(replays.lock(replay) for replay in pair.values()) if len(set(pair.values())) == 2 else ()
            return {"session_replays": pair}, locks
        replay = replays.select(selection) if kind in tuple(SAVED_INVESTIGATION_MARKETS) else None
        return {"saved_replay": replay}, (replays.lock(replay),) if replay is not None else ()

    async def static_asset(request):
        data, mime = app[ASSETS_KEY][request.path]
        return web.Response(body=data, content_type=mime)

    async def catalog(request):
        result = app[CORE_KEY].catalog()
        if replays.decorate_catalog(result):
            result.pop("result_sha256", None)
            result["result_sha256"] = digest(result)
        return web.json_response(result)

    async def checkpoints(request):
        if set(request.query) != {"session"} or len(request.query.getall("session")) != 1:
            raise ValueError("session is required")
        return web.json_response(app[CORE_KEY].checkpoints(request.query["session"]))

    async def examples(request):
        return web.json_response({"examples": [app[CORE_KEY].examples(name) for name in app[CORE_KEY].EXAMPLE_NAMES]})

    async def calculate(request):
        body = await read_body(request)
        kind = request.match_info["kind"]
        sources, locks = calculation_sources(kind, body)
        return await run_bounded(request, lambda: calculate_operation(
            kind, body, core=app[CORE_KEY], **sources), kind=kind, locks=locks)

    async def investigation_timeline(request):
        body = await read_body(request)
        checksum = body.get("capture_sha256")
        if set(body) != {"capture_sha256"} or not isinstance(checksum, str) or not ID_PATTERN.fullmatch(checksum):
            raise ReceiptError("Choose a verified saved capture for the replay timeline.")
        replay = replays.select(body)
        if replay is None:
            raise ReceiptError("Open the matching saved capture to scan its replay timeline.")

        async def scan():
            try:
                await replay.verify_capture(checksum)
            except (ValueError, OSError) as exc:
                raise ReceiptError("The saved capture could not be verified for the replay timeline.") from exc
            timeline = await replay.timeline()
            return timeline

        return await run_bounded(request, scan, kind="investigation-timeline", locks=(replays.lock(replay),))

    async def receipts(request):
        if request.method == "GET":
            entries = app[STORE_KEY].list()
            if comparison_store is not None:
                by_id = {entry["id"]: entry for entry in [*entries, *comparison_store.list()]}
                entries = sorted(by_id.values(), key=lambda entry: (entry["created_at"], entry["id"]), reverse=True)
            return web.json_response({"receipts": entries})
        body = await read_body(request)
        if set(body) != {"name", "kind", "request"}:
            raise ReceiptError("Saving requires a name, kind and request.")
        kind = body["kind"]
        if kind in BLIND_OPERATIONS:
            raise ReceiptError("Save this kind of receipt from a blind review window.")
        sources, locks = calculation_sources(kind, body["request"])

        async def calculate_and_save():
            receipt = await make_receipt(body["name"], kind, body["request"],
                                         core=app[CORE_KEY], **sources)
            market = SAVED_INVESTIGATION_MARKETS.get(receipt["kind"])
            store = comparison_store if comparison_store is not None and market == replays.comparison_symbol else app[STORE_KEY]
            return store.save(receipt)

        return await run_bounded(request, calculate_and_save, kind=kind, locks=locks)

    async def receipt(request):
        receipt_id = request.match_info["id"]
        try:
            value = app[STORE_KEY].load(receipt_id)
        except FileNotFoundError:
            if comparison_store is None:
                raise
            value = comparison_store.load(receipt_id)
        response = web.json_response(value, dumps=lambda item: canonical_bytes(item).decode())
        if request.path.endswith("/export"):
            response.headers["Content-Disposition"] = 'attachment; filename="wind-tunnel-' + value["receipt_sha256"][:12] + '.json"'
        return response

    async def reproduce(request):
        body = await read_body(request)
        kind = body.get("kind")
        if kind in BLIND_OPERATIONS:
            raise ReceiptError("Open blind review mode to reopen this receipt in Wind Tunnel.")
        sources, locks = calculation_sources(kind, body.get("request"))
        return await run_bounded(request, lambda: reproduce_receipt(
            body, core=app[CORE_KEY], **sources), kind=kind, locks=locks)

    async def inspect_intake(request):
        if request.content_type != "application/octet-stream":
            raise ReceiptError("Select a captured-session file to inspect.")
        data = await read_intake_body(request)

        async def inspect():
            return app[INTAKE_KEY].inspect(data)

        return await run_bounded(request, inspect)

    async def intake_checkpoint(request):
        body = await read_body(request)
        if set(body) != {"intake_id", "sequence"}:
            raise ReceiptError("Choose an inspected session and checkpoint.")

        async def freeze():
            artifact = await app[INTAKE_KEY].checkpoint(body["intake_id"], body["sequence"])
            return {"terminal_checkpoint": artifact}

        return await run_bounded(request, freeze)

    async def discard_intake(request):
        app[INTAKE_KEY].discard(request.match_info["id"])
        return web.json_response({"status": "discarded"})

    async def cleanup(_):
        app[INTAKE_KEY].clear()
        app[STORE_KEY].close()
        if comparison_store is not None:
            comparison_store.close()
        replays.close()

    for path in app[ASSETS_KEY]:
        app.router.add_get(path, static_asset)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_get("/api/checkpoints", checkpoints)
    app.router.add_get("/api/examples", examples)
    app.router.add_post("/api/investigation-timeline", investigation_timeline)
    app.router.add_post(f"/api/{{kind:{'|'.join(OPERATIONS)}}}", calculate)
    app.router.add_get("/api/receipts", receipts)
    app.router.add_post("/api/receipts", receipts)
    app.router.add_get("/api/receipts/{id}", receipt)
    app.router.add_get("/api/receipts/{id}/export", receipt)
    app.router.add_post("/api/reproduce", reproduce)
    app.router.add_post("/api/intake", inspect_intake)
    app.router.add_post("/api/intake/checkpoint", intake_checkpoint)
    app.router.add_delete("/api/intake/{id}", discard_intake)
    app.on_cleanup.append(cleanup)
    # Initialize storage last so asset/route construction cannot leak its descriptor.
    app[STORE_KEY] = ReceiptStore(workspace)
    try:
        comparison_store = ReceiptStore(comparison_workspace) if comparison_workspace is not None else None
    except BaseException:
        app[STORE_KEY].close()
        raise
    return app


async def start_server(workspace: Path | str, *, port: int = 8765, core=None, saved_replay=None,
                       saved_replays=None, comparison_workspace: Path | str | None = None,
                       blind_review=None, blind_reviews=None, blind_study=None, blind_studies=None,
                       blind_study_pair=None):
    """Return (runner, launch_url); the caller must await runner.cleanup()."""
    if isinstance(port, bool) or not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    study_mode = any(mode is not None for mode in (blind_study, blind_studies, blind_study_pair))
    if study_mode and (blind_review is not None or blind_reviews is not None):
        raise ValueError("Choose either a blind study or a saved blind review.")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    runner = None
    try:
        listener.bind(("127.0.0.1", port))
        listener.setblocking(False)
        actual_port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{actual_port}"
        if study_mode:
            from .wind_tunnel_blind_study_server import create_study_app
            app = create_study_app(workspace, origin=origin, study=blind_study, studies=blind_studies,
                                   pair=blind_study_pair)
        elif blind_review is None and blind_reviews is None:
            app = create_app(workspace, origin=origin, core=core, saved_replay=saved_replay,
                             saved_replays=saved_replays, comparison_workspace=comparison_workspace)
        else:
            from .wind_tunnel_blind_server import create_blind_app
            app = create_blind_app(workspace, origin=origin, review=blind_review, reviews=blind_reviews)
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=5, handler_cancellation=True)
        await runner.setup()
        site = web.SockSite(runner, listener)
        await site.start()
        return runner, origin + "/#cap=" + app[TOKEN_KEY]
    except BaseException:
        if runner is not None:
            await runner.cleanup()
        listener.close()
        raise

"""Bounded, private Tradovate payload evidence; never adapter certification.

Only contract-library discovery and market-data quote subscriptions are used.
Authentication is reused in memory, but authentication payloads and headers are
never exported. Private captures still require manual rights/redaction review.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gex_terminal.adapters.tradovate import TradovateAdapter, validate_tradovate_credentials
from gex_terminal.capture_governance import capture_policy_identity
from gex_terminal.redaction import is_sensitive_key

CAPTURE_SCHEMA = "gex-terminal.tradovate-raw-capture.v1"
HEARTBEAT_SECONDS = 2.5
_CLEANUP_ALLOWANCE_SECONDS = 1.0
_MANIFEST_RESERVE = 16384
_PRIVATE_KEYS = {
    "account", "accountid", "accountids", "accountnumber", "userid", "userids",
    "username", "password", "token", "accesstoken", "mdaccesstoken", "authorization",
    "secret", "sec", "apikey", "appsecret", "clientsecret", "customerid", "email",
    "subscriptionid", "pticket", "paccesskey",
    "cid", "appid", "applicationid", "appversion",
}
_GET_PATHS = {"product/find", "contractMaturity/deps", "contract/deps"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_int(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{label} must be an integer from {lower} through {upper}")
    return value


def _duration(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("duration_seconds must be finite, positive, and at most 300")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError("duration_seconds must be finite, positive, and at most 300") from None
    if not math.isfinite(result) or not 0 < result <= 300:
        raise ValueError("duration_seconds must be finite, positive, and at most 300")
    return result


def _identifier(value: Any) -> int | None:
    return value if type(value) is int and 0 < value < 2**63 else None


def _validate_websocket_target(websocket) -> None:
    """Pin authorization to the exact provider endpoint after any handshake.

    Modern websockets clients may follow cross-origin redirects. They don't
    know that a later application-level message will contain an access token.
    Check the final negotiated target before sending any application message;
    unknown client identity interfaces fail closed as well.
    """
    protocol = getattr(websocket, "protocol", None)
    uri = getattr(protocol, "uri", None)
    if uri is not None:
        secure = getattr(uri, "secure", None)
        host = getattr(uri, "host", None)
        port = getattr(uri, "port", None)
        path = getattr(uri, "resource_name", None)
        user_info = getattr(uri, "user_info", "unreported")
    else:
        secure = getattr(websocket, "secure", None)
        host = getattr(websocket, "host", None)
        port = getattr(websocket, "port", None)
        path = getattr(websocket, "path", None)
        user_info = getattr(websocket, "user_info", None)
        # Legacy protocols don't retain parsed URI userinfo, but handshake
        # userinfo creates an HTTP Authorization header. We never supply one.
        headers = getattr(websocket, "request_headers", None)
        if not isinstance(headers, Mapping) or any(str(key).lower() == "authorization" for key in headers):
            raise _CaptureStop("websocket_target_rejected")
    if (secure is not True or host != "md.tradovateapi.com" or type(port) is not int
            or port != 443 or path != "/v1/websocket" or user_info is not None):
        raise _CaptureStop("websocket_target_rejected")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonstandard JSON constant")


def _decoder() -> json.JSONDecoder:
    return json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=_constant)


def _unsafe(value: Any, secrets: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if is_sensitive_key(key) or normalized in _PRIVATE_KEYS:
                return True
            if normalized in {"error", "errortext", "errormessage", "errorreason", "failurereason"} and child:
                return True
            if _unsafe(key, secrets) or _unsafe(child, secrets):
                return True
        return False
    if isinstance(value, list):
        return any(_unsafe(child, secrets) for child in value)
    if isinstance(value, str):
        return any(secret in value for secret in secrets)
    return False


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return [value] if isinstance(value, dict) else []


class _CaptureStop(Exception):
    def __init__(self, reason: str):
        self.reason = reason


class _PrivateCapture:
    def __init__(self, path: Path, limit: int):
        # Walk existing parents without following links. Parents are never
        # created implicitly: the operator must choose an existing private area.
        path = Path(os.path.abspath(path))
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("capture destination must not contain symlinks")
            if (parent / ".git").exists():
                raise ValueError("raw capture destination must be outside Git checkouts")
        if not path.parent.is_dir():
            raise ValueError("capture destination requires an existing parent directory")
        try:
            os.mkdir(path, mode=0o700)
        except FileExistsError:
            raise ValueError("capture destination must be a new directory") from None
        os.chmod(path, 0o700)
        self.path = path
        self.dir_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.limit = limit - _MANIFEST_RESERVE
        self.bytes_written = 0
        self.handles = {}
        try:
            for name in ("rest.jsonl", "websocket.jsonl"):
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.dir_fd)
                self.handles[name] = os.fdopen(fd, "wb")
        except BaseException:
            self.close()
            os.close(self.dir_fd)
            raise

    def write(self, name: str, record: dict[str, Any]) -> None:
        data = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if self.bytes_written + len(data) > self.limit:
            raise _CaptureStop("byte_limit")
        self.handles[name].write(data)
        self.handles[name].flush()
        self.bytes_written += len(data)

    def close(self):
        for handle in self.handles.values():
            handle.close()

    def finish(self, manifest: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._finish(manifest)
        finally:
            os.close(self.dir_fd)

    def _finish(self, manifest: dict[str, Any]) -> dict[str, Any]:
        self.close()
        manifest["files"] = {}
        for name in ("rest.jsonl", "websocket.jsonl"):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.dir_fd)
            with os.fdopen(fd, "rb") as handle:
                content = handle.read()
            manifest["files"][name] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(data) > _MANIFEST_RESERVE:
            raise RuntimeError("capture manifest exceeded its reserved byte allowance")
        fd = os.open("manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.dir_fd)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return manifest


class _Collector:
    def __init__(self, adapter, writer, manifest):
        self.adapter = adapter
        self.writer = writer
        self.manifest = manifest
        self.limits = manifest["limits"]
        self.counts = manifest["counts"]
        self.websocket = None
        self.auth_request_id = 1
        self.subscription_ids: set[int] = set()
        self.active: list[int] = []
        self.secrets: tuple[str, ...] = ()
        self.quoted_contract_ids: set[int] = set()
        self.joined_option_contract_ids: set[int] = set()
        self.heartbeat_task = None
        self.selected_ids: set[int] = set()

    def _refresh_secrets(self):
        # Do not use short numeric client IDs as substring redactors: they are
        # legitimate contract metadata too. Credential string values, including
        # short passwords/tokens, are always protected.
        values = [value for key, value in self.adapter.auth_payload.items()
                  if key not in {"cid", "appVersion"} and isinstance(value, str) and value]
        values.extend(value for value in (self.adapter.access_token, self.adapter.md_access_token)
                      if isinstance(value, str) and value)
        self.secrets = tuple(values)

    def _omit(self, kind: str):
        self.counts[kind] += 1

    async def request(self, session, method: str, path: str, arguments: dict[str, Any]):
        if not ((method == "GET" and path in _GET_PATHS) or
                (method == "POST" and path == "contract/getoptionschain")):
            raise ValueError("capture request is outside the contract-library allowlist")
        if path == "product/find":
            valid = arguments == {"name": self.manifest["target"]["symbol"]}
        else:
            key = "contractId" if method == "POST" else "masterid"
            valid = set(arguments) == {key} and _identifier(arguments[key]) is not None
        if not valid:
            raise ValueError("capture request arguments are not allowlisted")
        if self.counts["rest_requests"] >= self.limits["max_requests"]:
            raise _CaptureStop("request_limit")
        self.counts["rest_requests"] += 1
        kwargs = {"json" if method == "POST" else "params": arguments, "allow_redirects": False}
        async with session.request(method, f"{self.adapter.rest_url}/{path}", **kwargs) as response:
            record = {"received_at": _utcnow(), "method": method, "path": path,
                      "arguments": arguments, "http_status": response.status}
            if response.status != 200:
                record["omission"] = "non_success_body"
                self.writer.write("rest.jsonl", record)
                self._omit("rest_bodies_omitted")
                return None
            chunks = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                chunks.extend(chunk)
                if len(chunks) > self.limits["max_frame_bytes"]:
                    raise _CaptureStop("response_size_limit")
            try:
                raw = chunks.decode("utf-8")
                payload = _decoder().decode(raw)
                if not isinstance(payload, (dict, list)):
                    raise ValueError("unsupported JSON root")
                if _unsafe(payload, self.secrets):
                    raise ValueError("private field or credential")
                if isinstance(payload, dict) and (payload.get("errorText") or payload.get("error")):
                    raise ValueError("provider error body")
            except (UnicodeError, ValueError, TypeError, RecursionError):
                record["omission"] = "unsafe_or_invalid_json_body"
                self.writer.write("rest.jsonl", record)
                self._omit("rest_bodies_omitted")
                return None
            record["raw_body"] = raw
            self.writer.write("rest.jsonl", record)
            self.counts["rest_bodies_captured"] += 1
            return payload

    async def discover(self, session) -> list[int]:
        product = await self.request(session, "GET", "product/find", {"name": self.manifest["target"]["symbol"]})
        products = _rows(product)
        product_id = next((_identifier(row.get("id")) for row in products if _identifier(row.get("id"))), None)
        if product_id is None:
            raise _CaptureStop("no_product")
        maturities = await self.request(session, "GET", "contractMaturity/deps", {"masterid": product_id})
        now = _utcnow()
        available = [row for row in _rows(maturities) if _identifier(row.get("id"))]
        # Prefer unexpired dated maturities, while retaining undated entries as
        # evidence rather than requiring the normalizer's expiry contract.
        available = [row for row in available if not isinstance(row.get("expirationDate"), str)
                     or row["expirationDate"][:10] >= now[:10]]
        available.sort(key=lambda row: (row.get("isFront") is not True, str(row.get("expirationDate", "9999"))))
        if len(available) > self.limits["max_maturities"]:
            self.manifest["selection"]["maturity_selection_limited"] = True
        selected_futures = []
        options = []
        seen_options: set[int] = set()
        for maturity in available[:self.limits["max_maturities"]]:
            contracts = await self.request(session, "GET", "contract/deps", {"masterid": maturity["id"]})
            underlying = next((row for row in _rows(contracts) if _identifier(row.get("id"))), None)
            if underlying is None:
                continue
            underlying_id = underlying["id"]
            if underlying_id not in selected_futures:
                selected_futures.append(underlying_id)
            chain = await self.request(session, "POST", "contract/getoptionschain", {"contractId": underlying_id})
            if not isinstance(chain, dict):
                continue
            option_products = {row["id"] for row in _rows(chain.get("products"))
                               if _identifier(row.get("id")) and str(row.get("productType", "")).lower() == "options"}
            option_maturities = {row["id"] for row in _rows(chain.get("contractMaturities"))
                                 if _identifier(row.get("id")) and
                                 (_identifier(row.get("productId")) in option_products or _identifier(row.get("underlyingId")) == underlying_id)}
            chain_contracts = [row for row in _rows(chain.get("contracts"))
                               if _identifier(row.get("id")) and row["id"] != underlying_id]
            joined = [row for row in chain_contracts if _identifier(row.get("contractMaturityId")) in option_maturities]
            self.joined_option_contract_ids.update(row["id"] for row in joined)
            # Missing metadata is the issue being investigated: preserve the
            # response and sample IDs even when joins cannot be established.
            candidates = joined or chain_contracts
            if candidates and not joined:
                self.manifest["selection"]["unclassified_chain_contracts_sampled"] = True
            for row in candidates:
                if row["id"] not in seen_options:
                    seen_options.add(row["id"])
                    options.append(row["id"])
        if len(options) > self.limits["max_option_contracts"]:
            self.manifest["selection"]["option_selection_limited"] = True
        options = options[:self.limits["max_option_contracts"]]
        self.manifest["selection"]["underlying_contract_ids"] = selected_futures
        self.manifest["selection"]["chain_contract_ids"] = options
        self.manifest["selection"]["joined_option_contract_ids"] = [value for value in options if value in self.joined_option_contract_ids]
        subscriptions = list(dict.fromkeys(selected_futures + options))
        if not subscriptions:
            raise _CaptureStop("no_subscribable_contracts")
        self.selected_ids = set(subscriptions)
        return subscriptions

    def frame(self, raw: Any) -> list[dict[str, Any]]:
        if self.counts["frames_received"] >= self.limits["max_frames"]:
            raise _CaptureStop("frame_limit")
        self.counts["frames_received"] += 1
        if not isinstance(raw, str):
            self._omit("frames_omitted")
            return []
        if len(raw.encode("utf-8")) > self.limits["max_frame_bytes"]:
            raise _CaptureStop("frame_size_limit")
        if raw in {"o", "h", "[]"}:
            self.counts["control_frames_omitted"] += 1
            return []
        try:
            if not raw or raw[0] not in {"a", "m"}:
                raise ValueError("unsupported wire frame")
            text = raw[1:]
            decoded = _decoder().decode(text)
            if not isinstance(decoded, (dict, list)):
                raise ValueError("unsupported frame root")
            events = decoded if isinstance(decoded, list) else [decoded]
            # Find exact event substrings so mixed frames can exclude auth ACKs
            # without reconstructing or changing market event field ordering.
            spans = []
            first = len(text) - len(text.lstrip())
            position = first + 1 if isinstance(decoded, list) else first
            decoder = _decoder()
            for event in events:
                while position < len(text) and text[position] in " \t\r\n,":
                    position += 1
                start = position
                _value, position = decoder.raw_decode(text, position)
                spans.append(text[start:position])
            retained = []
            for index, event in enumerate(events):
                # Never export authorization ACKs, including empty bodies.
                if isinstance(event, dict) and type(event.get("i")) is int and event["i"] == self.auth_request_id:
                    self.counts["authorization_events_omitted"] += 1
                    continue
                if not isinstance(event, dict) or _unsafe(event, self.secrets):
                    self.counts["unsafe_or_unsupported_events_omitted"] += 1
                    continue
                market = event.get("e") == "md" and isinstance(event.get("d"), dict) and isinstance(event["d"].get("quotes"), list)
                acknowledgement = (type(event.get("i")) is int and event["i"] in self.subscription_ids
                                   and type(event.get("s")) is int and event["s"] == 200
                                   and event.get("d") in (None, {}))
                if market or acknowledgement:
                    retained.append({"event_index": index, "raw_event": spans[index]})
                else:
                    self.counts["unsafe_or_unsupported_events_omitted"] += 1
            omitted = len(events) - len(retained)
            self.counts["events_omitted"] += omitted
            if retained:
                record = {"received_at": _utcnow(), "frame_index": self.counts["frames_received"] - 1,
                          "frame_prefix": raw[0], "source_event_count": len(events),
                          "omitted_event_count": omitted, "events": retained,
                          "raw_frame": raw if not omitted else None}
                self.writer.write("websocket.jsonl", record)
                self.counts["frames_captured"] += 1
                for item in retained:
                    event = events[item["event_index"]]
                    if event.get("e") == "md":
                        self.counts["market_data_events_captured"] += 1
                        for quote in event["d"]["quotes"]:
                            if not isinstance(quote, dict):
                                continue
                            contract_id = _identifier(quote.get("contractId"))
                            if contract_id in self.selected_ids:
                                self.quoted_contract_ids.add(contract_id)
                self.manifest["observed"]["quoted_contract_ids"] = sorted(self.quoted_contract_ids)
                self.manifest["observed"]["joined_option_quote_contract_ids"] = sorted(self.quoted_contract_ids & self.joined_option_contract_ids)
            elif len(events) != sum(1 for event in events if isinstance(event, dict) and type(event.get("i")) is int and event["i"] == self.auth_request_id):
                self._omit("frames_omitted")
            return [event for event in events if isinstance(event, dict)]
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self._omit("frames_omitted")
            return []

    async def receive(self):
        if self.counts["frames_received"] >= self.limits["max_frames"]:
            raise _CaptureStop("frame_limit")
        if self.heartbeat_task is None:
            raw = await self.websocket.recv()
        else:
            recv_task = asyncio.create_task(self.websocket.recv())
            try:
                done, _pending = await asyncio.wait({recv_task, self.heartbeat_task}, return_when=asyncio.FIRST_COMPLETED)
                if self.heartbeat_task in done:
                    await self.heartbeat_task
                    raise _CaptureStop("heartbeat_stopped")
                raw = await recv_task
            finally:
                if not recv_task.done():
                    recv_task.cancel()
                # Retrieve a simultaneous receive failure even when heartbeat
                # failure won the race, preserving the original active error.
                try:
                    await recv_task
                except (Exception, asyncio.CancelledError):
                    pass
        events = self.frame(raw)
        return raw, events

    async def heartbeat(self):
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            await self.websocket.send("[]")

    async def authenticate(self, aiohttp):
        validate_tradovate_credentials()
        timeout = aiohttp.ClientTimeout(total=min(15.0, self.limits["duration_seconds"]))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request("POST", f"{self.adapter.rest_url}/auth/accesstokenrequest",
                                       json=self.adapter.auth_payload, allow_redirects=False) as response:
                if response.status != 200:
                    return False
                content = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    content.extend(chunk)
                    if len(content) > self.limits["max_frame_bytes"]:
                        raise _CaptureStop("authentication_response_size_limit")
                try:
                    payload = _decoder().decode(content.decode("utf-8"))
                    if not isinstance(payload, dict) or not isinstance(payload.get("accessToken"), str) or not payload["accessToken"]:
                        return False
                    md_token = payload.get("mdAccessToken")
                    if md_token is not None and (not isinstance(md_token, str) or not md_token):
                        return False
                    self.adapter._apply_token_payload(payload)
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    return False
                return True

    async def ack(self, request_id: int):
        while True:
            raw, events = await self.receive()
            if raw == "h":
                await self.websocket.send("[]")
            acknowledgement = None
            for event in events:
                if event.get("e") in {"error", "md/error"}:
                    raise _CaptureStop("provider_error")
                if type(event.get("i")) is int and event["i"] == request_id:
                    if type(event.get("s")) is not int or event["s"] != 200:
                        raise _CaptureStop("authorization_rejected" if request_id == self.auth_request_id else "subscription_rejected")
                    acknowledgement = event
            if acknowledgement is not None:
                return

    async def run(self):
        import aiohttp
        import websockets

        if not await self.authenticate(aiohttp):
            raise _CaptureStop("authentication_failed")
        self.manifest["authentication_passed"] = True
        self._refresh_secrets()
        timeout = aiohttp.ClientTimeout(total=min(15.0, self.limits["duration_seconds"]))
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {self.adapter.access_token}"}, timeout=timeout) as session:
            subscriptions = await self.discover(session)
        private_logger = logging.Logger("gex_terminal.tradovate_capture.websocket", level=logging.CRITICAL + 1)
        private_logger.propagate = False
        private_logger.addHandler(logging.NullHandler())
        self.websocket = await websockets.connect(
            self.adapter.ws_url, open_timeout=min(15.0, self.limits["duration_seconds"]),
            close_timeout=0.5, max_size=self.limits["max_frame_bytes"], max_queue=16,
            logger=private_logger,
        )
        _validate_websocket_target(self.websocket)
        self.heartbeat_task = asyncio.create_task(self.heartbeat())
        while True:
            raw, _events = await self.receive()
            if raw == "o":
                break
            if raw != "h" and raw != "[]":
                raise _CaptureStop("invalid_open_frame")
        await self.websocket.send(f"authorize\n1\n\n{self.adapter.md_access_token}")
        await self.ack(1)
        self.manifest["websocket_authorized"] = True
        for request_id, contract_id in enumerate(subscriptions, start=2):
            self.subscription_ids.add(request_id)
            await self.websocket.send(f"md/subscribeQuote\n{request_id}\n\n" + json.dumps({"symbol": contract_id}, separators=(",", ":")))
            await self.ack(request_id)
            self.active.append(contract_id)
            self.counts["subscriptions_acknowledged"] += 1
        self.manifest["subscriptions_completed"] = True
        while True:
            raw, events = await self.receive()
            if raw == "h":
                await self.websocket.send("[]")
            if any(event.get("e") in {"error", "md/error"} for event in events):
                raise _CaptureStop("provider_error")

    async def close(self):
        if self.websocket is None:
            return
        try:
            async with asyncio.timeout(_CLEANUP_ALLOWANCE_SECONDS):
                if self.heartbeat_task is not None:
                    cancelling = asyncio.current_task().cancelling()
                    self.heartbeat_task.cancel()
                    try:
                        await self.heartbeat_task
                    except asyncio.CancelledError:
                        if asyncio.current_task().cancelling() > cancelling:
                            raise
                    except Exception:
                        pass
                for offset, contract_id in enumerate(self.active, start=1000):
                    await self.websocket.send(f"md/unsubscribeQuote\n{offset}\n\n" + json.dumps({"symbol": contract_id}, separators=(",", ":")))
                await self.websocket.close()
                self.manifest["cleanup_completed"] = True
        except BaseException:
            self.manifest["cleanup_completed"] = False
            transport = getattr(self.websocket, "transport", None)
            abort = getattr(transport, "abort", None)
            if callable(abort):
                abort()
            raise


async def capture_tradovate_payloads(
    output_dir: str | Path,
    *,
    symbol: str = "ES",
    environment: str = "demo",
    capture_policy: Mapping[str, Any],
    ack_live_network: bool = False,
    duration_seconds: float = 60.0,
    max_option_contracts: int = 12,
    max_maturities: int = 2,
    max_requests: int = 12,
    max_frames: int = 1000,
    max_total_bytes: int = 16777216,
    max_frame_bytes: int = 1048576,
) -> dict[str, Any]:
    """Collect bounded private raw evidence without placing or changing orders.

    ``duration_seconds`` covers authentication, discovery, and streaming; socket
    cleanup has a separately bounded one-second allowance. All preflight checks
    precede credential construction or network access. The returned manifest
    never establishes payload coverage, certification, or issue closure.
    """
    if ack_live_network is not True:
        raise ValueError("Tradovate capture requires --ack-live-network")
    if not isinstance(symbol, str) or symbol.upper() not in {"ES", "NQ"}:
        raise ValueError("Tradovate raw capture symbol must be ES or NQ")
    if not isinstance(environment, str) or environment not in {"demo", "live"}:
        raise ValueError("Tradovate environment must be demo or live")
    limits = {
        "duration_seconds": _duration(duration_seconds),
        "max_option_contracts": _bounded_int(max_option_contracts, "max_option_contracts", 1, 60),
        "max_maturities": _bounded_int(max_maturities, "max_maturities", 1, 12),
        "max_requests": _bounded_int(max_requests, "max_requests", 1, 64),
        "max_frames": _bounded_int(max_frames, "max_frames", 1, 10000),
        "max_total_bytes": _bounded_int(max_total_bytes, "max_total_bytes", 32768, 67108864),
        "max_frame_bytes": _bounded_int(max_frame_bytes, "max_frame_bytes", 1024, 16777216),
        "cleanup_allowance_seconds": _CLEANUP_ALLOWANCE_SECONDS,
    }
    policy_identity = capture_policy_identity(capture_policy)
    # No consumer or normalized adapter discovery is used by this collector.
    writer = _PrivateCapture(Path(output_dir), max_total_bytes)
    manifest = {
        "schema": CAPTURE_SCHEMA, "started_at": _utcnow(), "finished_at": None,
        "target": {"provider": "tradovate", "symbol": symbol.upper(), "environment": environment},
        "capture_policy": policy_identity, "limits": limits,
        "read_only": True, "orders_touched": False, "adapter_registry_status": "scaffold",
        "authentication_passed": False, "websocket_authorized": False,
        "subscriptions_completed": False, "cleanup_completed": True,
        "status": "failed", "outcome": "started", "truncated": False, "error_type": None,
        "counts": {name: 0 for name in ("rest_requests", "rest_bodies_captured", "rest_bodies_omitted",
                   "frames_received", "frames_captured", "frames_omitted", "control_frames_omitted",
                   "events_omitted", "market_data_events_captured", "subscriptions_acknowledged",
                   "authorization_events_omitted", "unsafe_or_unsupported_events_omitted")},
        "selection": {"maturity_selection_limited": False, "option_selection_limited": False,
                      "unclassified_chain_contracts_sampled": False, "option_classification_verified": False,
                      "underlying_contract_ids": [], "chain_contract_ids": [], "joined_option_contract_ids": []},
        "observed": {"quoted_contract_ids": [], "joined_option_quote_contract_ids": []},
        "review": {"redaction_status": "unreviewed", "redistribution_approved": False,
                   "actual_es_nq_payload_validation_complete": False, "issue_4_may_close": False},
        "omissions": ["authentication requests/responses and headers", "outgoing WebSocket frames",
                      "authorization ACK events", "provider error/free-text bodies", "known private keys or credential literals",
                      "invalid, duplicate-key, nonstandard or oversized JSON", "unsupported non-quote events and control frames"],
        "evidence_ceiling": "Private bounded sample only; no normalization, IV inference, certification, or full-chain coverage claim.",
    }
    collector = None
    cancelled = False
    deadline = asyncio.timeout(limits["duration_seconds"])
    try:
        adapter = TradovateAdapter(None, target_underlying=symbol.upper(), environment=environment,
                                   max_http_attempts=1, max_reconnect_attempts=0,
                                   request_timeout_seconds=min(15.0, limits["duration_seconds"]))
        collector = _Collector(adapter, writer, manifest)
        async with deadline:
            await collector.run()
        manifest["outcome"] = "connection_ended"
    except TimeoutError:
        manifest["outcome"] = "duration_limit" if deadline.expired() else "transport_timeout"
        manifest["truncated"] = deadline.expired()
    except _CaptureStop as exc:
        manifest["outcome"] = exc.reason
        manifest["truncated"] = exc.reason.endswith("limit")
    except asyncio.CancelledError:
        manifest["outcome"] = "cancelled"
        manifest["truncated"] = True
        cancelled = True
    except Exception as exc:
        manifest["outcome"] = "capture_failed"
        manifest["error_type"] = type(exc).__name__
    finally:
        if collector is not None:
            try:
                await collector.close()
            except asyncio.CancelledError:
                manifest["outcome"] = "cancelled"
                manifest["truncated"] = True
                cancelled = True
            except Exception:
                manifest["cleanup_completed"] = False
        if manifest["authentication_passed"]:
            manifest["status"] = "partial"
        if (manifest["outcome"] == "duration_limit" and manifest["subscriptions_completed"]
                and manifest["observed"]["joined_option_quote_contract_ids"]
                and not manifest["counts"]["rest_bodies_omitted"]
                and not manifest["counts"]["frames_omitted"]
                and not manifest["counts"]["unsafe_or_unsupported_events_omitted"]
                and manifest["cleanup_completed"]):
            manifest["status"] = "complete"
        manifest["finished_at"] = _utcnow()
        writer.finish(manifest)
    if cancelled:
        raise asyncio.CancelledError
    return manifest

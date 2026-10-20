"""Quote or explicitly acquire one bounded ES/NQ historical Globex session.

Quotes use metadata only. Downloads require the saved, integrity-checked plan,
a fresh quote, an operator-confirmed credit balance and ``--use-credits``.
No live API, automatic retry, replacement or narrower fallback is used.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import sys
from typing import Any, Mapping
import uuid
import warnings
from zoneinfo import ZoneInfo

from gex_terminal.adapters.databento import databento_option_parent_symbols
from scripts.databento_trial_download import DATASET, DATA_ROOT, TrialRequestError, TrialSetupError, read_key


PLAN_SCHEMA = "gex-terminal.databento-session-plan.v1"
DOWNLOAD_SCHEMA = "gex-terminal.databento-session-download.v1"
MAX_RECORDS_PER_MARKET = 5_000_000
MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COST_USD = 5.0
ROLES = (("definitions", "definition"), ("underlying", "bbo-1s"), ("trades", "trades"))
MARKETS = ("ES", "NQ")
CALENDAR_SCOPE = "requested_17_to_16_Chicago_window; holiday_hours_not_verified"
COVERAGE_SCOPE = "all_application_supported_option_parents; one_matched_future_per_market; trades_only_no_OI; full_chain_unverified"
DEFAULT_CACHED = {symbol: DATA_ROOT / "broader-20261019" / "acquisition" / symbol.lower() / "underlying.dbn"
                  for symbol in MARKETS}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical({k: v for k, v in value.items() if k != "plan_sha256"})).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TrialSetupError("Metadata must contain timezone-bearing dataset bounds.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TrialSetupError("Metadata contains an invalid dataset bound.") from None
    if parsed.tzinfo is None:
        raise TrialSetupError("Metadata must contain timezone-bearing dataset bounds.")
    return parsed.astimezone(timezone.utc)


def session_window(trading_date: str, *, now: datetime | None = None) -> dict[str, str]:
    try:
        day = date.fromisoformat(trading_date)
    except (TypeError, ValueError):
        raise TrialSetupError("Use a trading date in YYYY-MM-DD form.") from None
    if day.isoformat() != trading_date or day.weekday() >= 5:
        raise TrialSetupError("Choose a Monday-through-Friday trading date; holiday hours require separate verification.")
    chicago = ZoneInfo("America/Chicago")
    start = datetime.combine(day - timedelta(days=1), time(17), chicago).astimezone(timezone.utc)
    end = datetime.combine(day, time(16), chicago).astimezone(timezone.utc)
    if end > (now or datetime.now(timezone.utc)) - timedelta(hours=24):
        raise TrialSetupError("Choose a completed historical session at least 24 hours old.")
    lookback = datetime.combine(day - timedelta(days=2), time(), timezone.utc)
    return {"start": _iso(start), "end": _iso(end), "definition_start": _iso(lookback),
            "underlying_start": _iso(start - timedelta(seconds=2))}


def _integer(value: Any, name: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value <= 0 or (maximum is not None and value > maximum):
        raise TrialSetupError(f"Invalid or excessive {name}; no market data requested.")
    return value


def _cost(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise TrialSetupError("Provider returned an invalid cost estimate; no market data requested.")
    return float(value)


def cached_underlying_identity(path: Path, symbol: str, *, store_factory=None) -> dict:
    """Read an already-owned BBO file; this function never resolves a symbol remotely."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 64 * 1024 * 1024:
        raise TrialSetupError("Cached underlying must be a bounded ordinary DBN file.")
    if store_factory is None:
        import databento as db
        store_factory = db.DBNStore.from_file
    store = store_factory(path)
    try:
        metadata = store.metadata
        if str(metadata.schema) != "bbo-1s" or list(metadata.symbols) != [f"{symbol}.v.0"]:
            raise TrialSetupError("Cached BBO metadata does not match the selected market.")
        identities = set()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            for number, record in enumerate(store, 1):
                if number > MAX_RECORDS_PER_MARKET:
                    raise TrialSetupError("Cached BBO file exceeds the record bound.")
                identities.add(_integer(record.instrument_id, "cached futures instrument ID"))
        if len(identities) != 1:
            raise TrialSetupError("Cached BBO file must identify exactly one futures contract.")
    except TrialSetupError:
        raise
    except Exception:
        raise TrialSetupError("Cached BBO file could not be decoded completely.") from None
    finally:
        store.reader.close()
    return {"instrument_id": identities.pop(), "cached_sha256": _sha_file(path),
            "cached_schema": "bbo-1s", "cached_symbol": f"{symbol}.v.0"}


def requests_for(symbol: str, window: Mapping[str, str], instrument_id: int) -> list[dict]:
    parents = list(databento_option_parent_symbols(symbol))
    common = {"dataset": DATASET}
    return [
        {**common, "schema": "definition", "stype_in": "parent", "symbols": parents + [symbol + ".FUT"],
         "start": window["definition_start"], "end": window["end"]},
        {**common, "schema": "bbo-1s", "stype_in": "instrument_id", "symbols": [instrument_id],
         "start": window["underlying_start"], "end": window["end"]},
        {**common, "schema": "trades", "stype_in": "parent", "symbols": parents,
         "start": window["start"], "end": window["end"]},
    ]


def _quote_one(client, request: dict) -> dict:
    try:
        count = client.metadata.get_record_count(**request)
        size = client.metadata.get_billable_size(**request)
        count = _integer(count, "metadata record count", maximum=MAX_RECORDS_PER_MARKET)
        size = _integer(size, "metadata billable byte count")
        quoted = {**request, "limit": count + 1}
        cost = _cost(client.metadata.get_cost(**quoted))
    except TrialSetupError:
        raise
    except Exception as exc:
        raise TrialRequestError("quote", request["schema"], exc) from None
    return {"request": quoted, "record_count": count, "billable_bytes": size, "estimated_cost_usd": cost}


def quote_plan(client, trading_date: str, identities: Mapping[str, dict], *, now: datetime | None = None) -> dict:
    window = session_window(trading_date, now=now)
    try:
        bounds = client.metadata.get_dataset_range(DATASET)
        availability = {key: _iso(_timestamp(bounds[key])) for key in ("start", "end")}
    except TrialSetupError:
        raise
    except Exception as exc:
        raise TrialRequestError("quote", "definition", exc) from None
    if (_timestamp(window["definition_start"]) < _timestamp(availability["start"])
            or _timestamp(window["end"]) > _timestamp(availability["end"])):
        raise TrialSetupError("Requested historical window is outside dataset availability; no data requested.")
    markets = []
    for symbol in MARKETS:
        identity = identities[symbol]
        requests = [_quote_one(client, request) for request in requests_for(symbol, window, identity["instrument_id"])]
        if sum(item["record_count"] for item in requests) > MAX_RECORDS_PER_MARKET:
            raise TrialSetupError(f"{symbol} metadata exceeds the 5000000-record market bound; no data requested.")
        markets.append({"symbol": symbol, "option_parents": list(databento_option_parent_symbols(symbol)),
                        "underlying_identity": dict(identity), "requests": requests})
    total = math.fsum(item["estimated_cost_usd"] for market in markets for item in market["requests"])
    result = {"schema": PLAN_SCHEMA, "created_at": _iso(now or datetime.now(timezone.utc)),
              "trading_date": trading_date, "dataset": DATASET, "window": window,
              "calendar": CALENDAR_SCOPE,
              "dataset_availability": availability, "metadata_only": True,
              "max_cost_usd": MAX_COST_USD, "max_records_per_market": MAX_RECORDS_PER_MARKET,
              "max_compressed_bytes": MAX_COMPRESSED_BYTES, "markets": markets,
              "estimated_total_usd": total, "status": "quoted" if total <= MAX_COST_USD else "over_budget",
              "coverage": COVERAGE_SCOPE}
    result["plan_sha256"] = _digest(result)
    validate_plan(result, now=now, require_budget=False)
    return result


def validate_plan(plan: Any, *, now: datetime | None = None, require_budget: bool = True) -> dict:
    try:
        expected_keys = {"schema", "created_at", "trading_date", "dataset", "window", "calendar", "dataset_availability",
                         "metadata_only", "max_cost_usd", "max_records_per_market", "max_compressed_bytes", "markets",
                         "estimated_total_usd", "status", "coverage", "plan_sha256"}
        if (not isinstance(plan, dict) or set(plan) != expected_keys or plan["schema"] != PLAN_SCHEMA
                or plan["dataset"] != DATASET or plan["metadata_only"] is not True
                or plan["calendar"] != CALENDAR_SCOPE or plan["coverage"] != COVERAGE_SCOPE
                or plan["max_cost_usd"] != MAX_COST_USD or plan["max_records_per_market"] != MAX_RECORDS_PER_MARKET
                or plan["max_compressed_bytes"] != MAX_COMPRESSED_BYTES or plan["plan_sha256"] != _digest(plan)
                or plan["window"] != session_window(plan["trading_date"], now=now)
                or not isinstance(plan["markets"], list) or len(plan["markets"]) != 2):
            raise TrialSetupError("Saved session plan has invalid scope or integrity; create a new quote.")
        _timestamp(plan["created_at"])
        availability = plan["dataset_availability"]
        if (not isinstance(availability, dict) or set(availability) != {"start", "end"}
                or _timestamp(availability["start"]) > _timestamp(plan["window"]["definition_start"])
                or _timestamp(availability["end"]) < _timestamp(plan["window"]["end"])):
            raise TrialSetupError("Saved session plan exceeds its quoted dataset availability.")
        total = []
        for market, symbol in zip(plan["markets"], MARKETS):
            identity = market["underlying_identity"]
            if (set(market) != {"symbol", "option_parents", "underlying_identity", "requests"}
                    or market["symbol"] != symbol or market["option_parents"] != list(databento_option_parent_symbols(symbol))
                    or set(identity) != {"instrument_id", "cached_sha256", "cached_schema", "cached_symbol"}
                    or identity["cached_schema"] != "bbo-1s" or identity["cached_symbol"] != f"{symbol}.v.0"
                    or not isinstance(identity["cached_sha256"], str) or len(identity["cached_sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in identity["cached_sha256"])
                    or not isinstance(market["requests"], list) or len(market["requests"]) != 3):
                raise TrialSetupError("Saved session plan changes the permitted market scope.")
            instrument = _integer(identity["instrument_id"], "futures instrument ID")
            for item, expected in zip(market["requests"], requests_for(symbol, plan["window"], instrument)):
                if set(item) != {"request", "record_count", "billable_bytes", "estimated_cost_usd"}:
                    raise TrialSetupError("Saved session quote fields are invalid.")
                count = _integer(item["record_count"], "metadata record count", maximum=MAX_RECORDS_PER_MARKET)
                _integer(item["billable_bytes"], "metadata billable bytes")
                if item["request"] != {**expected, "limit": count + 1}:
                    raise TrialSetupError("Saved session request differs from the reviewed scope.")
                total.append(_cost(item["estimated_cost_usd"]))
            if sum(item["record_count"] for item in market["requests"]) > MAX_RECORDS_PER_MARKET:
                raise TrialSetupError("Saved session plan exceeds the per-market record bound.")
        if plan["estimated_total_usd"] != math.fsum(total) or plan["status"] != ("quoted" if math.fsum(total) <= MAX_COST_USD else "over_budget"):
            raise TrialSetupError("Saved session quote total is inconsistent.")
        if require_budget and plan["status"] != "quoted":
            raise TrialSetupError("All-parent quote exceeds the USD 5 ceiling; no narrower fallback or download was made.")
        return json.loads(_canonical(plan))
    except TrialSetupError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise TrialSetupError("Saved session plan is invalid; create a new quote.") from None


def private_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically create an owner-only receipt without replacing any target."""
    content = _canonical(value) + b"\n"
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def read_plan(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 1024 * 1024:
            raise TrialSetupError("Saved quote must be a bounded ordinary JSON file.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise TrialSetupError("Saved quote exceeds the JSON size bound.")
        return json.loads(content, object_pairs_hook=_unique_fields)
    finally:
        os.close(descriptor)


@contextmanager
def _file_size_limit(maximum: int):
    """Bound the SDK's on-disk output before it returns a readable DBN store."""
    import resource
    previous = resource.getrlimit(resource.RLIMIT_FSIZE)
    soft = maximum if previous[0] == resource.RLIM_INFINITY else min(maximum, previous[0])
    handler = signal.getsignal(signal.SIGXFSZ)
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, previous[1]))
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, previous)
        signal.signal(signal.SIGXFSZ, handler)


def download_plan(client, plan: dict, output: Path, *, credits_remaining: float,
                  max_cost: float, use_credits: bool, now: datetime | None = None) -> dict:
    if not use_credits:
        raise TrialSetupError("Review the saved quote and Billing, then explicitly supply --use-credits.")
    if isinstance(max_cost, bool) or not math.isfinite(max_cost) or not 0 < max_cost <= MAX_COST_USD:
        raise TrialSetupError("Maximum quoted cost must be positive and at most USD 5.")
    if isinstance(credits_remaining, bool) or not math.isfinite(credits_remaining) or credits_remaining <= 0:
        raise TrialSetupError("Supply the positive free-credit balance verified in Billing.")
    if output.exists() or output.is_symlink():
        raise TrialSetupError("Download output already exists; partial files are preserved and no automatic retry or overwrite is allowed.")
    plan = validate_plan(plan, now=now)
    fresh = quote_plan(client, plan["trading_date"], {market["symbol"]: market["underlying_identity"] for market in plan["markets"]}, now=now)
    for before, after in zip(plan["markets"], fresh["markets"]):
        for old, new in zip(before["requests"], after["requests"]):
            if any(old[key] != new[key] for key in ("request", "record_count", "billable_bytes")):
                raise TrialSetupError("Historical metadata changed; review a new immutable quote before downloading.")
    if fresh["estimated_total_usd"] > min(max_cost, credits_remaining):
        raise TrialSetupError("Fresh total exceeds the permitted estimate or confirmed free credits; no data downloaded.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    private_json(output / "request-plan.json", plan)
    private_json(output / "fresh-quote.json", fresh)
    manifest = {"schema": DOWNLOAD_SCHEMA, "status": "started", "created_at": _iso(now or datetime.now(timezone.utc)),
                "plan_sha256": plan["plan_sha256"], "fresh_quote_sha256": fresh["plan_sha256"],
                "estimated_total_usd": fresh["estimated_total_usd"], "max_cost_usd": max_cost,
                "operator_verified_credits_remaining_usd": credits_remaining, "billing_actual_usd": None,
                "attempted_quote_usd": 0.0, "compressed_bytes": 0, "files": [],
                "no_automatic_retry": True, "live_api_used": False}
    private_json(output / "download-start.json", manifest)
    try:
        for market in fresh["markets"]:
            folder = output / market["symbol"].lower()
            folder.mkdir(mode=0o700)
            for (role, schema), quoted in zip(ROLES, market["requests"]):
                if manifest["compressed_bytes"] >= MAX_COMPRESSED_BYTES:
                    raise TrialSetupError("Compressed input limit is exhausted; no further request was started.")
                number = len(manifest["files"])
                request, records = quoted["request"], None
                path = folder / (role + ".dbn")
                manifest["attempted_quote_usd"] = math.fsum((manifest["attempted_quote_usd"], quoted["estimated_cost_usd"]))
                attempt = {"index": number, "symbol": market["symbol"], "role": role, "request": request,
                           "estimated_cost_usd": quoted["estimated_cost_usd"], "attempted_quote_usd": manifest["attempted_quote_usd"]}
                private_json(output / f"progress-{number:02d}-before.json", attempt)
                stage = "download"
                try:
                    old_mask = os.umask(0o077)
                    try:
                        with _file_size_limit(MAX_COMPRESSED_BYTES - manifest["compressed_bytes"]):
                            records = client.timeseries.get_range(**request, path=path)
                    finally:
                        os.umask(old_mask)
                    stage = "validation"
                    info = path.lstat()
                    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_COMPRESSED_BYTES - manifest["compressed_bytes"]:
                        raise ValueError("invalid compressed file size")
                    path.chmod(0o600)
                    count = 0
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")
                        for _ in records:
                            count += 1
                            if count >= request["limit"]:
                                raise ValueError("metadata record limit reached")
                    if count == 0:
                        raise ValueError("empty historical data file")
                except Exception as exc:
                    raise TrialRequestError(stage, schema, exc) from None
                finally:
                    if records is not None and hasattr(records, "reader"):
                        records.reader.close()
                result = {**attempt, "path": str(path.relative_to(output)), "records": count,
                          "compressed_bytes": info.st_size, "sha256": _sha_file(path), "status": "complete"}
                manifest["compressed_bytes"] += info.st_size
                manifest["files"].append(result)
                private_json(output / f"progress-{number:02d}-complete.json", result)
        manifest["status"] = "download_complete"
        private_json(output / "download-complete.json", manifest)
        return manifest
    except BaseException as exc:
        manifest["status"] = "stopped"
        manifest["safe_error"] = str(exc) if isinstance(exc, TrialRequestError) else "Local acquisition stopped; partial files may have used credits. No automatic retry."
        try:
            private_json(output / "download-stopped.json", manifest)
        except OSError:
            pass
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="action", required=True)
    quote = commands.add_parser("quote", help="Save a metadata-only all-parent quote; downloads nothing.")
    quote.add_argument("--date", required=True, help="Completed CME trading date, YYYY-MM-DD.")
    quote.add_argument("--output", required=True, type=Path)
    for symbol in MARKETS:
        quote.add_argument(f"--{symbol.lower()}-underlying", type=Path, default=DEFAULT_CACHED[symbol],
                           help="Existing cached BBO-1s DBN identifying the selected futures contract.")
    download = commands.add_parser("download", help="Requote and explicitly acquire one reviewed saved plan.")
    download.add_argument("--plan", type=Path, required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--credits-remaining", type=float, required=True)
    download.add_argument("--max-cost", type=float, default=MAX_COST_USD)
    download.add_argument("--use-credits", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TrialSetupError("Output already exists; no overwrite, automatic retry or download was made.")
        if args.action == "download" and not args.use_credits:
            raise TrialSetupError("Downloading requires explicit --use-credits after reviewing the saved quote and Billing.")
        import databento as db
        client = db.Historical(key=read_key())
        if args.action == "quote":
            identities = {symbol: cached_underlying_identity(getattr(args, symbol.lower() + "_underlying"), symbol)
                          for symbol in MARKETS}
            plan = quote_plan(client, args.date, identities)
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_json(args.output, plan)
            for market in plan["markets"]:
                print(f"{market['symbol']}: {len(market['option_parents'])} parents; futures ID {market['underlying_identity']['instrument_id']}")
                for (role, _), item in zip(ROLES, market["requests"]):
                    print(f"  {role}: {item['record_count']:,} quoted records, {item['billable_bytes']:,} billable bytes, ${item['estimated_cost_usd']:.6f}")
            print(f"Metadata-only total: ${plan['estimated_total_usd']:.6f}; cap $5. No market data downloaded.")
            if plan["status"] != "quoted":
                print("All-parent quote exceeds the cap; stopped without a narrower fallback.")
                return 2
        else:
            result = download_plan(client, read_plan(args.plan), args.output,
                                   credits_remaining=args.credits_remaining, max_cost=args.max_cost, use_credits=args.use_credits)
            print(f"Session download complete; fresh quoted use ${result['estimated_total_usd']:.6f}. Actual billing is provider-controlled.")
        return 0
    except TrialSetupError as exc:
        print(f"Session setup stopped: {exc}")
        return 2
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        print("Session setup stopped: local input, storage or metadata was invalid. Existing files were preserved; no automatic retry.")
        return 2
    except Exception:
        print("Session setup stopped; provider details were withheld to protect credentials. Partial downloads may have used credits; no automatic retry.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

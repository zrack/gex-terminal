"""Independently reconcile local native full-session data and app replay evidence.

No provider client is constructed.  Raw accounting covers every input record;
numerical checks cover every European inverted tick and a deterministic sample
of checkpoint Greeks.  American reference checks require an already installed
QuantLib; their absence is reported, never silently certified.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import warnings

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.session_capture import (open_verified_capture,
                                         iter_verified_capture_stream)
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint
from gex_terminal.wind_tunnel import TerminalCheckpointCore
from gex_terminal.wind_tunnel_server import make_receipt, reproduce_receipt
from gex_terminal.snapshot import build_snapshot


NANO = 1_000_000_000
YEAR_NS = 365 * 86400 * NANO
ROLES = ("definitions", "underlying", "trades")
FP_FIELDS = ("publisher_id", "channel_id", "instrument_id", "ts_event", "ts_recv",
             "price", "size", "side", "action", "depth", "flags", "ts_in_delta", "sequence")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def field(record, name, default=None):
    value = record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)
    return getattr(value, "value", value)


def ns(value):
    """Parse native nanoseconds/ISO text without dropping fractional precision."""
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value if 0 <= value < (1 << 63) - 1 else None
    if isinstance(value, datetime):
        value = value.isoformat()
    text = str(value)
    match = re.fullmatch(r"(.{19})(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", text)
    require(match is not None, "Raw timestamp requires a timezone and at most nine fractional digits")
    date = datetime.fromisoformat(match[1] + ("+00:00" if match[3] == "Z" else match[3]))
    seconds = int((date - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())
    return seconds * NANO + int((match[2] or "").ljust(9, "0"))


def iso(value):
    seconds, fraction = divmod(value, NANO)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction:09d}Z"


def number(record, name, native):
    value = field(record, name)
    if value is None:
        return None
    if native:
        if int(value) == (1 << 63) - 1:
            return None
        return float(Decimal(int(value)) / NANO)
    value = float(value)
    return value if math.isfinite(value) and value != (1 << 63) - 1 else None


def native_trade_fingerprint(record, *, native=False):
    """Independent implementation of the documented native-fill identity."""
    payload = {}
    for name in FP_FIELDS:
        value = field(record, name)
        if value in (None, ""):
            payload[name] = None
            continue
        if name in {"ts_event", "ts_recv"}:
            stamp = ns(value)
            value = iso(stamp) if stamp is not None else value
        elif name == "price":
            value = Decimal(str(value)) / (NANO if native else 1)
            value = str(value.normalize())
        payload[name] = str(value)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def raw_records(path):
    """Yield native objects or decoded test fixtures; do not call an adapter."""
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Raw inputs must be ordinary local files")
    if path.suffix == ".jsonl":
        with path.open("rb") as stream:
            while line := stream.readline(1024 * 1024 + 1):
                require(len(line) <= 1024 * 1024, "Raw JSON record exceeds 1 MiB")
                if line.strip():
                    yield json.loads(line), False
        return
    import databento as db
    store = db.DBNStore.from_file(path)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message="DBN file is truncated.*")
            for record in store:
                yield record, True
    finally:
        store.reader.close()


def black76(futures, strike, years, rate, volatility, side):
    """Scalar stdlib price and futures gamma, independent of app engine."""
    require(futures > 0 and strike > 0 and years > 0 and volatility > 0,
            "Scalar Black-76 requires positive inputs")
    scale = volatility * math.sqrt(years)
    d1 = (math.log(futures / strike) + .5 * scale * scale) / scale
    d2 = d1 - scale
    sign = 1 if side == "C" else -1
    cdf = lambda z: .5 * math.erfc(-z / math.sqrt(2))
    discount = math.exp(-rate * years)
    price = sign * discount * (futures * cdf(sign * d1) - strike * cdf(sign * d2))
    gamma = discount * math.exp(-.5 * d1 * d1) / (math.sqrt(2 * math.pi) * futures * scale)
    return price, gamma


def independent_coverage(rows):
    available = lambda row: row.get("iv_source") != "unavailable" and isinstance(row.get("iv"), (int, float)) and row["iv"] > 0
    priced = [row for row in rows if available(row)]
    unpriced = [row for row in rows if not available(row)]
    retained = [row for row in priced if row.get("iv_source") == "prior_valid"]
    quantity = lambda items: sum(row["accumulated_volume"] for row in items)
    return {"selected_contract_count": len(rows), "selected_quantity": quantity(rows),
            "priced_contract_count": len(priced), "priced_quantity": quantity(priced),
            "unpriced_contract_count": len(unpriced), "unpriced_quantity": quantity(unpriced),
            "retained_iv_contract_count": len(retained), "retained_iv_quantity": quantity(retained),
            "unpriced_reasons": dict(Counter((row.get("iv_provenance") or {}).get("status", "iv_unavailable")
                                            for row in unpriced))}


class RawTruth:
    """An audit index constructed from native inputs, never converter SQLite."""

    def __init__(self, path, files, symbol, *, session=None):
        self.db = sqlite3.connect(path)
        Path(path).chmod(0o600)
        self.db.executescript("""
            PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
            CREATE TABLE definitions(id INTEGER PRIMARY KEY,iid TEXT,ns INTEGER,metadata TEXT);
            CREATE INDEX definition_time ON definitions(iid,ns,id);
            CREATE TABLE contracts(iid TEXT PRIMARY KEY,future TEXT);
            CREATE TABLE quotes(id INTEGER PRIMARY KEY,iid TEXT,ns INTEGER,price REAL,seen INTEGER DEFAULT 0);
            CREATE INDEX quote_time ON quotes(ns,id);
            CREATE TABLE trades(fp TEXT PRIMARY KEY,iid TEXT,ns INTEGER,recv INTEGER,price REAL,
                qty INTEGER,side TEXT,sequence TEXT,n INTEGER DEFAULT 1,seen INTEGER DEFAULT 0,selected INTEGER DEFAULT 0);
        """)
        self.inputs, self.counts, self.symbol = [], {}, symbol
        start, end = (ns(session["start"]), ns(session["end"])) if session else (None, None)
        if session:
            require(start is not None and end is not None and 0 < end - start <= 86400 * NANO, "Invalid native audit session window")
        products = {symbol, "EW" if symbol == "ES" else "QNE"}
        products.update(("EW" if symbol == "ES" else "QN") + str(i) for i in range(1, 5))
        products.update(("E" if symbol == "ES" else "Q") + str(i) + day
                        for i in range(1, 6) for day in "ABCD")
        futures, total = set(), 0
        require(set(files) == set(ROLES), "Native audit requires definitions, underlying and trades")
        require(sum(Path(path).stat().st_size for path in files.values()) <= 512 * 1024 * 1024, "Native audit input exceeds 512 MiB")
        for role in ROLES:
            path = Path(files[role])
            before, count, quantity = digest(path), 0, 0
            for record, native in raw_records(path):
                count += 1
                total += 1
                require(total <= 5_000_000, "Native audit exceeds five million records")
                kind = type(record).__name__ if native else str(field(record, "record_type", ""))
                valid = ((kind.startswith("InstrumentDefMsg") if native else kind == "definition") if role == "definitions" else
                         (kind == "BBOMsg" if native else kind == "bbo-1s") if role == "underlying" else
                         (kind == "TradeMsg" if native else kind == "trades"))
                require(valid, f"Native {role} contains an unexpected schema; underlying must be BBO-1s")
                iid = str(field(record, "instrument_id"))
                event = ns(field(record, "ts_event"))
                if role == "definitions":
                    require(event is not None, "Native definition requires authoritative event time; unknown-time metadata cannot be preloaded")
                    if end is not None:
                        require(event is None or event < end, "Native definition extends past session end")
                    side, product = str(field(record, "instrument_class", "")), str(field(record, "asset", ""))
                    if side not in {"C", "P"} or product not in products:
                        continue
                    strike, multiplier = number(record, "strike_price", native), number(record, "unit_of_measure_qty", native)
                    require(strike is not None and strike > 0 and multiplier is not None and multiplier > 0,
                            "Native option definition lacks strike/dollar multiplier")
                    expiry, future = ns(field(record, "expiration")), str(field(record, "underlying_id"))
                    require(expiry is not None, "Native option definition lacks exact expiration")
                    cfi = str(field(record, "cfi", ""))
                    style = {"A": "american", "E": "european"}.get(cfi[2:3], "unknown")
                    metadata = {"strike": strike, "option_type": side, "contract_symbol": str(field(record, "raw_symbol", "")),
                                "expiry_ns": expiry, "underlying_contract_id": future, "contract_multiplier": multiplier,
                                "provider_cfi": cfi if re.fullmatch("[A-Z]{6}", cfi) else None, "exercise_style": style,
                                "pricing_model": "american_futures_crr" if style == "american" else "black_76"}
                    old = self.db.execute("SELECT future FROM contracts WHERE iid=?", (iid,)).fetchone()
                    require(old is None or old[0] == future, "Native option underlying changes within session")
                    self.db.execute("INSERT OR IGNORE INTO contracts VALUES(?,?)", (iid, future))
                    self.db.execute("INSERT INTO definitions(iid,ns,metadata) VALUES(?,?,?)",
                                    (iid, event, json.dumps(metadata)))
                elif role == "underlying":
                    futures.add(iid)
                    schema = str(field(record, "record_type", ""))
                    bbo = schema == "bbo-1s" or (native and type(record).__name__ == "BBOMsg")
                    available = ns(field(record, "ts_recv")) if bbo else event
                    require(available is not None, "Raw underlying lacks authoritative quote availability")
                    if start is not None:
                        require(start - 2 * NANO <= available < end, "Native quote extends outside session and two-second warmup")
                    if native:
                        levels = record.levels[0]
                        bid, ask = number(levels, "bid_px", True), number(levels, "ask_px", True)
                    else:
                        bid, ask = number(record, "bid_px_00", False), number(record, "ask_px_00", False)
                    midpoint = (bid + ask) / 2 if bid is not None and ask is not None and 0 < bid <= ask else None
                    self.db.execute("INSERT INTO quotes(iid,ns,price) VALUES(?,?,?)", (iid, available, midpoint))
                else:
                    require(event is not None, "Raw trade lacks authoritative event time")
                    if start is not None:
                        require(start <= event < end, "Native trade extends outside requested session")
                    qty, premium = int(field(record, "size", 0)), number(record, "price", native)
                    require(qty >= 0, "Raw trade has negative quantity")
                    quantity += qty
                    fp = native_trade_fingerprint(record, native=native)
                    self.db.execute("""INSERT INTO trades(fp,iid,ns,recv,price,qty,side,sequence) VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(fp) DO UPDATE SET n=n+1""", (fp, iid, event, ns(field(record, "ts_recv")),
                        premium, qty, str(field(record, "side", "")), str(field(record, "sequence", ""))))
                if count % 10000 == 0:
                    self.db.commit()
            require(count > 0 and digest(path) == before, "Native input is empty or changed during audit")
            self.inputs.append({"role": role, "file": str(path.absolute()), "sha256": before, "records": count})
            self.counts[role] = {"records": count, "raw_quantity": quantity}
        require(len(futures) == 1, "Native BBO must identify exactly one futures contract")
        self.future = futures.pop()
        self.db.execute("UPDATE trades SET selected=1 WHERE iid IN (SELECT iid FROM contracts WHERE future=?)", (self.future,))
        self.db.execute("UPDATE trades SET selected=3 WHERE selected=1 AND qty=0")
        # The converter correctly does not preload later definitions.  Retain
        # those selected raw fills as a separately counted causal exclusion.
        self.db.execute("UPDATE trades SET selected=2 WHERE selected=1 AND NOT EXISTS (SELECT 1 FROM definitions d WHERE d.iid=trades.iid AND d.ns<=trades.ns)")
        self.db.commit()

    def close(self):
        self.db.close()

    def quote(self, message):
        event = ns(message["event_time"])
        row = self.db.execute("SELECT id,price FROM quotes WHERE ns=? AND iid=? AND seen=0 AND price IS NOT NULL ORDER BY id LIMIT 1",
                              (event, str(message.get("contract_id")))).fetchone()
        require(row is not None and math.isclose(message["price"], row[1], abs_tol=1e-9), "Captured underlying differs from native interval-end midpoint")
        self.db.execute("UPDATE quotes SET seen=1 WHERE id=?", (row[0],))

    def trade(self, message):
        fp = message.get("provider_trade_event_id")
        record = self.db.execute("SELECT iid,ns,recv,price,qty,side,sequence,n,seen,selected FROM trades WHERE fp=?", (fp,)).fetchone()
        require(record is not None, "Captured trade fingerprint is absent from native inputs")
        iid, event, received, premium, qty, side, sequence, occurrences, seen, selected = record
        require(selected == 1 and seen < occurrences, "Captured trade is excluded or exceeds native occurrences")
        metadata = self.db.execute("SELECT metadata FROM definitions WHERE iid=? AND ns<=? ORDER BY ns DESC,id DESC LIMIT 1", (iid, event)).fetchone()
        require(metadata is not None, "Captured trade used a future definition")
        metadata = json.loads(metadata[0])
        require(message["contract_id"] == iid and ns(message["event_time"]) == event and message["volume"] == qty,
                "Captured contract/time/quantity differs from raw trade")
        if received is not None:
            require(ns(message.get("received_time")) == received, "Captured receive time differs from native trade")
        for key in ("strike", "option_type", "contract_symbol", "underlying_contract_id", "contract_multiplier", "exercise_style", "pricing_model"):
            require(message.get(key) == metadata[key], f"Captured {key} differs from causal native definition")
        if metadata["provider_cfi"] is not None:
            require(message.get("provider_cfi") == metadata["provider_cfi"], "Captured CFI differs from native definition")
        require(ns(message["expiry_timestamp"]) == metadata["expiry_ns"], "Captured expiration differs from native definition")
        require(message.get("aggressor_side") == {"B": "buy", "A": "sell"}.get(side, "unknown"), "Captured aggressor side differs from native trade")
        if sequence:
            require(str(message.get("sequence")) == sequence, "Captured sequence differs from native trade")
        provenance = message.get("iv_provenance") or {}
        require(provenance.get("option_price") == premium, "Captured IV premium differs from native trade")
        quote = self.db.execute("SELECT ns,price FROM quotes WHERE ns<=? AND price IS NOT NULL ORDER BY ns DESC,id DESC LIMIT 1", (event,)).fetchone()
        if quote is not None:
            require(provenance.get("underlying_price") == quote[1] and ns(provenance.get("underlying_event_time")) == quote[0],
                    "IV inversion did not use latest causally available native quote")
            require(math.isclose(provenance["underlying_price_age_ms"], (event - quote[0]) / 1e6, abs_tol=1e-6), "IV quote age differs from native nanoseconds")
        else:
            require(provenance.get("underlying_price") is None, "IV inversion used unavailable underlying quote")
        years = (metadata["expiry_ns"] - event) / YEAR_NS
        if years > 0:
            require(math.isclose(provenance.get("time_to_expiry_years", -1), years, rel_tol=1e-9, abs_tol=1e-13), "IV remaining time differs from native expiration")
            if quote is not None:
                discount = math.exp(-provenance["risk_free_rate"] * years)
                intrinsic = max((quote[1] - metadata["strike"]) * (1 if metadata["option_type"] == "C" else -1), 0.)
                american = metadata["pricing_model"] == "american_futures_crr"
                lower = intrinsic if american else discount * intrinsic
                upper = (max(1., discount) if american else discount) * (quote[1] if metadata["option_type"] == "C" else metadata["strike"])
                require(math.isclose(provenance.get("lower_bound", -1), lower, rel_tol=1e-12, abs_tol=1e-8)
                        and math.isclose(provenance.get("upper_bound", -1), upper, rel_tol=1e-12, abs_tol=1e-8),
                        "Captured no-arbitrage bounds differ from independent model math")
                if provenance.get("status") == "outside_no_arbitrage_bounds":
                    require(premium is not None and (premium < lower or premium > upper), "Failed IV claims an unsupported bound violation")
        else:
            require(provenance.get("time_to_expiry_years") is None, "Expired trade has positive inversion time")
        iv_source, iv = message.get("iv_source"), message.get("iv")
        require(iv_source in {"black_76_inverted", "american_futures_inverted", "prior_valid", "unavailable", "provider"}, "Unsupported/default IV source")
        require(iv is None if iv_source == "unavailable" else isinstance(iv, (float, int)) and 0 < iv <= 5,
                "Unavailable IV was filled, or priced IV is invalid")
        if iv_source in {"black_76_inverted", "american_futures_inverted"}:
            require(provenance.get("status") == "converged" and quote is not None and years > 0,
                    "Inverted IV has no successful causal inversion")
            require((event - quote[0]) / 1e6 <= provenance["maximum_underlying_age_ms"], "Inverted IV used stale quote")
            if iv_source == "black_76_inverted":
                price, _ = black76(quote[1], metadata["strike"], years, provenance["risk_free_rate"], iv, metadata["option_type"])
                require(abs(price - premium) <= 1e-6, "Independent Black-76 repricing failed")
        if iv_source == "prior_valid":
            prior_ns = ns(provenance.get("prior_iv_event_time"))
            require(prior_ns is not None and 0 < event - prior_ns <= 300 * NANO
                    and provenance.get("prior_iv") == iv and provenance.get("prior_iv_pricing_model") == message["pricing_model"],
                    "Retained IV does not have a valid same-model age/value")
        self.db.execute("UPDATE trades SET seen=seen+1 WHERE fp=?", (fp,))
        return seen == 0, metadata

    def finish(self):
        missing = self.db.execute("SELECT COALESCE(SUM(n-seen),0) FROM trades WHERE selected=1").fetchone()[0]
        require(missing == 0, "Eligible raw trade occurrences are missing from normalized capture")
        missing_quotes = self.db.execute("SELECT COUNT(*) FROM quotes WHERE price IS NOT NULL AND seen=0").fetchone()[0]
        require(missing_quotes == 0, "Valid raw underlying quotes are missing from normalized capture")
        raw, unique, duplicates, excluded, excluded_qty = self.db.execute("""SELECT
            COALESCE(SUM(CASE WHEN selected>0 THEN n*qty ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN selected=1 THEN qty ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN selected=1 THEN n-1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN selected=0 THEN n ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN selected=0 THEN n*qty ELSE 0 END),0) FROM trades""").fetchone()
        self.db.commit()
        causal_events, causal_qty = self.db.execute("SELECT COALESCE(SUM(n),0),COALESCE(SUM(n*qty),0) FROM trades WHERE selected=2").fetchone()
        zero_events = self.db.execute("SELECT COALESCE(SUM(n),0) FROM trades WHERE selected=3").fetchone()[0]
        return {"input": self.counts, "selected_raw_quantity_including_duplicates": raw,
                "selected_unique_quantity": unique, "duplicate_trade_occurrences": duplicates,
                "excluded_option_events": excluded, "excluded_option_quantity": excluded_qty,
                "causally_unavailable_definition_events": causal_events, "causally_unavailable_definition_quantity": causal_qty,
                "nonpositive_quantity_events": zero_events,
                "missing_trade_occurrences": missing, "missing_valid_quotes": missing_quotes}


def quantlib_reference(futures, strike, years, rate, volatility, side, grid=1000):
    """Optional independent FD oracle; exact fractional maturity, no date rounding."""
    try:
        ql = importlib.import_module("QuantLib")
    except ImportError:
        local = Path("/tmp/gex-quantlib-reference")
        if not local.is_dir():
            return None
        sys.path.insert(0, str(local))
        try:
            ql = importlib.import_module("QuantLib")
        except ImportError:
            return None
    today = ql.Date(1, 1, 2020)
    ql.Settings.instance().evaluationDate = today
    clock = ql.Actual365Fixed()
    rates = ql.YieldTermStructureHandle(ql.FlatForward(today, rate * years, clock))
    vol = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), volatility * math.sqrt(years), clock))
    process = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(futures)), rates, rates, vol)
    option = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if side == "C" else ql.Option.Put, strike),
                             ql.AmericanExercise(today, today + 365))
    option.setPricingEngine(ql.FdBlackScholesVanillaEngine(process, grid, grid))
    return {"price": option.NPV(), "gamma": option.gamma(), "grid": grid, "version": ql.__version__}


def stratified(rows, limit=16):
    """Deterministic calls/puts, styles and expiry strata, spanning strikes."""
    groups = {}
    for row in rows:
        groups.setdefault((row.get("exercise_style"), row["option_type"], row["expiry_timestamp"]), []).append(row)
    queues = []
    for key in sorted(groups, key=str):
        group = sorted(groups[key], key=lambda row: (row["strike"], row["contract_id"]))
        order = [len(group) // 2, 0, len(group) - 1]
        order.extend(range(len(group)))
        queues.append([group[index] for index in dict.fromkeys(order)])
    result = []
    while queues and len(result) < limit:
        for group in list(queues):
            if len(result) == limit:
                break
            result.append(group.pop(0))
            if not group:
                queues.remove(group)
    return result


def write_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


async def checkpoint_audit(consumer, ledger, requested_ns, name, output, model_inputs, checkpoint_cache=None):
    if consumer.market_time is None:
        result = {"name": name, "requested_cutoff": iso(requested_ns), "actual_as_of": None,
                  "coverage": independent_coverage([]), "expired_quantity_retained_in_session_ledger": 0,
                  "terminal_status": "no_data", "wind_status": "not_evaluable",
                  "snapshot_status": "unavailable: no authoritative captured market state at cutoff",
                  "checkpoint_status": "unavailable: no authoritative captured market state at cutoff",
                  "total_net_gex": None, "receipt_reproduction": "not_evaluable: no checkpoint", "numeric_checks": []}
        write_json(output / (name + "-summary.json"), result)
        return result
    matrix = await consumer.process_latest_snapshot(model_inputs["days_to_expiry"])
    actual_as_of = consumer.market_time.isoformat().replace("+00:00", "Z")
    actual_ns = ns(actual_as_of)
    active = [row for row in ledger.values() if ns(row["expiry_timestamp"]) > actual_ns]
    coverage = independent_coverage(active)
    selected = await consumer.selected_contract_rows(expiry_filter="all")
    expected = {row["contract_id"]: row["accumulated_volume"] for row in active}
    require({row["contract_id"]: row["accumulated_volume"] for row in selected} == expected,
            "Consumer active quantities differ from independent native unique-trade ledger")
    for key, value in (matrix.get("pricing_coverage") or {}).items():
        if key in coverage:
            require(value == coverage[key], f"Terminal pricing coverage differs: {key}")
    checkpoint_cache = checkpoint_cache if checkpoint_cache is not None else {}
    request, checkpoint_status = {}, "available"
    if active:
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=model_inputs["days_to_expiry"], source_label=name)
        require({row["contract_id"]: row["accumulated_volume"] for row in artifact["rows"]} == expected,
                "Checkpoint quantities differ from active native ledger")
        checkpoint_cache["artifact"] = artifact
    else:
        require("error" in matrix, "All-expired consumer state must be unavailable")
        artifact = checkpoint_cache.get("artifact")
        checkpoint_status = "unavailable: canonical Terminal checkpoint requires at least one active row"
        if artifact is None:
            result = {"name": name, "requested_cutoff": iso(requested_ns), "actual_as_of": actual_as_of,
                      "coverage": coverage, "expired_quantity_retained_in_session_ledger": sum(row["accumulated_volume"] for row in ledger.values()),
                      "terminal_status": matrix.get("status", "no_data"), "wind_status": "not_evaluable",
                      "snapshot_status": "unavailable: " + matrix["error"], "checkpoint_status": checkpoint_status,
                      "total_net_gex": None, "receipt_reproduction": "not_evaluable: no prior nonempty checkpoint", "numeric_checks": []}
            write_json(output / (name + "-summary.json"), result)
            return result
        request = {"time_advance": (actual_ns - ns(artifact["source"]["as_of"])) / (60 * NANO),
                   "spot_shift": consumer.current_spot - artifact["parameters"]["spot"]}
        checkpoint_status += "; Wind uses explicit time/spot advance from prior nonempty captured checkpoint"
    core = TerminalCheckpointCore(artifact)
    receipt = await make_receipt(name, "calculate", request, core=core)
    reproduction = await reproduce_receipt(receipt, core=core)
    require(reproduction["status"] == "verified", "Fresh Wind receipt did not reproduce exactly")
    baseline = receipt["result"]["baseline" if active else "scenario"]
    for key, value in (baseline.get("pricing_coverage") or {}).items():
        if key in coverage:
            require(value == coverage[key], f"Wind pricing coverage differs: {key}")
    unpriced = {row["contract_id"]: row for row in active if row.get("iv_source") == "unavailable"}
    excluded = {row["contract_id"]: row for row in baseline["excluded_contracts"] if row["reason"] == "iv_unavailable"}
    require(set(unpriced) == set(excluded), "Wind unpriced details omit or invent a contract")
    for iid, row in unpriced.items():
        require(excluded[iid]["quantity"] == row["accumulated_volume"] and excluded[iid]["iv_provenance"] == row["iv_provenance"],
                "Wind unpriced captured inputs/quantity changed")
    if coverage["priced_contract_count"]:
        require(baseline["status"] == "available" and "error" not in matrix, "Priced active data became unavailable")
        require(math.isclose(matrix["total_net_gex"], baseline["summary"]["total_net_gex"], rel_tol=1e-12, abs_tol=1e-6),
                "Terminal/Wind raw-volume GEX differs")
    else:
        require(baseline["status"] != "available" and matrix.get("error"), "Empty/all-unpriced exposure was presented as available")
    details = {row["contract_id"]: row for row in baseline["contracts"]}
    require(set(details) == {row["contract_id"] for row in active if row.get("iv_source") != "unavailable"},
            "Wind priced details omit or invent a contract")
    scalar_total, checks = 0., []
    for row in active:
        if row.get("iv_source") == "unavailable":
            continue
        current = details[row["contract_id"]]
        require(current["quantity"] == row["accumulated_volume"] and current["strike"] == row["strike"]
                and current["option_type"] == row["option_type"] and current["pricing_model"] == row["pricing_model"]
                and current["base_iv"] == row["iv"] and current["multiplier"] == row["contract_multiplier"],
                "Wind priced detail changed the captured contract/IV/quantity inputs")
        years = (ns(row["expiry_timestamp"]) - actual_ns) / YEAR_NS
        if row["pricing_model"] == "black_76":
            _, gamma = black76(consumer.current_spot, row["strike"], years, model_inputs["risk_free_rate"], row["iv"], row["option_type"])
            require(math.isclose(gamma, current["gamma"], rel_tol=1e-9, abs_tol=1e-12), "Independent European checkpoint gamma differs")
        else:
            gamma = current["gamma"]
        signed = row["accumulated_volume"] * (1 if row["option_type"] == "C" else -1)
        gex = gamma * consumer.current_spot ** 2 * .01 * row["contract_multiplier"] * signed
        require(math.isclose(gex, current["net_gex"], rel_tol=1e-10, abs_tol=1e-7), "Independent per-contract GEX arithmetic differs")
        scalar_total += gex
    if details:
        require(math.isclose(scalar_total, matrix["total_net_gex"], rel_tol=1e-9, abs_tol=1e-5), "Independent aggregate GEX arithmetic differs")
    if "error" not in matrix:
        snapshot = build_snapshot(symbol=consumer.target_underlying, spot=consumer.current_spot,
                                  session_open=consumer.session_open, days_to_expiry=model_inputs["days_to_expiry"],
                                  contract_multiplier=model_inputs["contract_multiplier"], risk_free_rate=model_inputs["risk_free_rate"],
                                  data=matrix, chain_state=consumer.chain_state, timestamp=actual_as_of)
        require(math.isclose(snapshot["metrics"]["total_net_gex"], scalar_total, rel_tol=1e-9, abs_tol=1e-5), "Portable snapshot GEX differs")
        write_json(output / (name + "-snapshot.json"), snapshot)
        snapshot_status = "available"
    else:
        snapshot_status = "unavailable: " + matrix["error"]
    for row in stratified([row for row in active if row.get("iv_source") != "unavailable"]):
        years = (ns(row["expiry_timestamp"]) - actual_ns) / YEAR_NS
        check = {"contract_id": row["contract_id"], "side": row["option_type"], "strike": row["strike"],
                 "expiry": row["expiry_timestamp"], "exercise_style": row.get("exercise_style"), "model": row["pricing_model"]}
        if row["pricing_model"] == "american_futures_crr":
            from gex_terminal.american_futures import american_futures_price_gamma
            production = american_futures_price_gamma(futures_price=consumer.current_spot, strike=row["strike"], time_to_expiry_years=years,
                                                     risk_free_rate=model_inputs["risk_free_rate"], volatility=row["iv"], option_type=row["option_type"])
            require(math.isclose(production.gamma, details[row["contract_id"]]["gamma"], rel_tol=1e-9, abs_tol=1e-12),
                    "Wind American gamma differs from the same side-specific model inputs")
            first = quantlib_reference(consumer.current_spot, row["strike"], years, model_inputs["risk_free_rate"], row["iv"], row["option_type"], 1000)
            if first is None:
                check["status"] = "independent_reference_unavailable"
            else:
                reference = quantlib_reference(consumer.current_spot, row["strike"], years, model_inputs["risk_free_rate"], row["iv"], row["option_type"], 2000)
                price_error, gamma_error = abs(reference["price"] - production.price), abs(reference["gamma"] - production.gamma)
                price_limit, gamma_limit = max(.05, consumer.current_spot * 2e-6), max(1e-9, abs(reference["gamma"]) * .01)
                require(abs(reference["price"] - first["price"]) <= price_limit and abs(reference["gamma"] - first["gamma"]) <= gamma_limit,
                        "Independent American FD reference has not converged within declared gates")
                require(price_error <= price_limit and gamma_error <= gamma_limit, "American model differs from independent FD beyond declared gates")
                check.update(status="passed", reference=reference, coarse_reference=first, price_error=price_error, gamma_error=gamma_error,
                             price_limit=price_limit, gamma_limit=gamma_limit)
        else:
            check["status"] = "scalar_black76_passed"
        checks.append(check)
    write_json(output / (name + "-checkpoint.json"), artifact)
    write_json(output / (name + "-receipt.json"), receipt)
    write_json(output / (name + "-reproduction.json"), reproduction)
    result = {"name": name, "requested_cutoff": iso(requested_ns), "actual_as_of": actual_as_of,
              "coverage": coverage, "expired_quantity_retained_in_session_ledger": sum(row["accumulated_volume"] for row in ledger.values()) - coverage["selected_quantity"],
              "terminal_status": matrix.get("status", "available"), "wind_status": baseline["status"],
              "snapshot_status": snapshot_status,
              "checkpoint_status": checkpoint_status,
              "total_net_gex": matrix.get("total_net_gex"), "receipt_reproduction": reproduction["status"],
              "numeric_checks": checks, "gex_arithmetic": "All active European Greeks independently scalar checked; American aggregate uses production Greeks with deterministic sampled independent FD checks."}
    write_json(output / (name + "-summary.json"), result)
    return result


async def validate_market(*, files, symbol, capture, conversion_report, output, expected_inputs=None):
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    truth = None
    stream = None
    try:
        stream = open_verified_capture(capture)
        header = json.loads(stream.readline())
        source, model_inputs = header["source"], header["model_inputs"]
        truth = RawTruth(output / "raw-truth.sqlite", files, symbol, session=source["session"])
        if expected_inputs is not None:
            for entry in truth.inputs:
                expected = expected_inputs[entry["role"]]
                require(entry["sha256"] == expected["sha256"] and entry["records"] == expected["records"], "Native input differs from download receipt")
        require(source.get("symbol") == symbol and source.get("network_used") is False,
                "Capture source is not the requested offline market")
        require(source["subset"]["underlying_instrument_id"] == truth.future, "Captured futures subset differs from native BBO")
        for entry in truth.inputs:
            declared = next((item for item in source["inputs"] if item["role"] == entry["role"]), {})
            require(declared.get("sha256") == entry["sha256"] and declared.get("records") == entry["records"], "Capture native provenance does not match raw files")
        start, end = ns(source["session"]["start"]), ns(source["session"]["end"])
        require(start is not None and end is not None and start < end, "Capture lacks session boundaries")
        if expected_inputs is not None:
            requested = expected_inputs["trades"]["request"]
            require(start == ns(requested["start"]) and end == ns(requested["end"]),
                    "Captured session window differs from the acquisition trade request")
        day = datetime.fromtimestamp((end - 1) / NANO, timezone.utc).strftime("%Y-%m-%d")
        cutoffs = [("open-15m", start + 15 * 60 * NANO), ("original-sample", ns(day + "T13:40:00Z")),
                   ("pre-expiry", ns(day + "T19:59:59Z")), ("post-expiry", ns(day + "T20:00:00Z"))]
        cutoffs = sorted((name, stamp) for name, stamp in cutoffs if start <= stamp < end)
        cutoffs.sort(key=lambda item: item[1])
        consumer = StatefulGexConsumer(IntradayGexEngine(model_inputs["contract_multiplier"]), target_underlying=symbol,
                                      risk_free_rate=model_inputs["risk_free_rate"], data_mode="replay", expiry_filter="all")
        consumer.mark_connected()
        ledger, latest_valid, statuses, iv_sources, checkpoints = {}, {}, Counter(), Counter(), []
        checkpoint_cache = {}
        previous, events, duplicates, total_qty = -1, 0, 0, 0
        for envelope in iter_verified_capture_stream(stream):
            message = envelope["message"]
            event = ns(message.get("event_time"))
            require(event is not None and event >= previous, "Capture market events are not chronological")
            while cutoffs and event > cutoffs[0][1]:
                name, cutoff = cutoffs.pop(0)
                checkpoints.append(await checkpoint_audit(consumer, ledger, cutoff, name, output, model_inputs, checkpoint_cache))
            previous, events = event, events + 1
            if message["type"] == "underlying_tick":
                truth.quote(message)
                unique = True
            elif message["type"] == "options_volume_tick":
                require(start <= event < end, "Captured trade is outside requested session")
                unique, metadata = truth.trade(message)
                provenance = message.get("iv_provenance") or {}
                require(provenance.get("risk_free_rate") == model_inputs["risk_free_rate"], "IV rate differs from capture assumptions")
                statuses[str(provenance.get("status", "missing"))] += 1
                iv_sources[message["iv_source"]] += 1
                iid = message["contract_id"]
                if message["iv_source"] == "prior_valid":
                    prior = latest_valid.get(iid)
                    require(prior is not None and prior["event_time"] == provenance["prior_iv_event_time"]
                            and prior["iv"] == message["iv"] and prior["pricing_model"] == message["pricing_model"]
                            and prior["contract_id"] == iid and prior["provider"] == message["provider"]
                            and prior["symbol"] == message["symbol"] and prior["expiry_timestamp"] == message["expiry_timestamp"]
                            and prior.get("underlying_contract_id") == message.get("underlying_contract_id")
                            and prior["iv_source"] == provenance.get("prior_iv_source")
                            and provenance.get("prior_iv_risk_free_rate") == (prior.get("iv_provenance") or {}).get("risk_free_rate", model_inputs["risk_free_rate"]),
                            "Retained IV is not the actual prior successful same-contract observation")
                if unique:
                    total_qty += message["volume"]
                    row = dict(message)
                    row["accumulated_volume"] = ledger.get(iid, {}).get("accumulated_volume", 0) + message["volume"]
                    ledger[iid] = row
                else:
                    duplicates += 1
                if unique and message["iv_source"] in {"provider", "black_76_inverted", "american_futures_inverted"}:
                    latest_valid[iid] = message
            else:
                raise ValueError("Capture includes an unexpected non-trade/non-underlying message")
            accepted = await consumer.update_market_state(json.dumps(message))
            require(accepted == unique, "Consumer acceptance differs from native unique-event accounting")
            if events % 10000 == 0:
                truth.db.commit()
                print(f"Validated {events:,} {symbol} normalized events...", file=sys.stderr, flush=True)
                await asyncio.sleep(0)
        require(events > 0 and consumer.market_time is not None, "Completed capture has no market state")
        while cutoffs:
            name, cutoff = cutoffs.pop(0)
            checkpoints.append(await checkpoint_audit(consumer, ledger, cutoff, name, output, model_inputs, checkpoint_cache))
        checkpoints.append(await checkpoint_audit(consumer, ledger, end, "final", output, model_inputs, checkpoint_cache))
        accounting = truth.finish()
        require(total_qty == accounting["selected_unique_quantity"] and duplicates == accounting["duplicate_trade_occurrences"], "Native/consumer duplicate accounting differs")
        report = json.loads(Path(conversion_report).read_text())
        require(report.get("errors") == [] and report.get("provider_requests") == 0 and report.get("credits_used") == 0,
                "Converter did not finish cleanly offline")
        for role in ROLES:
            require(report["raw_accounting"][role]["records"] == truth.counts[role]["records"], "Converter raw record count differs")
        eligible = truth.db.execute("SELECT COUNT(*) FROM contracts WHERE future=?", (truth.future,)).fetchone()[0]
        selected_defs = truth.db.execute("SELECT COUNT(*) FROM definitions WHERE iid IN (SELECT iid FROM contracts WHERE future=?)", (truth.future,)).fetchone()[0]
        other_defs = truth.db.execute("SELECT COUNT(*) FROM definitions WHERE iid IN (SELECT iid FROM contracts WHERE future!=?)", (truth.future,)).fetchone()[0]
        for key, value in {"eligible_option_contracts": eligible, "excluded_definitions": truth.counts["definitions"]["records"] - selected_defs,
                           "excluded_other_future_option_definitions": other_defs, "excluded_option_events": accounting["excluded_option_events"]}.items():
            require(source["subset"].get(key) == value, f"Captured native subset accounting differs: {key}")
        require(report["coverage"]["option_trades"] == sum(iv_sources.values())
                and report["coverage"]["retained_prior_iv_ticks"] == iv_sources["prior_valid"]
                and report["coverage"]["unavailable_iv_ticks"] == iv_sources["unavailable"]
                and report["coverage"]["inverted_iv_ticks"] == iv_sources["black_76_inverted"] + iv_sources["american_futures_inverted"],
                "Converter IV event/reason counters differ from normalized stream")
        require(report["raw_accounting"]["trades"]["raw_quantity"] == truth.counts["trades"]["raw_quantity"]
                and report["raw_accounting"]["trades"]["selected_raw_quantity"] == accounting["selected_raw_quantity_including_duplicates"],
                "Converter raw quantity accounting differs")
        last = checkpoints[-1]
        require(report["final_matrix"].get("total_net_gex") == last["total_net_gex"], "Saved converter final GEX differs from fresh replay")
        for key, value in (report["final_matrix"].get("pricing_coverage") or {}).items():
            if key in last["coverage"]:
                require(value == last["coverage"][key], "Saved converter final coverage differs from fresh independent ledger")
        result = {"schema": "gex-terminal.full-session-validation.v1", "status": "passed", "symbol": symbol,
                  "capture": str(Path(capture).absolute()), "capture_sha256": digest(capture), "inputs": truth.inputs,
                  "raw_accounting": accounting, "normalized_event_count": events, "iv_sources": dict(iv_sources),
                  "inversion_statuses": dict(statuses), "checkpoints": checkpoints,
                  "provider_requests": 0, "credits_used": 0,
                  "evidence_ceiling": "Complete reconciliation of these downloaded files, not exchange-chain completeness, live entitlement, economic fair value or predictive validity. American reference checks are sampled; unavailable optional references remain explicit."}
        write_json(output / "validation.json", result)
        return result
    finally:
        if stream is not None:
            stream.close()
        if truth is not None:
            truth.close()


async def validate_download(manifest, replays, output):
    manifest = Path(manifest).absolute()
    receipt = json.loads(manifest.read_text())
    require(receipt.get("status") == "download_complete", "A completed acquisition receipt is required")
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    results = []
    for symbol in ("ES", "NQ"):
        entries = {entry["role"]: entry for entry in receipt["files"] if entry["symbol"] == symbol}
        require(set(entries) == set(ROLES), "Acquisition requires definitions, underlying and trades for ES and NQ")
        files = {role: manifest.parent / entry["path"] for role, entry in entries.items()}
        replay = Path(replays) / symbol.lower()
        results.append(await validate_market(files=files, symbol=symbol, capture=replay / f"{symbol.lower()}.gex-session.jsonl",
                                             conversion_report=replay / "report.json", output=output / symbol.lower(), expected_inputs=entries))
    summary = {"schema": "gex-terminal.full-session-validation-run.v1", "status": "passed", "manifest_sha256": digest(manifest),
               "markets": [{"symbol": row["symbol"], "normalized_event_count": row["normalized_event_count"],
                            "final_coverage": row["checkpoints"][-1]["coverage"]} for row in results],
               "provider_requests": 0, "credits_used": 0}
    write_json(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replays", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from gex_terminal.saved_workspace import restrict_network_to_loopback
    restrict_network_to_loopback()
    print(json.dumps(asyncio.run(validate_download(args.manifest, args.replays, args.output))))


if __name__ == "__main__":
    main()

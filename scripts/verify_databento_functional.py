"""Verify an installed wheel with public CLI, binary replay and terminal exports.

Run with --python pointing at a fresh wheel installation. The worker is copied
outside the checkout and rejects source imports. All inputs are synthetic.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


EVENT = datetime(2026, 8, 6, 16, tzinfo=timezone.utc)
EXPIRY = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
RATE = 0.045
VOLATILITY = 0.22


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


def year_fraction(as_of):
    return (EXPIRY - as_of).total_seconds() / (365 * 86400)


def scalar_price(forward, strike, years, volatility, option_type):
    deviation = volatility * math.sqrt(years)
    d1 = (math.log(forward / strike) + deviation * deviation / 2) / deviation
    d2 = d1 - deviation
    cdf = lambda x: (1 + math.erf(x / math.sqrt(2))) / 2
    if option_type == "C":
        return math.exp(-RATE * years) * (forward * cdf(d1) - strike * cdf(d2))
    return math.exp(-RATE * years) * (strike * cdf(-d2) - forward * cdf(-d1))


def scalar_gex(forward, strike, years, volatility, quantity, multiplier, option_type):
    deviation = volatility * math.sqrt(years)
    d1 = (math.log(forward / strike) + deviation * deviation / 2) / deviation
    gamma = math.exp(-RATE * years - d1 * d1 / 2) / (math.sqrt(2 * math.pi) * forward * deviation)
    return gamma * forward * forward * 0.01 * quantity * multiplier * (1 if option_type == "C" else -1)


def scenario(root):
    forward, multiplier = (6000.0, 50) if root == "ES" else (20000.0, 20)
    families = (root, "E2A", "EW3", "EW") if root == "ES" else (root, "Q2A", "QN3", "QNE")
    definitions = []
    for index, asset in enumerate(families):
        definitions.append({
            "record_type": "definition", "instrument_id": 101 + index,
            "raw_symbol": f"{asset}Q6 {'P' if index == 1 else 'C'}{forward + index * 25:g}",
            "asset": asset, "underlying": f"{root}U6", "underlying_id": 202,
            "strike_price": forward + index * 25, "instrument_class": "P" if index == 1 else "C",
            "expiration": iso(EXPIRY), "contract_multiplier": 2147483647,
            "unit_of_measure": "IPNT", "unit_of_measure_qty": multiplier,
        })
    quote = {
        "record_type": "mbp-1", "instrument_id": 202,
        "bid_px_00": forward - 0.25, "ask_px_00": forward + 0.25, "ts_event": iso(EVENT),
    }
    trades = []
    for index, quantity in ((0, 7), (1, 4)):
        strike, kind = forward + index * 25, "P" if index else "C"
        trades.append({
            "record_type": "trades", "instrument_id": 101 + index,
            "price": round(scalar_price(forward, strike, year_fraction(EVENT), VOLATILITY, kind), 9),
            "size": quantity, "side": "B", "sequence": 10 + index, "ts_event": iso(EVENT),
        })
    oi = lambda instrument, quantity, seconds=0, **extras: {
        "record_type": "statistics", "instrument_id": instrument, "stat_type": 9,
        "quantity": quantity, "update_action": 1, "ts_ref": "2026-08-05T00:00:00Z",
        "ts_event": iso(EVENT + timedelta(seconds=seconds)), **extras,
    }
    base = [*definitions, quote, *trades, oi(103, 1200), oi(104, 0)]
    revised = [*base, oi(103, 1250, 1), oi(103, 800, 2, ts_ref="2026-08-04T00:00:00Z"), oi(103, 9223372036854775807, 3)]
    deleted = [*revised, oi(103, 0, 4, update_action=2)]
    rolled = [*deleted, {**quote, "instrument_id": 303, "bid_px_00": forward + 99.75, "ask_px_00": forward + 100.25, "ts_event": iso(EVENT + timedelta(seconds=5))},
              {**trades[0], "sequence": 30, "ts_event": iso(EVENT + timedelta(seconds=6))}, oi(103, 1400, 6),
              {**quote, "ts_event": iso(EVENT + timedelta(seconds=7))}]
    return {"initial": base, "revised": revised, "deleted": deleted, "rollover": rolled}


def expected_gex(root, stage):
    if stage == "rollover":
        return None
    forward, multiplier = (6000.0, 50) if root == "ES" else (20000.0, 20)
    seconds = {"initial": 0, "revised": 1, "deleted": 4}[stage]
    years = year_fraction(EVENT + timedelta(seconds=seconds))
    value = scalar_gex(forward, forward, years, VOLATILITY, 7, multiplier, "C")
    value += scalar_gex(forward, forward + 25, years, VOLATILITY, 4, multiplier, "P")
    if stage != "deleted":
        value += scalar_gex(forward, forward + 50, years, 0.15, 1200 if stage == "initial" else 1250, multiplier, "C")
    return value


def write_dbn(records, path):
    import databento_dbn as dbn
    nanos = lambda value: int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1e9)
    metadata = dbn.Metadata(dataset="GLBX.MDP3", start=nanos(iso(EVENT)), stype_in=dbn.SType.RAW_SYMBOL, stype_out=dbn.SType.INSTRUMENT_ID, schema=None, symbols=[])
    encoded = [metadata.encode()]
    for record in records:
        kind = record["record_type"]
        common = {"publisher_id": 1, "instrument_id": record["instrument_id"], "ts_event": nanos(record.get("ts_event", iso(EVENT))), "ts_recv": nanos(record.get("ts_event", iso(EVENT)))}
        if kind == "definition":
            item = dbn.InstrumentDefMsg(**common, min_price_increment=250000000, display_factor=1000000000,
                raw_symbol=record["raw_symbol"], asset=record["asset"], underlying=record["underlying"], underlying_id=record["underlying_id"], security_type="OOF",
                instrument_class=dbn.InstrumentClass.PUT if record["instrument_class"] == "P" else dbn.InstrumentClass.CALL,
                security_update_action=dbn.SecurityUpdateAction.ADD, expiration=nanos(record["expiration"]),
                strike_price=int(record["strike_price"] * 1e9), unit_of_measure=record["unit_of_measure"], unit_of_measure_qty=int(record["unit_of_measure_qty"] * 1e9))
        elif kind == "mbp-1":
            item = dbn.MBP1Msg(**common, price=dbn.UNDEF_PRICE, size=0, action=dbn.Action.ADD, side=dbn.Side.NONE, depth=0,
                levels=dbn.BidAskPair(bid_px=int(record["bid_px_00"] * 1e9), ask_px=int(record["ask_px_00"] * 1e9), bid_sz=1, ask_sz=1))
        elif kind == "trades":
            item = dbn.TradeMsg(**common, price=round(record["price"] * 1e9), size=record["size"], action=dbn.Action.TRADE,
                side=dbn.Side.BID, depth=0, sequence=record["sequence"])
        else:
            item = dbn.StatMsg(**common, ts_ref=nanos(record["ts_ref"]), price=dbn.UNDEF_PRICE, quantity=record["quantity"], stat_type=dbn.StatType.OPEN_INTEREST,
                update_action=dbn.StatUpdateAction.DELETE if record["update_action"] == 2 else dbn.StatUpdateAction.NEW)
        encoded.append(bytes(item))
    path.write_bytes(b"".join(encoded))


def verify_report(report, root, stage):
    expected = expected_gex(root, stage)
    snapshot = report["snapshot"]
    if expected is None:
        assert snapshot is None, "rollover retained stale exposure"
    else:
        actual = snapshot["metrics"]["total_net_gex"]
        assert math.isclose(actual, expected, rel_tol=2e-6, abs_tol=1e-5), (root, stage, actual, expected)
        assert snapshot["effective_contract_multiplier"] == (50 if root == "ES" else 20)
        assert snapshot["model"]["multiplier_provenance"]["fallback_row_count"] == 0
    assert report["input"]["network_used"] is False
    assert not report["errors"], report["errors"]
    return expected


def verify_installed_wheel(package_directory, wheel):
    members_verified = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if not member.startswith("gex_terminal/") or member.endswith("/"):
                continue
            parts = Path(member).parts
            if ".." in parts:
                raise ValueError("invalid wheel member path")
            installed_file = package_directory.joinpath(*parts[1:])
            if not installed_file.is_file() or installed_file.read_bytes() != archive.read(member):
                raise ValueError(f"installed package does not match candidate wheel: {member}")
            members_verified += 1
    if not members_verified:
        raise ValueError("candidate wheel has no application package members")
    return {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "package_members_verified": members_verified, "passed": True}


async def terminal_check(root, records, directory):
    from gex_terminal.adapters.databento import DatabentoAdapter
    from gex_terminal.adapters.replay import ReplayAdapter
    from gex_terminal.config import GexConfig
    from gex_terminal.consumer import StatefulGexConsumer
    from gex_terminal.engine import IntradayGexEngine
    from gex_terminal.tui import GexTerminalApp
    from textual.widgets import DataTable, Static
    from rich.text import Text

    multiplier = 50 if root == "ES" else 20
    class RecordingConsumer(StatefulGexConsumer):
        def __init__(self):
            super().__init__(IntradayGexEngine(multiplier=multiplier), target_underlying=root, data_mode="replay")
            self.messages = []
        async def update_market_state(self, raw_message):
            accepted = await super().update_market_state(raw_message)
            if accepted:
                self.messages.append(raw_message)
            return accepted

    recorder = RecordingConsumer()
    adapter = DatabentoAdapter(recorder, target_underlying=root)
    for record in records:
        await adapter._handle_live_record(record)
    replay_path = directory / f"{root}-normalized.jsonl"
    replay_path.write_text("\n".join(recorder.messages) + "\n")
    consumer = StatefulGexConsumer(IntradayGexEngine(multiplier=multiplier), target_underlying=root, data_mode="replay")
    await ReplayAdapter(consumer, replay_path, delay_seconds=0, replay_clock="fixed").stream_market_data()
    config = GexConfig(symbol=root, symbols=(root,), data_mode="replay", data_provider="databento", contract_multiplier=multiplier,
        risk_free_rate=RATE, days_to_expiry=14, refresh_interval_seconds=3600, stale_after_seconds=10,
        replay_path=str(replay_path), replay_delay_seconds=0, tradovate_environment="demo")
    app = GexTerminalApp(consumer, config, allow_replay_switching=False)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await app.refresh_terminal_data()
        assert app.query_one("#gex-table", DataTable).row_count > 0
        assert math.isclose(app._last_data["total_net_gex"], expected_gex(root, "deleted"), rel_tol=2e-6)
        def visible(selector):
            content = app.query_one(selector, Static).content
            return content.plain if isinstance(content, Text) else Text.from_markup(str(content)).plain
        assert visible("#stat-netgex") == ("+83.0K" if root == "ES" else "+110.2K")
        assert visible("#stat-spot") == ("6,000.00" if root == "ES" else "20,000.00")
        await pilot.press("e")
        export_path = app._last_export
        assert export_path is not None and export_path.is_file()
        exported = json.loads(export_path.read_text())
        assert math.isclose(exported["metrics"]["total_net_gex"], expected_gex(root, "deleted"), rel_tol=2e-6)
        app.save_screenshot(str(directory / f"{root}-terminal.svg"))
        # Apply rollover while the terminal already displays a calculated matrix.
        accepted_boundary = len(recorder.messages)
        for record in scenario(root)["rollover"][len(records):]:
            await adapter._handle_live_record(record)
        for message in recorder.messages[accepted_boundary:]:
            await consumer.update_market_state(message)
        await app.refresh_terminal_data()
        assert app._last_data is None
        assert app.query_one("#gex-table", DataTable).row_count == 0
        assert visible("#stat-netgex") == "--"
        prior_export = app._last_export
        await pilot.press("e")
        assert app._last_export == prior_export, "empty rollover exported stale calculation"
    return {"export": str(export_path), "screenshot": str(directory / f"{root}-terminal.svg"), "empty_rollover_export_blocked": True}


def worker(directory):
    if sys.flags.optimize:
        raise RuntimeError("verification assertions require Python optimization disabled")
    import gex_terminal
    import importlib.metadata
    package_path = Path(gex_terminal.__file__).resolve()
    assert package_path.is_relative_to(Path(sys.prefix).resolve()), "functional test requires an installed wheel outside the checkout"
    # A network attempt in the worker or public CLI is an immediate test failure.
    (directory / "sitecustomize.py").write_text("import socket\ndef blocked(*a, **k):\n raise RuntimeError('network disabled by functional test')\nsocket.socket.connect=blocked\nsocket.socket.connect_ex=blocked\nsocket.create_connection=blocked\n")
    rows = []
    for root in ("ES", "NQ"):
        snapshots = {}
        for stage, records in scenario(root).items():
            input_path = directory / f"{root}-{stage}.jsonl"
            input_path.write_text("".join(json.dumps(record) + "\n" for record in records))
            binary_path = input_path.with_suffix(".dbn")
            write_dbn(records, binary_path)
            for path in (input_path, binary_path):
                report_path = directory / f"{root}-{stage}-{path.suffix[1:]}.json"
                completed = subprocess.run([sys.executable, "-m", "gex_terminal.cli", "databento-replay", str(path), str(report_path), "--symbol", root, "--multiplier", "50" if root == "ES" else "20"], cwd=directory, capture_output=True, text=True, timeout=90)
                assert completed.returncode == 0, completed.stderr
                report = json.loads(report_path.read_text())
                expected = verify_report(report, root, stage)
                key = (root, stage)
                if key in snapshots:
                    assert report["coverage"] == snapshots[key]["coverage"]
                    if report["snapshot"] is not None:
                        assert math.isclose(report["snapshot"]["metrics"]["total_net_gex"], snapshots[key]["snapshot"]["metrics"]["total_net_gex"], rel_tol=1e-10)
                        assert report["snapshot"]["model"]["multiplier_provenance"] == snapshots[key]["snapshot"]["model"]["multiplier_provenance"]
                        assert report["snapshot"]["model"]["position_sources"] == snapshots[key]["snapshot"]["model"]["position_sources"]
                        assert len(report["snapshot"]["strikes"]) == len(snapshots[key]["snapshot"]["strikes"])
                        for left, right in zip(report["snapshot"]["strikes"], snapshots[key]["snapshot"]["strikes"]):
                            assert left.keys() == right.keys()
                            for field in left:
                                if isinstance(left[field], (int, float)):
                                    assert math.isclose(left[field], right[field], rel_tol=1e-10, abs_tol=1e-9), field
                                else:
                                    assert left[field] == right[field], field
                    assert report["underlying_identity"] == snapshots[key]["underlying_identity"]
                snapshots[key] = report
                rows.append({"symbol": root, "stage": stage, "format": path.suffix[1:], "records": len(records), "expected_gex": expected, "passed": True})
        ui = asyncio.run(terminal_check(root, scenario(root)["deleted"], directory))
        rows.append({"symbol": root, "stage": "terminal_export_and_rollover", "passed": True, **ui})
    return {"schema": "gex-terminal.databento-functional.v1", "environment": {"python": sys.version, "platform": platform.platform(), "executable": sys.executable, "package_path": str(package_path), "version": importlib.metadata.version("gex-terminal")},
            "cases": rows, "result": {"passed": True, "network_used": False, "live_transport_certified": False}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python in a fresh candidate-wheel installation")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path, help="Verify installed package bytes against this candidate wheel")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.worker:
        report = worker(Path.cwd())
        output.write_text(json.dumps(report, indent=2) + "\n")
        return 0
    with tempfile.TemporaryDirectory(prefix="gex-databento-functional-") as temporary:
        directory = Path(temporary)
        child_script = directory / Path(__file__).name
        shutil.copyfile(__file__, child_script)
        env = {key: value for key, value in os.environ.items() if not key.startswith(("GEX_", "DATABENTO_", "TRADOVATE_")) and key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONOPTIMIZE"}}
        env["PYTHONPATH"] = str(directory)  # Only the network-blocking sitecustomize, never source packages.
        (directory / "sitecustomize.py").write_text("import socket\ndef blocked(*a, **k):\n raise RuntimeError('network disabled by functional test')\nsocket.socket.connect=blocked\nsocket.socket.connect_ex=blocked\nsocket.create_connection=blocked\n")
        completed = subprocess.run([str(Path(args.python).absolute()), str(child_script), "--worker", "--output", str(output), "--wheel", str(args.wheel.resolve())], cwd=directory, env=env, capture_output=True, text=True, timeout=180)
        if completed.returncode:
            output.write_text(json.dumps({"schema": "gex-terminal.databento-functional.v1", "result": {"passed": False, "network_used": False}, "error": completed.stderr[-6000:]}, indent=2) + "\n")
            print(f"Functional verification failed; see {output}")
            return 1
        report = json.loads(output.read_text())
        evidence = output.parent / (output.stem + "-artifacts")
        evidence.mkdir(exist_ok=True)
        copied = []
        for path in directory.iterdir():
            if path.suffix in {".svg", ".json", ".jsonl", ".dbn"}:
                shutil.copyfile(path, evidence / path.name)
                copied.append(evidence / path.name)
        report["artifacts"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(copied)}
        report["artifact_directory"] = str(evidence)
        for case in report["cases"]:
            for field in ("export", "screenshot"):
                if field in case:
                    case[field] = str(evidence / Path(case[field]).name)
        package_directory = Path(report["environment"]["package_path"]).parent
        try:
            report["wheel_verification"] = verify_installed_wheel(package_directory, args.wheel)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            report["result"]["passed"] = False
            report["error"] = str(error)
            output.write_text(json.dumps(report, indent=2) + "\n")
            return 1
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Functional verification passed: {len(report['cases'])} cases; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

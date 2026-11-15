"""Independent offline CLI for the Wind Tunnel; no ambient provider setup."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import webbrowser

from .wind_tunnel_server import (
    BLIND_COMPARISON, BLIND_REVIEW, BLIND_SESSION_COMPARISON, MAX_JSON_BYTES, SAVED_FLIP_COMPARISON, SAVED_INVESTIGATION_MARKETS,
    SAVED_SESSION_COMPARISON, ReceiptError, canonical_bytes, core_module, decode_json, operation_core,
    make_receipt, reproduce_receipt, start_server, validate_receipt,
)


def add_saved_capture_options(command: argparse.ArgumentParser, help_text: str) -> None:
    for symbol in ("ES", "NQ"):
        command.add_argument(f"--saved-{symbol.lower()}-capture", type=Path, action="append",
                             help=help_text.format(symbol=symbol))


def capture_inputs(es: Path | list[Path] | None, nq: Path | list[Path] | None) -> list[tuple[str, Path]]:
    inputs = []
    for symbol, paths in (("ES", es), ("NQ", nq)):
        for path in (paths,) if isinstance(paths, Path) else (paths or ()):
            inputs.append((symbol, path))
    return inputs


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="gex-terminal wind-tunnel",
                                     description="Explore bundled scenarios or an explicit frozen Terminal checkpoint in a local browser.")
    commands = result.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Open the local offline workbench (default command).")
    serve.add_argument("--port", type=int, default=8765, help="Loopback port; 0 selects a free port (default: 8765).")
    serve.add_argument("--no-browser", action="store_true", help="Print the local launch URL without opening a browser.")
    serve.add_argument("--workspace", type=Path,
                       help="Empty or owned research directory, separate from the application.")
    serve.add_argument("--checkpoint", type=Path,
                       help="Read one explicit local demo/replay checkpoint; the browser cannot select input paths.")
    serve.add_argument("--comparison-checkpoint", type=Path, action="append", default=[],
                       help="Add an explicit saved checkpoint to the source picker; repeat at most twice and use --checkpoint for the initial source.")
    add_saved_capture_options(serve, "Open a local {symbol} capture. Repeat for a second {symbol} session.")
    serve.add_argument("--saved-capture-sha256", help=argparse.SUPPRESS)
    serve.add_argument("--comparison-capture-sha256", help=argparse.SUPPRESS)
    serve.add_argument("--comparison-workspace", type=Path, help=argparse.SUPPRESS)
    serve.add_argument("--blind-review", action="store_true",
                       help="Review flips from one or two distinct saved ES or NQ captures in one window.")
    serve.add_argument("--flip-sequence", type=int,
                       help="Choose the initial capture's exact flip sequence (ES when both markets are supplied).")
    example = commands.add_parser("example", help="Calculate a bundled example and produce a portable receipt.")
    example.add_argument("name", choices=core_module().EXAMPLE_NAMES)
    example.add_argument("--output", type=Path, help="Write a new JSON file; otherwise print JSON.")
    for name, help_text in (("verify", "Verify receipt integrity and reproduce its exact result."),
                            ("reproduce", "Recalculate a portable receipt and report exact agreement.")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("receipt", type=Path)
        command.add_argument("--output", type=Path, help="Write a new JSON report; otherwise print JSON.")
        add_saved_capture_options(command, "Original local {symbol} capture. Repeat when both receipt inputs are {symbol}.")
    return result


def read_artifact(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
            raise ReceiptError("Input must be a regular JSON file no larger than 32 MiB.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return decode_json(stream.read(MAX_JSON_BYTES + 1))
    finally:
        os.close(fd)


def emit_artifact(value: dict, output: Path | None):
    data = canonical_bytes(value) + b"\n"
    if output is None:
        print(data.decode("utf-8"), end="")
        return
    # Explicit file path only; never replace a prior result or follow a symlink.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    print("Wrote Wind Tunnel JSON artifact.")


def registered_capture_specs(captures, checkpoint, comparisons, primary_digest, comparison_digest):
    from .wind_tunnel_checkpoint import read_checkpoint

    if primary_digest is None:
        raise ReceiptError("A saved capture paired with a prebuilt checkpoint requires its registered digest.")
    primary = read_checkpoint(checkpoint)
    symbol = primary["source"]["symbol"]
    if symbol not in captures:
        raise ReceiptError("The primary checkpoint must match one of the selected capture markets.")
    specs = {symbol: (captures[symbol], primary_digest, primary["sha256"])}
    if len(captures) == 2:
        other = next(market for market in captures if market != symbol)
        matches = [artifact for path in comparisons if (artifact := read_checkpoint(path))["source"]["symbol"] == other]
        if len(matches) != 1 or comparison_digest is None:
            raise ReceiptError("The second saved capture needs its matching comparison checkpoint and registered digest.")
        specs[other] = (captures[other], comparison_digest, matches[0]["sha256"])
    elif comparison_digest is not None:
        raise ReceiptError("A comparison capture digest requires a second saved capture.")
    return specs


async def serve(workspace: Path, *, port: int, no_browser: bool, checkpoint: Path | None = None,
                comparison_checkpoints=(), saved_es_capture: Path | list[Path] | None = None,
                saved_nq_capture: Path | list[Path] | None = None, saved_capture_sha256: str | None = None,
                comparison_capture_sha256: str | None = None, comparison_workspace: Path | None = None) -> int:
    from .wind_tunnel_sources import checkpoint_core

    captures = capture_inputs(saved_es_capture, saved_nq_capture)
    symbols = {symbol for symbol, _ in captures}
    if len(captures) > 2:
        raise ReceiptError("Open at most two saved capture files per Wind Tunnel window.")
    if len({path.absolute() for _, path in captures}) != len(captures):
        raise ReceiptError("Choose two different saved captures.")
    if any(value is not None for value in (saved_capture_sha256, comparison_capture_sha256)) and (checkpoint is None or not captures):
        raise ReceiptError("A preverified capture digest requires both its saved checkpoint and capture.")
    if comparison_workspace is not None and symbols != {"ES", "NQ"}:
        raise ReceiptError("Per-market receipt workspaces require a saved ES capture and a saved NQ capture.")

    with ExitStack() as resources:
        saved_replays = {}
        if captures:
            from .wind_tunnel_saved_replay import SavedReplay
            if checkpoint is None:
                from .saved_workspace import prepare_saved_workspace
                directory = Path(resources.enter_context(TemporaryDirectory(prefix="gex-saved-replays-")))
                specs = []
                for index, (symbol, path) in enumerate(captures, start=1):
                    plan = await asyncio.to_thread(prepare_saved_workspace, path, symbol, directory / str(index))
                    prepared = Path(plan["checkpoint_path"])
                    if checkpoint is None:
                        checkpoint = prepared
                    else:
                        comparison_checkpoints = (*comparison_checkpoints, prepared)
                    specs.append((symbol, Path(plan["capture_path"]), plan["capture_sha256"], plan["checkpoint_sha256"]))
            else:
                if len(symbols) != len(captures):
                    raise ReceiptError("To compare two sessions of the same market, supply both capture files directly.")
                registered = registered_capture_specs(dict(captures), checkpoint, comparison_checkpoints,
                                                       saved_capture_sha256, comparison_capture_sha256)
                specs = [(symbol, *binding) for symbol, binding in registered.items()]
            if len({capture_digest for _, _, capture_digest, _ in specs}) != len(specs):
                raise ReceiptError("Choose two different saved captures.")
            for symbol, path, capture_digest, checkpoint_digest in specs:
                replay = SavedReplay(path, capture_digest, symbol=symbol)
                resources.callback(replay.close)
                saved_replays[checkpoint_digest] = replay

        core = checkpoint_core(checkpoint, comparison_checkpoints)
        if len(symbols) == 2:
            source = "saved ES and NQ replays."
        elif len(captures) == 2:
            source = f"two saved {captures[0][0]} replays."
        elif captures:
            source = f"a saved {captures[0][0]} replay."
        else:
            source = "a frozen Terminal checkpoint." if core is not None else "bundled synthetic data."
        await serve_window(workspace, port, no_browser, source, core=core, saved_replays=saved_replays,
                           comparison_workspace=comparison_workspace)
    return 0


async def serve_window(workspace: Path, port: int, no_browser: bool, source: str, **options) -> None:
    runner, url = await start_server(workspace, port=port, **options)
    try:
        print("Wind Tunnel is running locally with " + source, flush=True)
        print(url, flush=True)
        print("Keep this terminal open. Press Ctrl+C to stop. Save receipts to preserve research.", flush=True)
        if not no_browser:
            try:
                opened = await asyncio.to_thread(webbrowser.open, url)
            except Exception:
                opened = False
            if not opened:
                print("Open the launch URL above in your browser.", flush=True)
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def serve_blind_review(args) -> int:
    from .wind_tunnel_blind_review import BlindReview
    from .wind_tunnel_blind_session_comparison import SIDES
    from .wind_tunnel_saved_replay import SavedReplay
    from .wind_tunnel_sources import saved_capture_digest

    captures = capture_inputs(args.saved_es_capture, args.saved_nq_capture)
    if (not 1 <= len(captures) <= 2 or args.checkpoint is not None
            or args.comparison_checkpoint or args.saved_capture_sha256 is not None
            or args.comparison_capture_sha256 is not None or args.comparison_workspace is not None):
        raise ReceiptError("Blind review requires one or two completed local captures using the saved capture flags.")
    if len({path.absolute() for _, path in captures}) != len(captures):
        raise ReceiptError("Choose two different saved captures.")
    if args.flip_sequence is not None and args.flip_sequence < 1:
        raise ReceiptError("Choose a positive saved flip sequence.")

    symbols = {symbol for symbol, _ in captures}
    same_market = len(captures) == 2 and len(symbols) == 1
    digests = [None] * len(captures)
    if same_market:
        try:
            digests = [await asyncio.to_thread(saved_capture_digest, path) for _, path in captures]
        except (ValueError, OSError) as exc:
            raise ReceiptError("A supplied saved capture could not be read for blind review.") from exc
        if digests[0] == digests[1]:
            raise ReceiptError("Choose two different saved captures.")

    with ExitStack() as resources:
        reviews = {}
        for index, (symbol, path) in enumerate(captures):
            replay = SavedReplay(path, digests[index], symbol=symbol)
            resources.callback(replay.close)
            key = SIDES[index] if same_market else symbol
            reviews[key] = BlindReview(replay, sequence=args.flip_sequence if index == 0 else None)
        if same_market:
            source = f"two blind {captures[0][0]} replay reviews."
        elif len(reviews) == 2:
            source = "blind ES and NQ replay reviews."
        else:
            source = f"a blind {captures[0][0]} replay review."
        await serve_window(args.workspace or Path("wind_tunnel_reviews"), args.port, args.no_browser,
                           source, blind_reviews=reviews)
    return 0


async def run(args) -> int:
    if args.command == "serve":
        if args.blind_review:
            return await serve_blind_review(args)
        if args.flip_sequence is not None:
            raise ReceiptError("--flip-sequence requires --blind-review.")
        options = {"port": args.port, "no_browser": args.no_browser}
        if args.checkpoint is not None:
            options["checkpoint"] = args.checkpoint
        if args.comparison_checkpoint:
            options["comparison_checkpoints"] = args.comparison_checkpoint
        if any(value is not None for value in (args.saved_es_capture, args.saved_nq_capture, args.saved_capture_sha256)):
            options.update(saved_es_capture=args.saved_es_capture, saved_nq_capture=args.saved_nq_capture,
                           saved_capture_sha256=args.saved_capture_sha256)
        if args.comparison_capture_sha256 is not None:
            options["comparison_capture_sha256"] = args.comparison_capture_sha256
        if args.comparison_workspace is not None:
            options["comparison_workspace"] = args.comparison_workspace
        return await serve(args.workspace or Path("wind_tunnel_research"), **options)
    if args.command == "example":
        example = core_module().examples(args.name)
        result = await make_receipt(example["title"], example["operation"], example["request"])
        emit_artifact(result, args.output)
        return 0
    receipt = validate_receipt(read_artifact(args.receipt))
    captures = capture_inputs(args.saved_es_capture, args.saved_nq_capture)
    kind = receipt["kind"]
    with ExitStack() as resources:
        sources = {}
        if kind in (SAVED_FLIP_COMPARISON, BLIND_COMPARISON):
            from .wind_tunnel_saved_replay import SavedReplay
            if len(captures) != 2 or {symbol for symbol, _ in captures} != {"ES", "NQ"}:
                raise ReceiptError("Reproduce this comparison with both --saved-es-capture and --saved-nq-capture.")
            try:
                selection = operation_core(kind).normalize_request(receipt["request"])
            except ValueError as exc:
                raise ReceiptError(str(exc)) from exc
            replays = {}
            for symbol, path in captures:
                replay = SavedReplay(path, selection[symbol.lower()]["capture_sha256"], symbol=symbol)
                resources.callback(replay.close)
                replays[symbol] = replay
            sources["comparison_replays"] = replays
        elif kind in (SAVED_SESSION_COMPARISON, BLIND_SESSION_COMPARISON):
            sources["session_replays"] = await comparison_receipt_replays(receipt, captures, resources)
        elif captures or kind == BLIND_REVIEW:
            from .wind_tunnel_saved_replay import SavedReplay
            if kind == BLIND_REVIEW:
                flip = receipt["result"].get("flip")
                source = flip.get("source") if isinstance(flip, dict) else None
                symbol = source.get("symbol") if isinstance(source, dict) else None
                if symbol not in ("ES", "NQ"):
                    raise ReceiptError("The blind review receipt requires an ES or NQ source identity.")
                if len(captures) != 1 or captures[0][0] != symbol:
                    raise ReceiptError(f"Reproduce this review with its original --saved-{symbol.lower()}-capture.")
            else:
                symbol = SAVED_INVESTIGATION_MARKETS.get(kind)
                if len(captures) != 1 or captures[0][0] != symbol:
                    raise ReceiptError("Supply the single saved capture matching the investigation receipt's market.")
            replay = SavedReplay(captures[0][1], receipt["request"].get("capture_sha256"), symbol=symbol)
            resources.callback(replay.close)
            sources["saved_replay"] = replay
        result = await reproduce_receipt(receipt, **sources)
    emit_artifact(result, args.output)
    return 0 if result["status"] == "verified" else 1


async def comparison_receipt_replays(receipt, captures, resources):
    from .wind_tunnel_saved_replay import SavedReplay
    from .wind_tunnel_session_comparison import SIDES
    from .wind_tunnel_sources import saved_capture_digest

    if len(captures) != 2:
        raise ReceiptError("Supply both original capture files using the saved capture flags for their markets.")
    try:
        producer = operation_core(receipt["kind"])
        if receipt["kind"] == BLIND_SESSION_COMPARISON:
            expected = producer.capture_slots(receipt["request"])
        else:
            selection = producer.normalize_request(receipt["request"])
            expected = {(selection[side]["symbol"], selection[side]["capture_sha256"]): side for side in SIDES}
    except ValueError as exc:
        raise ReceiptError(str(exc)) from exc

    replays = {}
    for symbol, path in captures:
        try:
            checksum = await asyncio.to_thread(saved_capture_digest, path)
        except (ValueError, OSError) as exc:
            raise ReceiptError("A supplied saved capture could not be read for comparison verification.") from exc
        side = expected.pop((symbol, checksum), None)
        if side is None:
            raise ReceiptError("Each supplied capture must match a different receipt checksum and its market.")
        replay = SavedReplay(path, checksum, symbol=symbol)
        resources.callback(replay.close)
        replays[side] = replay
    return replays


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0].startswith("--") and arguments[0] not in ("--help",):
        arguments.insert(0, "serve")
    args = parser().parse_args(arguments)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Wind Tunnel stopped. Saved research remains in its workspace.")
        return 0
    except ReceiptError as exc:
        print(f"Wind Tunnel: {exc}", file=sys.stderr)
    except FileExistsError:
        print("Wind Tunnel: output already exists; choose a new file.", file=sys.stderr)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        print("Wind Tunnel: invalid or unsupported input; inspect the command help.", file=sys.stderr)
    except OSError:
        print("Wind Tunnel: local file or port is unavailable; check the selected workspace, input and port.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

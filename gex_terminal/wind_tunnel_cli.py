"""Independent offline CLI for the Wind Tunnel; no ambient provider setup."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import stat
import sys
import webbrowser

from .wind_tunnel_server import (
    MAX_JSON_BYTES, ReceiptError, canonical_bytes, core_module, decode_json,
    make_receipt, reproduce_receipt, start_server,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="gex-terminal wind-tunnel",
                                     description="Explore bundled synthetic scenarios in an offline local browser.")
    commands = result.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Open the local offline workbench (default command).")
    serve.add_argument("--port", type=int, default=8765, help="Loopback port; 0 selects a free port (default: 8765).")
    serve.add_argument("--no-browser", action="store_true", help="Print the local launch URL without opening a browser.")
    serve.add_argument("--workspace", type=Path, default=Path("wind_tunnel_research"),
                       help="Empty or owned research directory, separate from the application.")
    example = commands.add_parser("example", help="Calculate a bundled example and produce a portable receipt.")
    example.add_argument("name", choices=core_module().EXAMPLE_NAMES)
    example.add_argument("--output", type=Path, help="Write a new JSON file; otherwise print JSON.")
    for name, help_text in (("verify", "Verify receipt integrity and reproduce its exact result."),
                            ("reproduce", "Recalculate a portable receipt and report exact agreement.")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("receipt", type=Path)
        command.add_argument("--output", type=Path, help="Write a new JSON report; otherwise print JSON.")
    return result


def read_artifact(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
            raise ReceiptError("Input must be a regular JSON file no larger than 4 MiB.")
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


async def serve(workspace: Path, *, port: int, no_browser: bool) -> int:
    runner, url = await start_server(workspace, port=port)
    try:
        print("Wind Tunnel is running locally with bundled synthetic data.", flush=True)
        print(url, flush=True)
        print("Keep this terminal open. Press Ctrl+C to stop. Save receipts to preserve research.", flush=True)
        if not no_browser:
            try:
                opened = await asyncio.to_thread(webbrowser.open, url)
                if not opened:
                    print("Open the launch URL above in your browser.", flush=True)
            except Exception:
                print("Open the launch URL above in your browser.", flush=True)
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
    return 0


async def run(args) -> int:
    if args.command == "serve":
        return await serve(args.workspace, port=args.port, no_browser=args.no_browser)
    if args.command == "example":
        example = core_module().examples(args.name)
        result = await make_receipt(example["title"], example["operation"], example["request"])
        emit_artifact(result, args.output)
        return 0
    result = await reproduce_receipt(read_artifact(args.receipt))
    emit_artifact(result, args.output)
    return 0 if result["status"] == "verified" else 1


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

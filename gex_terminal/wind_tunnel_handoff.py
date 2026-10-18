"""Owned loopback service for an explicit frozen Terminal handoff.

Only the caller can supply a checkpoint or local output location. The browser
never selects a path, and a new handoff replaces only this owner's service.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import webbrowser

from .wind_tunnel import TerminalCheckpointCore
from .wind_tunnel_checkpoint import read_checkpoint, validate_checkpoint, write_checkpoint
from .wind_tunnel_server import canonical_bytes, start_server


class TerminalHandoff:
    def __init__(self, directory: Path | str = "wind_tunnel_handoffs"):
        self.directory = Path(directory)
        self.checkpoint_path: Path | None = None
        self.launch_url: str | None = None
        self._runner = None
        self._runners = []
        self._lock = asyncio.Lock()
        self._closed = False

    async def open(self, artifact: dict) -> bool:
        """Start a fresh fixed-source service; return whether a browser opened."""
        # Validate/copy before touching storage or replacing a healthy server.
        artifact = validate_checkpoint(artifact)
        identity = hashlib.sha256(canonical_bytes(artifact)).hexdigest()
        async with self._lock:
            if self._closed:
                raise ValueError("The Terminal handoff owner has stopped.")
            if self.directory.is_symlink():
                raise ValueError("Choose a local handoff directory, not a symbolic link.")
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            checkpoint_path = self.directory / f"checkpoint-{identity}.json"
            if checkpoint_path.exists():
                if read_checkpoint(checkpoint_path) != artifact:
                    raise ValueError("The saved checkpoint differs; preserve it and choose a new folder.")
            else:
                write_checkpoint(checkpoint_path, artifact)
            runner, url = await start_server(
                self.directory / f"research-{identity}", port=0,
                core=TerminalCheckpointCore(artifact),
            )
            previous = self._runner
            self._runners.append(runner)
            self._runner, self.launch_url = runner, url
            self.checkpoint_path = checkpoint_path.resolve()
            try:
                if previous is not None:
                    await self._cleanup(previous)
            except BaseException:
                try:
                    await self._cleanup(runner)
                finally:
                    self._runner = previous
                    self.launch_url = None
                raise
            try:
                # The capability stays in memory/the launch URL, never artifacts.
                return bool(await asyncio.to_thread(webbrowser.open, url))
            except asyncio.CancelledError:
                try:
                    await self._cleanup(runner)
                finally:
                    self._runner, self.launch_url = None, None
                raise
            except Exception:
                # Browser failure does not discard the checkpoint or receipt store.
                return False

    async def _cleanup(self, runner) -> None:
        # Interrupted cleanup retains ownership so close() can retry it.
        await runner.cleanup()
        self._runners.remove(runner)

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self.launch_url = None
            errors = []
            for runner in tuple(self._runners):
                try:
                    await self._cleanup(runner)
                except Exception as exc:
                    errors.append(exc)
            if self._runner not in self._runners:
                self._runner = None
            if errors:
                raise errors[0]

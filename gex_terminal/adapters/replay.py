import asyncio
import json
from pathlib import Path
from typing import Iterable

from gex_terminal.market_data_adapter import MarketDataAdapter, dumps_normalized_message


class ReplayAdapter(MarketDataAdapter):
    """Feeds normalized JSONL market-data events into the consumer."""

    def __init__(
        self,
        consumer,
        replay_path: str | Path,
        delay_seconds: float = 0.05,
        loop: bool = False,
    ):
        self.consumer = consumer
        self.replay_path = Path(replay_path)
        self.delay_seconds = delay_seconds
        self.loop = loop

    async def stream_market_data(self) -> None:
        if not self.replay_path.exists():
            raise FileNotFoundError(f"Replay file not found: {self.replay_path}")

        self.consumer.mark_connected()
        try:
            while True:
                for message in self._load_messages():
                    await self.consumer.update_market_state(dumps_normalized_message(message))
                    await asyncio.sleep(self.delay_seconds)

                if not self.loop:
                    break
        finally:
            self.consumer.mark_disconnected()

    def _load_messages(self) -> Iterable[dict]:
        with self.replay_path.open(encoding="utf-8") as replay_file:
            for line_number, line in enumerate(replay_file, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in replay file {self.replay_path} at line {line_number}"
                    ) from exc

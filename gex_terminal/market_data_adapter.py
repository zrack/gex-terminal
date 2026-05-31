import json
from abc import ABC, abstractmethod
from typing import Any


NormalizedMessage = dict[str, Any]

OPTION_TYPES = {"C", "P"}


class MarketDataAdapter(ABC):
    """Common async contract for live and replay market-data adapters."""

    @abstractmethod
    async def stream_market_data(self) -> None:
        """Stream normalized market-data messages into a consumer."""


def validate_normalized_message(message: NormalizedMessage) -> None:
    message_type = message.get("type")

    if message_type == "underlying_tick":
        _require_fields(message, ("symbol", "price"))
        return

    if message_type == "options_volume_tick":
        _require_fields(message, ("strike", "option_type", "volume"))
        option_type = str(message["option_type"]).upper()
        if option_type not in OPTION_TYPES:
            raise ValueError(f"Unsupported option_type: {message['option_type']}")
        return

    raise ValueError(f"Unsupported normalized message type: {message_type}")


def dumps_normalized_message(message: NormalizedMessage) -> str:
    validate_normalized_message(message)
    return json.dumps(message)


def _require_fields(message: NormalizedMessage, fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if message.get(field) in (None, "")]
    if missing:
        raise ValueError(
            f"Missing required field(s) for {message.get('type')}: {', '.join(missing)}"
        )

"""Safe, configurable process logging for command-line runtimes."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from typing import IO

from gex_terminal.redaction import environment_secret_values, redact_sensitive, redact_text


DEFAULT_LOG_LEVEL = "WARNING"
LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


class SensitiveDataFilter(logging.Filter):
    """Redact messages and arguments before any configured handler formats them."""

    def __init__(self, *, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.secrets = tuple(secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.msg, secrets=self.secrets)
        if record.args:
            record.args = redact_sensitive(record.args, secrets=self.secrets)
        rendered = record.getMessage()
        record.msg = redact_text(rendered, secrets=self.secrets)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text, secrets=self.secrets)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info, secrets=self.secrets)
        return True


class SensitiveDataFormatter(logging.Formatter):
    """Format exception tracebacks only after applying the central sanitizer."""

    def __init__(self, fmt: str, *, secrets: tuple[str, ...] = ()) -> None:
        super().__init__(fmt)
        self.secrets = tuple(secrets)

    def formatException(self, ei) -> str:  # noqa: N802 - logging API name
        return redact_text(super().formatException(ei), secrets=self.secrets)


def resolve_log_level(
    cli_level: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve and validate CLI/environment logging configuration."""
    environment = os.environ if environ is None else environ
    raw_level = cli_level if cli_level is not None else environment.get(
        "GEX_LOG_LEVEL", DEFAULT_LOG_LEVEL
    )
    normalized = str(raw_level).strip().upper()
    if normalized not in LOG_LEVELS:
        raise ValueError(
            "GEX log level must be one of: " + ", ".join(LOG_LEVELS)
        )
    return normalized


def configure_logging(
    cli_level: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stream: IO[str] | None = None,
) -> str:
    """Install one redacting root handler and return the effective level name."""
    environment = os.environ if environ is None else environ
    level_name = resolve_log_level(cli_level, environ=environment)
    secrets = environment_secret_values(environment)
    handler = logging.StreamHandler(sys.stderr if stream is None else stream)
    handler.setFormatter(SensitiveDataFormatter(LOG_FORMAT, secrets=secrets))
    handler.addFilter(SensitiveDataFilter(secrets=secrets))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level_name))
    return level_name

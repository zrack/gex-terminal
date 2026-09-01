"""Central recursive redaction for logs and derived safety artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Iterable


REDACTED = "[redacted]"
RECURSIVE_VALUE = "[recursive]"

_SENSITIVE_KEY_NAMES = {
    "account",
    "accountid",
    "accountids",
    "accountidentifier",
    "accountidentifiers",
    "accountnumber",
    "accountnumbers",
    "accesstoken",
    "apikey",
    "apikeys",
    "apisecret",
    "auth",
    "authorization",
    "clientsecret",
    "cookie",
    "credential",
    "credentials",
    "licensedpayload",
    "mdaccesstoken",
    "password",
    "passwd",
    "payloadfragment",
    "privatepayload",
    "providerpayload",
    "rawframe",
    "rawpayload",
    "refreshtoken",
    "secret",
    "sessionsecret",
    "setcookie",
    "subscriptionid",
    "subscriptionids",
    "subscriptionidentifier",
    "subscriptionidentifiers",
    "token",
}
_SENSITIVE_KEY_SUFFIXES = (
    "accountid",
    "accountids",
    "accountidentifier",
    "accountidentifiers",
    "accountnumber",
    "accountnumbers",
    "apikey",
    "apikeys",
    "apisecret",
    "password",
    "secret",
    "subscriptionid",
    "subscriptionids",
    "subscriptionidentifier",
    "subscriptionidentifiers",
    "token",
)
_PROVIDER_CREDENTIAL_ENV_NAMES = {
    "DATABENTO_API_KEY",
    "TRADOVATE_APP_ID",
    "TRADOVATE_CID",
    "TRADOVATE_NAME",
    "TRADOVATE_PASSWORD",
    "TRADOVATE_SEC",
}

_TEXT_KEY = (
    r"api[_-]?(?:keys?|secret)|access[_-]?token|refresh[_-]?token|"
    r"md[_-]?access[_-]?token|authorization|password|passwd|client[_-]?secret|"
    r"account(?:[_-]?(?:ids?|identifiers?|numbers?))?|"
    r"subscription[_-]?(?:ids?|identifiers?)|session[_-]?secret|"
    r"raw[_-]?(?:payload|frame)|provider[_-]?payload|licensed[_-]?payload|"
    r"payload[_-]?fragment|credential(?:s)?|cookie|secret|token"
)
_QUOTED_ASSIGNMENT = re.compile(
    rf"(?P<prefix>[\"']?(?:{_TEXT_KEY})[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE,
)
_UNQUOTED_ASSIGNMENT = re.compile(
    rf"(?P<prefix>\b(?:{_TEXT_KEY})\b\s*[:=]\s*)"
    r"(?P<value>(?![\"'])[^\s,;&{}\[\]]+)",
    re.IGNORECASE,
)
_COMPOSITE_ASSIGNMENT = re.compile(
    rf"(?P<prefix>[\"']?(?:{_TEXT_KEY})[\"']?\s*[:=]\s*)"
    r"(?P<value>[\[{])",
    re.IGNORECASE,
)
_BEARER_TOKEN = re.compile(r"(?P<prefix>\bBearer\s+)[^\s,;]+", re.IGNORECASE)
_LOGGING_PLACEHOLDER = re.compile(
    r"%(?:\([^)]+\))?[#0 +\-]?\d*(?:\.\d+)?[diouxXeEfFgGcrsa%]"
)


def is_sensitive_key(key: Any) -> bool:
    """Return whether a mapping key denotes secret or private identifier data."""
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return normalized in _SENSITIVE_KEY_NAMES or normalized.endswith(
        _SENSITIVE_KEY_SUFFIXES
    )


def environment_secret_values(environ: Mapping[str, str]) -> tuple[str, ...]:
    """Collect configured credentials without exposing their names or values."""
    values = []
    for name, value in environ.items():
        if not value:
            continue
        if name in _PROVIDER_CREDENTIAL_ENV_NAMES or is_sensitive_key(name):
            values.append(str(value))
    return _normalized_secrets(values)


def redact_text(
    value: str,
    *,
    secrets: Iterable[str] = (),
    replacement: str = REDACTED,
) -> str:
    """Redact declared secrets and recognizable key/value credentials in text."""
    redacted = str(value)
    normalized_secrets = _normalized_secrets(secrets)
    for secret in normalized_secrets:
        redacted = redacted.replace(secret, replacement)
    redacted = _redact_json_document(
        redacted,
        secrets=normalized_secrets,
        replacement=replacement,
    )
    redacted = _BEARER_TOKEN.sub(
        lambda match: f"{match.group('prefix')}{replacement}", redacted
    )
    redacted = _redact_composite_assignments(redacted, replacement=replacement)
    redacted = _QUOTED_ASSIGNMENT.sub(
        lambda match: (
            match.group(0)
            if _LOGGING_PLACEHOLDER.fullmatch(match.group("value"))
            else (
                f"{match.group('prefix')}{match.group('quote')}"
                f"{replacement}{match.group('quote')}"
            )
        ),
        redacted,
    )
    return _UNQUOTED_ASSIGNMENT.sub(
        lambda match: (
            match.group(0)
            if _LOGGING_PLACEHOLDER.fullmatch(match.group("value"))
            else f"{match.group('prefix')}{replacement}"
        ),
        redacted,
    )


def _redact_json_document(
    value: str,
    *,
    secrets: tuple[str, ...],
    replacement: str,
) -> str:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if not isinstance(parsed, (Mapping, list)):
        return value
    return json.dumps(
        redact_sensitive(parsed, secrets=secrets, replacement=replacement),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _redact_composite_assignments(value: str, *, replacement: str) -> str:
    decoder = json.JSONDecoder()
    output: list[str] = []
    position = 0
    while True:
        match = _COMPOSITE_ASSIGNMENT.search(value, position)
        if match is None:
            output.append(value[position:])
            break
        composite_start = match.start("value")
        output.append(value[position:composite_start])
        output.append(replacement)
        if value.startswith(replacement, composite_start):
            position = composite_start + len(replacement)
            continue
        try:
            _parsed, consumed = decoder.raw_decode(value[composite_start:])
        except json.JSONDecodeError:
            # The sensitive value is malformed or truncated. Hiding the
            # remainder is safer than leaking a fragment after the opener.
            position = len(value)
            break
        position = composite_start + consumed
    return "".join(output)


def redact_sensitive(
    value: Any,
    *,
    secrets: Iterable[str] = (),
    replacement: str = REDACTED,
) -> Any:
    """Return a recursively redacted copy without mutating the input value."""
    normalized_secrets = _normalized_secrets(secrets)
    return _redact_value(
        value,
        secrets=normalized_secrets,
        replacement=replacement,
        active_ids=set(),
    )


def _redact_value(
    value: Any,
    *,
    secrets: tuple[str, ...],
    replacement: str,
    active_ids: set[int],
) -> Any:
    if isinstance(value, str):
        return redact_text(value, secrets=secrets, replacement=replacement)
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return replacement.encode("utf-8")
        return redact_text(text, secrets=secrets, replacement=replacement).encode("utf-8")

    is_container = isinstance(value, (Mapping, list, tuple, set, frozenset))
    if is_container:
        identity = id(value)
        if identity in active_ids:
            return RECURSIVE_VALUE
        active_ids.add(identity)
        try:
            if isinstance(value, Mapping):
                return {
                    key: (
                        replacement
                        if is_sensitive_key(key)
                        else _redact_value(
                            nested,
                            secrets=secrets,
                            replacement=replacement,
                            active_ids=active_ids,
                        )
                    )
                    for key, nested in value.items()
                }
            if isinstance(value, list):
                return [
                    _redact_value(
                        item,
                        secrets=secrets,
                        replacement=replacement,
                        active_ids=active_ids,
                    )
                    for item in value
                ]
            if isinstance(value, tuple):
                return tuple(
                    _redact_value(
                        item,
                        secrets=secrets,
                        replacement=replacement,
                        active_ids=active_ids,
                    )
                    for item in value
                )
            redacted_items = (
                _redact_value(
                    item,
                    secrets=secrets,
                    replacement=replacement,
                    active_ids=active_ids,
                )
                for item in value
            )
            return type(value)(redacted_items)
        finally:
            active_ids.remove(identity)
    return value


def _normalized_secrets(secrets: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {str(secret) for secret in secrets if secret is not None and str(secret)},
            key=len,
            reverse=True,
        )
    )

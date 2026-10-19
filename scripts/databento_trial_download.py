"""Small, cost-previewed historical requests for the local ES/NQ trial.

Run from the checkout with ``.venv/bin/python -m scripts.databento_trial_download``.
Only ``quote`` and ``download`` make network requests; neither uses the Live API.
"""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / ".env.databento"
DATA_ROOT = ROOT / "historical_sessions" / "databento_trial"
DATASET = "GLBX.MDP3"
KEY_PATTERN = re.compile(r"db-[A-Za-z0-9_-]{29}\Z")
RECORD_LIMIT = 60000
MANIFEST_SCHEMA = "gex-terminal.databento-credit-trial.v1"
REQUEST_SCHEMAS = frozenset({"definition", "bbo-1s", "mbp-1", "trades"})
# Only recognized technical identifiers may leave a provider exception. Never
# print its message, body, headers, request ID, or arbitrary case strings.
PROVIDER_CASES = frozenset({
    "auth_failed", "auth_required", "invalid_api_key", "api_key_disabled",
    "invalid_request", "invalid_symbol", "no_symbols_resolved", "symbol_not_found",
    "license_missing", "not_entitled", "insufficient_funds", "usage_limit_exceeded",
    "rate_limit_exceeded", "dataset_unavailable", "data_end_after_available_end",
    "data_start_before_available_start", "data_range_is_empty",
})


class TrialSetupError(ValueError):
    """An operator-safe message, unlike arbitrary provider exceptions."""


class TrialRequestError(TrialSetupError):
    """A request failure with only allowlisted diagnostic information."""

    def __init__(self, stage: str, schema: str, error: Exception) -> None:
        self.stage = stage if stage in {"quote", "download", "validation"} else "download"
        self.schema = schema if schema in REQUEST_SCHEMAS else "unknown"
        status = getattr(error, "http_status", None)
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None
        body = getattr(error, "json_body", None)
        detail = body.get("detail") if isinstance(body, dict) else None
        case = detail.get("case") if isinstance(detail, dict) else None
        self.provider_case = case if isinstance(case, str) and case in PROVIDER_CASES else None
        diagnostics = []
        if self.http_status is not None:
            diagnostics.append(f"HTTP {self.http_status}")
        if self.provider_case is not None:
            diagnostics.append(f"case {self.provider_case}")
        suffix = f" ({'; '.join(diagnostics)})" if diagnostics else ""
        consequence = (
            "No market data downloaded."
            if self.stage == "quote" else
            "Retained partial files may have used credits; no automatic retry."
        )
        super().__init__(f"Historical {self.stage} failed for {self.schema}{suffix}. {consequence}")


def existing_output_message(output_dir: Path, symbol: str) -> str:
    """Describe a prior stop without trusting saved free-form diagnostics."""
    requested_symbol = symbol if symbol in {"ES", "NQ"} else "Selected"
    message = f"{requested_symbol} trial directory already exists: {output_dir}."
    stopped = output_dir / "download-stopped.json"
    try:
        info = stopped.lstat()
        if output_dir.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            return message + " No automatic retry or overwrite is allowed."
        manifest = json.loads(stopped.read_text(encoding="utf-8"))
        if (
            isinstance(manifest, dict)
            and manifest.get("schema") == MANIFEST_SCHEMA
            and manifest.get("status") in {"stopped_request_error", "stopped_empty_or_record_limit"}
            and manifest.get("stopped_stage") in {"download", "validation"}
            and manifest.get("stopped_schema") in REQUEST_SCHEMAS
        ):
            message += f" Previous stop: {manifest['stopped_stage']} for {manifest['stopped_schema']}."
    except (OSError, ValueError, TypeError):
        pass
    return message + " Existing data was preserved; no automatic retry or overwrite is allowed."


def save_stopped_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    """Best effort: a filesystem failure must not hide the original safe error."""
    try:
        private_write(output_dir / "download-stopped.json", json.dumps(manifest, indent=2) + "\n")
    except OSError:
        pass


def private_write(path: Path, value: str) -> None:
    """Never follow or overwrite an existing file when saving local material."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(value)


def save_key(path: Path = KEY_FILE) -> None:
    if not sys.stdin.isatty():
        raise TrialSetupError("Run set-key in an interactive terminal so the key stays hidden.")
    key = getpass.getpass("Paste Databento API key (hidden): ").strip()
    if not KEY_PATTERN.fullmatch(key):
        raise TrialSetupError("Expected a 32-character Databento key beginning db-.")
    private_write(path, f"DATABENTO_API_KEY={key}\n")
    print("Key saved locally with owner-only permissions; no network request made.")


def read_key(path: Path = KEY_FILE) -> str:
    if not path.exists():
        raise TrialSetupError("No local key yet. Run the set-key command first.")
    permissions = path.lstat()
    if not stat.S_ISREG(permissions.st_mode) or stat.S_IMODE(permissions.st_mode) & 0o077:
        raise TrialSetupError("Key file must be a regular owner-only file (chmod 600).")
    from dotenv import dotenv_values

    values = dotenv_values(path, interpolate=False)
    if set(values) != {"DATABENTO_API_KEY"}:
        raise TrialSetupError("The trial key file must contain only DATABENTO_API_KEY.")
    key = values["DATABENTO_API_KEY"] or ""
    if not KEY_PATTERN.fullmatch(key):
        raise TrialSetupError("Local Databento key is missing or invalid; its value was not printed.")
    return key


def build_requests(
    symbol: str, start_text: str, *, underlying_schema: str = "bbo-1s", now: datetime | None = None,
) -> list[dict[str, Any]]:
    if symbol not in {"ES", "NQ"}:
        raise TrialSetupError("Select ES or NQ.")
    if underlying_schema not in {"bbo-1s", "mbp-1"}:
        raise TrialSetupError("Select bbo-1s or mbp-1 for the underlying quotes.")
    try:
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
    except ValueError:
        raise TrialSetupError("Use an ISO timestamp with timezone, such as 2026-10-16T13:35:00Z.") from None
    if start.tzinfo is None:
        raise TrialSetupError("Start time must include a timezone (Z or an explicit offset).")
    start = start.astimezone(timezone.utc)
    end = start + timedelta(seconds=60)
    if end > (now or datetime.now(timezone.utc)) - timedelta(hours=24):
        raise TrialSetupError("Choose a completed historical interval at least 24 hours old.")
    if start.weekday() >= 5:
        raise TrialSetupError("Choose a weekday during an active CME session.")
    # Include the prior day's definitions; never use definitions published after
    # the replay starts. One parent deliberately means a bounded quarterly subset.
    definition_start = start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    common = {"dataset": DATASET, "limit": RECORD_LIMIT}
    iso = lambda value: value.isoformat().replace("+00:00", "Z")
    return [
        {**common, "schema": "definition", "stype_in": "parent",
         "symbols": [f"{symbol}.OPT", f"{symbol}.FUT"],
         "start": iso(definition_start), "end": iso(start)},
        {**common, "schema": underlying_schema, "stype_in": "continuous",
         "symbols": [f"{symbol}.v.0"],
         "start": iso(start - timedelta(seconds=2)), "end": iso(end)},
        {**common, "schema": "trades", "stype_in": "parent",
         "symbols": [f"{symbol}.OPT"], "start": iso(start), "end": iso(end)},
    ]


def quote_requests(client: Any, requests: list[dict[str, Any]]) -> list[float]:
    costs = []
    for request in requests:
        try:
            cost = float(client.metadata.get_cost(**request))
        except Exception as exc:
            raise TrialRequestError("quote", request["schema"], exc) from None
        if not math.isfinite(cost) or cost < 0:
            raise TrialSetupError(f"Provider returned an invalid {request['schema']} cost estimate; no data requested.")
        costs.append(cost)
    return costs


def download_requests(
    client: Any,
    requests: list[dict[str, Any]],
    *,
    symbol: str,
    max_cost: float,
    credits_remaining: float,
    acknowledge: bool,
    output_dir: Path,
) -> dict[str, Any]:
    if not acknowledge:
        raise TrialSetupError("Download requires --use-credits after reviewing the quote and Billing balance.")
    if not math.isfinite(max_cost) or not 0 < max_cost <= 5:
        raise TrialSetupError("The trial estimate ceiling must be greater than $0 and at most $5.")
    if not math.isfinite(credits_remaining) or credits_remaining <= 0:
        raise TrialSetupError("Supply the positive remaining credit balance shown in Billing.")
    if output_dir.exists():
        raise TrialSetupError(existing_output_message(output_dir, symbol))
    costs = quote_requests(client, requests)
    total = sum(costs)
    if total > min(max_cost, credits_remaining):
        raise TrialSetupError(f"Estimated ${total:.6f} exceeds the permitted estimate or credit balance; no download made.")
    output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.mkdir(mode=0o700)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "status": "started",
        "symbol": symbol,
        "replay_start": requests[2]["start"],
        "replay_end": requests[2]["end"],
        "dataset": DATASET,
        "source_kind": "historical_provider_download",
        "underlying_schema": requests[1]["schema"],
        "underlying_sampling": (
            "one-second BBO snapshots" if requests[1]["schema"] == "bbo-1s"
            else "every top-of-book update"
        ),
        "estimated_total_usd": total,
        "operator_reported_credits_remaining_usd": credits_remaining,
        "estimated_cost_ceiling_usd": max_cost,
        "coverage": "quarterly parent subset; trade-volume proxy; no OI; not full options chain",
        "live_certified": False,
        "record_counts": {},
        "requests": [dict(request, estimated_cost_usd=cost) for request, cost in zip(requests, costs)],
    }
    private_write(output_dir / "request-plan.json", json.dumps(manifest, indent=2) + "\n")
    for request, name in zip(requests, ("definitions.dbn", "underlying.dbn", "trades.dbn")):
        path = output_dir / name
        stage = "download"
        try:
            private_write(path, "")
            # SDK requires a nonexistent target. The owner-only directory and
            # umask preserve private permissions while it streams to disk.
            path.unlink()
            old_mask = os.umask(0o077)
            try:
                records = client.timeseries.get_range(**request, path=path)
            finally:
                os.umask(old_mask)
            stage = "validation"
            os.chmod(path, 0o600)
            count = 0
            for _ in records:
                count += 1
                if count >= request["limit"]:
                    break
        except Exception as exc:
            error = TrialRequestError(stage, request["schema"], exc)
            manifest.update(status="stopped_request_error", stopped_stage=error.stage,
                            stopped_schema=error.schema)
            if error.http_status is not None:
                manifest["http_status"] = error.http_status
            if error.provider_case is not None:
                manifest["provider_case"] = error.provider_case
            save_stopped_manifest(output_dir, manifest)
            raise error from None
        manifest["record_counts"][request["schema"]] = count
        if count == 0 or count >= request["limit"]:
            manifest.update(status="stopped_empty_or_record_limit", stopped_stage="validation",
                            stopped_schema=request["schema"])
            save_stopped_manifest(output_dir, manifest)
            raise TrialSetupError(
                f"Historical {request['schema']} returned {count} records (limit {request['limit']}); "
                "download stopped. Retained partial files may have used credits; no automatic retry."
            )
    manifest["status"] = "download_complete"
    private_write(output_dir / "download-complete.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("set-key", "check", "quote", "download"))
    result.add_argument("--symbol", choices=("ES", "NQ"), default="ES")
    result.add_argument("--start", help="Historical timezone-bearing start; fixed 60-second option window")
    result.add_argument("--underlying-schema", choices=("bbo-1s", "mbp-1"), default="bbo-1s",
                        help="Underlying quote sampling (default bbo-1s; mbp-1 retains every update)")
    result.add_argument("--max-cost", type=float, default=1.0, help="Maximum quoted USD, up to $5 (default $1)")
    result.add_argument("--credits-remaining", type=float, help="Remaining free credits you verified in Billing")
    result.add_argument("--use-credits", action="store_true", help="Explicitly request the quoted historical data")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "set-key":
            save_key()
            return 0
        key = read_key()
        if args.action == "check":
            import databento  # noqa: F401
            print("Local key format, permissions and Databento SDK: ready. No authentication or data requested.")
            return 0
        if not args.start:
            raise TrialSetupError("Supply --start with a completed historical interval.")
        requests = build_requests(args.symbol, args.start, underlying_schema=args.underlying_schema)
        if args.action == "download" and (not args.use_credits or args.credits_remaining is None):
            raise TrialSetupError("Review quote and Billing first, then use --use-credits --credits-remaining AMOUNT.")
        import databento as db

        client = db.Historical(key=key)
        if args.action == "quote":
            costs = quote_requests(client, requests)
            for request, cost in zip(requests, costs):
                print(f"{request['schema']}: ${cost:.6f}")
            print(f"Estimated total: ${sum(costs):.6f}. No market data downloaded.")
            print("Scope: quarterly option-parent subset, trade-volume proxy, no OI; 60 seconds.")
            print(f"Underlying quote schema: {args.underlying_schema}.")
        else:
            timestamp = requests[2]["start"].replace(":", "").replace("-", "")
            sampling_suffix = "-bbo-1s" if args.underlying_schema == "bbo-1s" else ""
            output = DATA_ROOT / f"{args.symbol.lower()}-{timestamp}{sampling_suffix}"
            manifest = download_requests(
                client, requests, symbol=args.symbol,
                max_cost=args.max_cost, credits_remaining=args.credits_remaining,
                acknowledge=args.use_credits, output_dir=output,
            )
            print(f"Historical download complete: {output}")
            print(f"Quoted credit use: ${manifest['estimated_total_usd']:.6f}. Actual billing is provider-controlled.")
        return 0
    except TrialSetupError as exc:
        print(f"Setup stopped: {exc}")
        return 2
    except FileExistsError:
        print("Setup stopped: a target already exists; existing keys and data were preserved.")
        return 2
    except Exception as exc:
        # SDK exception strings can contain URLs, account details or payloads.
        print(f"Setup stopped ({type(exc).__name__}); check the provider portal. Details were withheld to protect credentials.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

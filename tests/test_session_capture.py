import asyncio
import json
import os
import re
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.cli import _shutdown_runtime_tasks
from gex_terminal.cli import compute_snapshot, export_demo_screenshot
from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.session_capture import (
    CAPTURE_SCHEMA,
    CapturedSessionWriter,
    RecordingConsumerProxy,
    inspect_captured_session,
    iter_captured_events,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _AdvancingClock:
    def __init__(self):
        self.current = datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current += timedelta(milliseconds=250)
        return value


class _AdvancingMonotonic:
    def __init__(self):
        self.current = 1_000_000_000

    def __call__(self):
        value = self.current
        self.current += 250_000_000
        return value


class _RecordingConsumer:
    def __init__(self):
        self.payloads = []

    async def update_market_state(self, payload):
        self.payloads.append(payload)


def _messages():
    return [
        {
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "capture-test",
            "symbol": "ES",
            "price": 5_000.0,
            "event_time": "2026-08-04T20:00:00Z",
        },
        {
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "capture-test",
            "contract_id": "ESU6-C-5000",
            "symbol": "ES",
            "contract_symbol": "ESU6 C5000",
            "strike": 5_000.0,
            "option_type": "C",
            "volume": 125,
            "iv": 0.18,
            "iv_source": "provider",
            "expiry": "2026-09-18",
            "expiry_timestamp": "2026-09-18T20:00:00Z",
            "instrument_class": "futures_option",
            "volume_semantics": "cumulative",
            "position_source": "trade_volume",
            "event_time": "2026-08-04T20:00:01Z",
            "sequence": 17,
        },
    ]


class CapturedSessionTests(unittest.IsolatedAsyncioTestCase):
    def _writer(self, path):
        return CapturedSessionWriter(
            path,
            source="unit-test-provider",
            model_inputs={
                "symbol": "ES",
                "risk_free_rate": 0.045,
                "contract_multiplier": 50,
            },
            label="deterministic round trip",
            clock=_AdvancingClock(),
            monotonic_ns=_AdvancingMonotonic(),
        )

    async def test_round_trip_preserves_payload_order_and_verifies_hash_footer(self):
        messages = _messages()
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "session.jsonl"
            writer = self._writer(target)

            await writer.start()
            for message in messages:
                await writer.append(message)
            finalized = await writer.finalize(
                final_snapshot_record_id="snapshot-001",
                feed_quality={"status": "healthy"},
            )

            self.assertEqual(finalized, target)
            self.assertTrue(target.exists())
            self.assertEqual(list(Path(temp_dir).glob("*.partial")), [])

            records = [
                json.loads(line)
                for line in target.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(records[0]["record_type"], "header")
            self.assertEqual(records[0]["schema"], CAPTURE_SCHEMA)
            self.assertEqual(
                [record["record_type"] for record in records],
                ["header", "event", "event", "footer"],
            )

            events = list(iter_captured_events(target, verify=True))
            self.assertEqual([event["sequence"] for event in events], [0, 1])
            self.assertEqual([event["message"] for event in events], messages)
            self.assertEqual(
                [event["event_time"] for event in events],
                [message["event_time"] for message in messages],
            )
            for event in events:
                self.assertRegex(event["message_sha256"], _SHA256)
                self.assertRegex(event["record_sha256"], _SHA256)

            footer = records[-1]
            self.assertTrue(footer["completed"])
            self.assertEqual(footer["status"], "complete")
            self.assertEqual(footer["event_count"], len(messages))
            self.assertRegex(footer["message_sha256"], _SHA256)
            self.assertRegex(footer["records_sha256"], _SHA256)
            self.assertRegex(footer["content_sha256"], _SHA256)
            self.assertNotEqual(footer["content_sha256"], footer["records_sha256"])

            inspected = inspect_captured_session(target)
            self.assertEqual(inspected["event_count"], len(messages))
            self.assertTrue(inspected["completed"])
            self.assertTrue(inspected["integrity_verified"])
            self.assertEqual(inspected["header"], records[0])
            self.assertEqual(inspected["footer"], footer)

    async def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "session.jsonl"
            writer = self._writer(target)
            await writer.start()
            await writer.append(_messages()[0])
            await writer.finalize()

            records = [
                json.loads(line)
                for line in target.read_text(encoding="utf-8").splitlines()
            ]
            records[1]["message"]["price"] = 9_999.0
            target.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "(?i)(hash|integrity)"):
                list(iter_captured_events(target, verify=True))

    async def test_footer_aggregate_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "session.jsonl"
            writer = self._writer(target)
            await writer.start()
            await writer.append(_messages()[0])
            await writer.finalize()

            records = [
                json.loads(line)
                for line in target.read_text(encoding="utf-8").splitlines()
            ]
            records[-1]["records_sha256"] = "0" * 64
            records[-1]["content_sha256"] = "0" * 64
            target.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "(?i)(aggregate|hash|integrity)"):
                list(iter_captured_events(target, verify=True))

    async def test_header_metadata_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "session.jsonl"
            writer = self._writer(target)
            await writer.start()
            await writer.append(_messages()[0])
            await writer.finalize()

            records = [
                json.loads(line)
                for line in target.read_text(encoding="utf-8").splitlines()
            ]
            records[0]["label"] = "tampered label"
            target.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "(?i)(content|hash|integrity)"):
                list(iter_captured_events(target, verify=True))

    async def test_footer_metadata_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "session.jsonl"
            writer = self._writer(target)
            await writer.start()
            await writer.append(_messages()[0])
            await writer.finalize(feed_quality={"status": "healthy"})

            records = [
                json.loads(line)
                for line in target.read_text(encoding="utf-8").splitlines()
            ]
            records[-1]["feed_quality"]["status"] = "tampered"
            target.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "(?i)(content|hash|integrity)"):
                list(iter_captured_events(target, verify=True))

    async def test_missing_footer_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "session.jsonl"
            writer = self._writer(target)
            await writer.start()
            await writer.append(_messages()[0])
            await writer.finalize()

            lines = target.read_text(encoding="utf-8").splitlines()
            target.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "(?i)(footer|incomplete)"):
                list(iter_captured_events(target, verify=True))

    async def test_recording_proxy_forwards_original_payload_and_captures_it(self):
        message = _messages()[0]
        payload = json.dumps(message)
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "proxied.jsonl"
            writer = self._writer(target)
            consumer = _RecordingConsumer()
            proxy = RecordingConsumerProxy(consumer, writer)

            await writer.start()
            await proxy.update_market_state(payload)
            await writer.finalize()

            events = list(iter_captured_events(target))

        self.assertEqual(consumer.payloads, [payload])
        self.assertEqual([event["message"] for event in events], [message])

    async def test_failed_stream_task_aborts_and_flushes_partial_capture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "failed.gex-session.jsonl"
            writer = self._writer(target)
            await writer.start()
            await writer.append(_messages()[0])

            async def fail_stream():
                raise RuntimeError("synthetic stream failure")

            task = asyncio.create_task(fail_stream())
            await asyncio.sleep(0)
            consumer = StatefulGexConsumer(IntradayGexEngine())

            errors = await _shutdown_runtime_tasks(
                task,
                None,
                writer,
                consumer,
                run_failed=False,
            )

            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], RuntimeError)
            self.assertFalse(target.exists())
            self.assertTrue(writer.partial_path.exists())
            self.assertIn(
                '"record_type":"abort"',
                writer.partial_path.read_text(encoding="utf-8"),
            )

    async def test_capture_files_remain_owner_only_before_and_after_finalize(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "private.gex-session.jsonl"
            writer = self._writer(target)
            await writer.start()
            self.assertEqual(stat.S_IMODE(writer.partial_path.stat().st_mode), 0o600)
            await writer.append(_messages()[0])
            await writer.finalize()

            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    async def test_verified_iterator_replays_buffered_bytes_after_path_swap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "original.gex-session.jsonl"
            replacement = Path(temp_dir) / "replacement.gex-session.jsonl"
            original_writer = self._writer(target)
            await original_writer.start()
            await original_writer.append(_messages()[0])
            await original_writer.finalize()
            replacement_message = {**_messages()[0], "price": 5_100.0}
            replacement_writer = self._writer(replacement)
            await replacement_writer.start()
            await replacement_writer.append(replacement_message)
            await replacement_writer.finalize()
            from gex_terminal import session_capture as capture_module

            real_verify = capture_module._verify_capture

            def verify_then_swap(path):
                verified = real_verify(path)
                os.replace(replacement, target)
                return verified

            with patch.object(capture_module, "_verify_capture", verify_then_swap):
                events = list(iter_captured_events(target))

            self.assertEqual(events[0]["message"]["price"], 5_000.0)

    async def test_noninteractive_capture_snapshot_disables_event_time_sleep(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "long-gap.gex-session.jsonl"
            writer = self._writer(target)
            await writer.start()
            messages = _messages()
            messages[1]["event_time"] = "2026-08-05T20:00:00Z"
            await writer.append(messages[0])
            await writer.append(messages[1])
            await writer.finalize()
            sleep = AsyncMock()
            built_clocks = []

            def replay_factory(*args, **kwargs):
                built_clocks.append(kwargs.get("replay_clock"))
                return ReplayAdapter(*args, **kwargs, sleep=sleep)

            config = GexConfig(
                symbol="ES",
                symbols=("ES", "NQ", "SPX", "QQQ"),
                data_mode="replay",
                data_provider="replay",
                contract_multiplier=50,
                risk_free_rate=0.045,
                days_to_expiry=0.25,
                refresh_interval_seconds=1.0,
                stale_after_seconds=10.0,
                replay_path=str(target),
                replay_delay_seconds=0.05,
                tradovate_environment="demo",
                replay_clock="auto",
            )

            with patch("gex_terminal.adapters.registry.ReplayAdapter", replay_factory):
                snapshot, _, _ = await compute_snapshot(config)
                await export_demo_screenshot(
                    config,
                    str(Path(temp_dir) / "capture.svg"),
                    width=100,
                    height=32,
                )

            self.assertEqual(snapshot["symbol"], "ES")
            self.assertEqual(built_clocks, ["none", "none"])
            sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

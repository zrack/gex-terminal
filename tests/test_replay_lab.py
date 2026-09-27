import csv
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.replay_catalog import replay_session_names
from gex_terminal.replay_lab import (
    build_replay_lab_report,
    replay_lab_to_csv,
    replay_lab_to_markdown,
    write_replay_lab_report,
)


def _config():
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ", "SPX", "QQQ"),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="sample_data/demo_replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


class ReplayLabTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_session_identity_replaces_ambient_config(self):
        report = await build_replay_lab_report(
            replace(_config(), symbol="NQ", contract_multiplier=20),
            session_names=("trend-day",),
        )

        self.assertEqual(report["symbol"], "ES")
        self.assertEqual(report["inputs"]["contract_multiplier"], 50)
        self.assertEqual(report["sessions"][0]["snapshot"]["symbol"], "ES")
        self.assertEqual(
            report["sessions"][0]["snapshot"]["contract_multiplier"],
            50,
        )

    async def test_builds_replay_lab_report_with_alerts_and_comparisons(self):
        report = await build_replay_lab_report(
            _config(),
            session_names=("trend-day", "zero-gamma-flip"),
        )

        self.assertEqual(report["schema"], "gex-terminal.replay-lab.v1")
        self.assertEqual(len(report["sessions"]), 2)
        self.assertEqual(len(report["comparisons"]), 1)
        self.assertGreater(report["sessions"][0]["summary"]["snapshot_count"], 0)
        self.assertGreater(report["sessions"][1]["summary"]["alert_count"], 0)
        self.assertIn("snapshot", report["sessions"][0])

    async def test_mixed_instruments_are_grouped_and_never_compared(self):
        report = await build_replay_lab_report(
            _config(),
            session_names=("trend-day", "nq-research-loop", "zero-gamma-flip"),
        )

        self.assertIsNone(report["symbol"])
        self.assertIsNone(report["inputs"]["contract_multiplier"])
        self.assertEqual(report["leaderboard"], {})
        self.assertEqual(
            {(row["symbol"], row["contract_multiplier"]) for row in report["instruments"]},
            {("ES", 50), ("NQ", 20)},
        )
        self.assertEqual(len(report["comparisons"]), 1)
        self.assertEqual(report["comparisons"][0]["symbol"], "ES")
        self.assertEqual(report["comparisons"][0]["contract_multiplier"], 50)
        self.assertNotIn("nq-research-loop", {
            report["comparisons"][0]["from_session"],
            report["comparisons"][0]["to_session"],
        })

        markdown = replay_lab_to_markdown(report)
        csv_rows = list(csv.DictReader(io.StringIO(replay_lab_to_csv(report))))
        self.assertIn("Multiple instrument identities", markdown)
        session_rows = [row for row in csv_rows if row["record_type"] == "session"]
        self.assertEqual(
            {(row["symbol"], row["contract_multiplier"]) for row in session_rows},
            {("ES", "50"), ("NQ", "20")},
        )

    async def test_formats_replay_lab_markdown_csv_and_json(self):
        report = await build_replay_lab_report(_config(), session_names=("trend-day",))

        markdown = replay_lab_to_markdown(report)
        csv_rows = list(csv.DictReader(io.StringIO(replay_lab_to_csv(report))))

        self.assertIn("# Replay Research Lab", markdown)
        self.assertIn("Trend Day", markdown)
        self.assertIn("session", {row["record_type"] for row in csv_rows})

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            md_path = write_replay_lab_report(report, str(base / "lab.md"))
            csv_path = write_replay_lab_report(report, str(base / "lab.csv"))
            json_path = write_replay_lab_report(report, str(base / "lab.json"))

            self.assertIn("Replay Research Lab", md_path.read_text())
            self.assertIn("record_type", csv_path.read_text())
            self.assertEqual(json.loads(json_path.read_text())["schema"], report["schema"])


class BundledReplayExpectationTests(unittest.IsolatedAsyncioTestCase):
    """Semantic checkpoints, read from fixture events rather than saved outputs.

    These expectations pin the legacy ES fallback to 0.01 days and the catalog
    multiplier. They deliberately avoid exact floating-point GEX snapshots:
    nearby strikes, call/put quantities, spot paths and event times provide the
    oracles. Sequential call/put arrivals can produce temporary sign flips;
    a scenario's name alone does not predict either sign or compatibility level.
    """

    async def _session(self, name):
        report = await build_replay_lab_report(_config(), session_names=(name,))
        return report["sessions"][0]

    def _point(self, session, timestamp):
        matches = [p for p in session["timeline"] if p["timestamp"] == timestamp]
        self.assertEqual(len(matches), 1, (session["name"], timestamp))
        return matches[0]

    def _alerts_at(self, session, timestamp, expected_types, *, spot, wall):
        alerts = [a for a in session["alerts"] if a["timestamp"] == timestamp]
        self.assertCountEqual([a["type"] for a in alerts], expected_types)
        for alert in alerts:
            self.assertEqual(alert["session"], session["name"])
            self.assertEqual(alert["spot"], spot)
            self.assertEqual(alert["gamma_wall"], wall)

    async def test_every_bundled_session_starts_at_first_accepted_option(self):
        # Before the first option there is no chain to analyze. Quality Stress
        # also supplies an NQ tick before its first ES option; it cannot start ES.
        # Demo has no event time and must honestly retain processing-time status.
        starts = {
            "demo": (2, "", 5943.25, 5875),
            "full-session": (2, "2026-06-12T13:30:05Z", 5928.25, 5875),
            "trend-day": (2, "2026-07-16T13:30:04Z", 5928.25, 5900),
            "chop-day": (2, "2026-07-16T13:30:04Z", 5942, 5900),
            "volatility-spike": (2, "2026-07-16T13:30:04Z", 5966, 5975),
            "gap-fade": (2, "2026-07-16T13:30:04Z", 6008.25, 5975),
            "call-wall-breakout": (2, "2026-07-16T13:30:04Z", 5932.25, 5925),
            "zero-gamma-flip": (2, "2026-07-16T13:30:04Z", 5922.25, 5900),
            "expiration-compression": (2, "2026-07-16T18:30:04Z", 5946.75, 5925),
            "quality-stress": (3, "2026-07-16T13:30:04Z", 5943.25, 5900),
            "nq-research-loop": (2, "2026-09-04T13:30:10Z", 21020, 20800),
        }
        self.assertEqual(set(starts), set(replay_session_names()))
        report = await build_replay_lab_report(_config())
        for session in report["sessions"]:
            with self.subTest(session=session["name"]):
                index, timestamp, spot, wall = starts[session["name"]]
                first = session["timeline"][0]
                self.assertEqual(first["message_index"], index)
                self.assertEqual(first["input_event_time"], timestamp)
                self.assertEqual(first["time_basis"], (
                    "accepted_market_time" if timestamp else "processing_time"
                ))
                if timestamp:
                    self.assertEqual(first["timestamp"], timestamp)
                starts_emitted = [a for a in session["alerts"]
                                  if a["type"] == "session_started"]
                self.assertEqual(len(starts_emitted), 1)
                self.assertEqual(starts_emitted[0]["timestamp"], first["timestamp"])
                self.assertEqual(starts_emitted[0]["severity"], "info")
                self._alerts_at(session, first["timestamp"], ["session_started"],
                                spot=spot, wall=wall)

    async def test_trend_accumulation_moves_wall_without_compatibility_cross(self):
        session = await self._session("trend-day")
        # Rising spot reprices the existing 5975 calls at 19:00. The 6000
        # calls then arrive five seconds later. The distant 6025 addition
        # cannot displace the near-spot 6000 wall at this very short DTE.
        shifts = [a for a in session["alerts"] if a["type"] == "gamma_wall_shift"]
        self.assertEqual([(a["timestamp"], a["gamma_wall"]) for a in shifts], [
            ("2026-07-16T13:31:00Z", 5925),
            ("2026-07-16T15:00:05Z", 5950),
            ("2026-07-16T19:00:00Z", 5975),
            ("2026-07-16T19:00:05Z", 6000),
        ])
        self._alerts_at(session, "2026-07-16T19:00:05Z", ["gamma_wall_shift"],
                        spot=5988.75, wall=6000)
        self._alerts_at(session, "2026-07-16T19:15:05Z", [], spot=5988.75, wall=6000)
        self.assertNotIn("zero_gamma_cross", [a["type"] for a in session["alerts"]])
        summary = session["summary"]
        self.assertEqual(summary["session_change"], 60.5)
        self.assertEqual(summary["call_wall"], 6000)
        self.assertEqual(summary["regime"], "positive_gex_proxy")
        self.assertGreater(summary["total_net_gex"], 0)

    async def test_breakout_cross_and_later_wall_follow_distinct_events(self):
        session = await self._session("call-wall-breakout")
        # The 16:00 spot jump moves from below the mixed-sign strike-profile
        # level to above it. The next 5975 call is a separate wall/exposure
        # event; a delayed or repeated cross at that option tick is incorrect.
        self._alerts_at(session, "2026-07-16T16:00:00Z", [
            "gamma_wall_shift", "zero_gamma_cross", "regime_flip", "imbalance_threshold",
        ], spot=5982.5, wall=5950)
        self._alerts_at(session, "2026-07-16T16:00:04Z", [
            "gamma_wall_shift", "major_exposure_change",
        ], spot=5982.5, wall=5975)
        before = self._point(session, "2026-07-16T14:00:05Z")
        after = self._point(session, "2026-07-16T16:00:00Z")
        self.assertLess(before["spot"], before["zero_gamma"])
        self.assertGreater(after["spot"], after["zero_gamma"])
        self.assertEqual(after["regime"], "positive_gex_proxy")
        self._alerts_at(session, "2026-07-16T19:00:04Z", [
            "gamma_wall_shift", "major_exposure_change",
        ], spot=6032.75, wall=6025)
        self.assertEqual(session["summary"]["call_wall"], 6025)
        self.assertEqual(session["summary"]["regime"], "wall_proximity")

    async def test_put_heavy_rotations_flip_sign_on_put_arrival(self):
        cases = (
            # 5975 puts increase by 1920 after only 440 added calls.
            ("gap-fade", "15:00:04", "15:00:05", 5984.5, 5975, 5950),
            # 2840 puts versus 760 calls at the same 5950 strike and IV.
            ("volatility-spike", "15:10:04", "15:10:05", 5944.25, 5950, 5900),
        )
        for name, before_time, put_time, spot, wall, final_wall in cases:
            with self.subTest(session=name):
                session = await self._session(name)
                before = self._point(session, f"2026-07-16T{before_time}Z")
                after = self._point(session, f"2026-07-16T{put_time}Z")
                self.assertGreater(before["total_net_gex"], 0)
                self.assertLess(after["total_net_gex"], 0)
                self._alerts_at(session, after["timestamp"], [
                    "regime_flip", "major_exposure_change", "imbalance_threshold",
                ], spot=spot, wall=wall)
                # Proximity is a spatial classification, not the net-GEX sign.
                self.assertEqual(before["regime"], "wall_proximity")
                self.assertEqual(after["regime"], "wall_proximity")
                self.assertLess(session["summary"]["total_net_gex"], -1_000_000_000)
                self.assertEqual(session["summary"]["put_wall"], final_wall)
                self.assertLess(session["summary"]["session_change"], 0)
                if name == "volatility-spike":
                    self.assertNotIn("zero_gamma_cross", [
                        a["type"] for a in session["alerts"]
                    ])

    async def test_named_flip_changes_gex_sign_without_crossing_compatibility_level(self):
        session = await self._session("zero-gamma-flip")
        # At 16:00, spot has moved away from the put-heavy 5925 position but
        # net GEX remains negative. The 2880 near-spot 5950 calls cause the
        # positive flip, and 620 matching puts cannot undo it. Spot stays above
        # the historical compatibility level throughout this fixture.
        before = self._point(session, "2026-07-16T16:00:00Z")
        after = self._point(session, "2026-07-16T16:00:04Z")
        paired = self._point(session, "2026-07-16T16:00:05Z")
        self.assertLess(before["total_net_gex"], 0)
        self.assertEqual(before["regime"], "negative_gex_proxy")
        self.assertGreater(after["total_net_gex"], 0)
        self.assertGreater(paired["total_net_gex"], 0)
        self._alerts_at(session, after["timestamp"], [
            "gamma_wall_shift", "regime_flip", "major_exposure_change", "imbalance_threshold",
        ], spot=5948.75, wall=5950)
        self._alerts_at(session, paired["timestamp"], [], spot=5948.75, wall=5950)
        self.assertEqual(after["regime"], "wall_proximity")
        self.assertTrue(all(p["spot"] > p["zero_gamma"] for p in session["timeline"]))
        self.assertNotIn("zero_gamma_cross", [a["type"] for a in session["alerts"]])

    async def test_chop_retains_balanced_wall_after_both_sides_arrive(self):
        session = await self._session("chop-day")
        # The 5950 pair has 2180 calls / 2060 puts: slightly positive, near
        # balance. Farther 5975/6000 puts must not reverse that near-spot pair.
        paired = self._point(session, "2026-07-16T15:00:05Z")
        self.assertGreater(paired["imbalance"], 1.0)
        self.assertLess(paired["imbalance"], 1.1)
        for point in session["timeline"]:
            if point["timestamp"] >= paired["timestamp"]:
                self.assertEqual(point["gamma_wall"], 5950)
                self.assertGreater(point["total_net_gex"], 0)
        self.assertFalse(any(
            a["type"] in {"gamma_wall_shift", "regime_flip"}
            and a["timestamp"] >= paired["timestamp"]
            for a in session["alerts"]
        ))
        self.assertEqual(session["summary"]["spot"], 5947.5)
        self.assertEqual(session["summary"]["regime"], "wall_proximity")

    async def test_expiration_pinning_preserves_wall_through_spot_crossings(self):
        session = await self._session("expiration-compression")
        # The heavy 5950 pair remains dominant as spot crosses that strike in
        # both directions. A wall crossing is not a compatibility-level cross.
        for timestamp, spot in (
            ("2026-07-16T18:45:05Z", 5946.75),
            ("2026-07-16T19:20:00Z", 5951.25),
            ("2026-07-16T19:55:00Z", 5949.5),
        ):
            point = self._point(session, timestamp)
            self.assertEqual(point["spot"], spot)
            self.assertEqual(point["gamma_wall"], 5950)
            self.assertEqual(point["regime"], "wall_proximity")
        for timestamp in ("2026-07-16T19:55:04Z", "2026-07-16T19:55:05Z"):
            self._alerts_at(session, timestamp, [
                "major_exposure_change", "imbalance_threshold",
            ], spot=5949.5, wall=5950)
        self.assertEqual([
            (a["timestamp"], a["gamma_wall"])
            for a in session["alerts"] if a["type"] == "gamma_wall_shift"
        ], [("2026-07-16T18:45:04Z", 5950)])
        self.assertNotIn("zero_gamma_cross", [a["type"] for a in session["alerts"]])
        self.assertGreater(session["summary"]["concentration_ratio"], 0.99)

    async def test_quality_annotations_do_not_accept_off_symbol_spot_or_repeat(self):
        session = await self._session("quality-stress")
        quality = [a for a in session["alerts"] if a["type"] == "data_quality"]
        # Both 5950 sides carry partial_chain; report its first occurrence only.
        self.assertEqual([(a["timestamp"], a["spot"]) for a in quality], [
            ("2026-07-16T13:30:01Z", 18442.5),
            ("2026-07-16T13:31:04Z", None),
            ("2026-07-16T13:32:00Z", 5941.75),
        ])
        self.assertTrue(all(a["gamma_wall"] is None for a in quality))
        self.assertTrue(all(a["severity"] == "low" for a in quality))
        self.assertEqual([p["message_index"] for p in session["timeline"]], [3, 4, 5, 6, 7])
        self.assertEqual({p["spot"] for p in session["timeline"]}, {5943.25, 5941.75})
        self.assertEqual(session["snapshot"]["raw_input_audit"]["accepted_count"], 6)
        self.assertEqual(session["summary"]["session_change"], -1.5)

    async def test_nq_event_time_and_late_call_wall_survive_schema_v2_replay(self):
        session = await self._session("nq-research-loop")
        # NQ event_time precedes received_time by 20 ms. At 15:00 the near-spot
        # 21100 calls remain dominant while spot rises from 21072 to 21110;
        # that changes imbalance, not the wall or net-GEX sign.
        self._alerts_at(session, "2026-09-04T15:00:00Z", ["imbalance_threshold"],
                        spot=21110, wall=21100)
        self.assertEqual(session["summary"]["symbol"], "NQ")
        self.assertEqual(session["summary"]["contract_multiplier"], 20)
        self.assertEqual(session["summary"]["last_timestamp"], "2026-09-04T15:30:00Z")
        self.assertEqual(session["summary"]["session_change"], 115)
        self.assertEqual(session["summary"]["call_wall"], 21100)
        self.assertEqual(session["summary"]["put_wall"], 21000)
        self.assertEqual(session["summary"]["regime"], "wall_proximity")
        self.assertTrue(all(p["timestamp"] == p["input_event_time"]
                            for p in session["timeline"]))
        self.assertFalse(any(a["timestamp"] > "2026-09-04T15:00:00Z"
                             for a in session["alerts"]))


if __name__ == "__main__":
    unittest.main()

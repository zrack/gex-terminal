"""Observation ages disclose uncertainty without changing IV or pricing coverage."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from gex_terminal.iv_freshness import iv_freshness
from gex_terminal.pricing_assumptions import pricing_coverage
from gex_terminal import wind_tunnel as wind
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint
from tests.test_pricing_coverage import consumer_with, unavailable
from tests.test_wind_tunnel_checkpoint import AS_OF, option


CUTOFF = datetime(2026, 9, 4, 13, 35, tzinfo=timezone.utc)


def row(age=0, quantity=7, **changes):
    result = {"iv": .2, "iv_source": "provider", "accumulated_volume": quantity,
              "event_time": (CUTOFF - timedelta(seconds=age)).isoformat()}
    result.update(changes)
    return result


class IvFreshnessTests(unittest.TestCase):
    def test_recent_boundary_and_old_valid_iv_do_not_change_pricing(self):
        rows = [row(0, 2), row(300, 3), row(300.000001, 5), row(6 * 3600, 11)]
        frozen = copy.deepcopy(rows)
        before = pricing_coverage(rows)
        result = iv_freshness(rows, CUTOFF)
        self.assertEqual(result["time_basis"], "captured_cutoff")
        self.assertEqual(result["recent_contract_count"], 2)
        self.assertEqual(result["recent_quantity"], 5)
        self.assertEqual(result["older_contract_count"], 2)
        self.assertEqual(result["older_quantity"], 16)
        self.assertEqual(result["known_age_quantity"], 21)
        self.assertEqual(result["max_age_seconds"], 21600)
        self.assertAlmostEqual(result["median_age_seconds"], 300.0000005)
        self.assertEqual(result["reference_window_seconds"], 300)
        self.assertIn("not an IV validity or expiry rule", result["reference_window_note"])
        self.assertEqual(pricing_coverage(rows), before)
        self.assertEqual(rows, frozen)

    def test_retained_iv_uses_original_accepted_observation_not_failed_tick(self):
        retained = row(10, iv_source="prior_valid", iv_provenance={
            "prior_iv_event_time": (CUTOFF - timedelta(seconds=3600)).isoformat(),
            "prior_iv_source": "black_76_inverted", "prior_iv_age_ms": 1000,
        })
        result = iv_freshness([retained], CUTOFF)
        self.assertEqual(result["max_age_seconds"], 3600)
        self.assertEqual(result["max_retained_age_seconds"], 3600)
        self.assertEqual(result["older_quantity"], 7)
        self.assertEqual(result["recent_quantity"], 0)
        self.assertEqual(result["retained_iv_contract_count"], 1)

    def test_missing_retained_clock_or_unqualified_prior_source_is_unknown(self):
        for provenance in ({}, {"prior_iv_event_time": AS_OF},
                           {"prior_iv_event_time": AS_OF, "prior_iv_source": "configured_default"}):
            with self.subTest(provenance=provenance):
                result = iv_freshness([row(iv_source="prior_valid", iv_provenance=provenance)], CUTOFF)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["unknown_quantity"], 7)
                self.assertIsNone(result["max_retained_age_seconds"])
                self.assertIsNone(result["max_age_seconds"])

    def test_missing_naive_invalid_and_future_observation_times_are_never_zero_age(self):
        for clock in (None, "", "2026-09-04T13:35:00", "invalid", "2026-09-04T13:35:00.000001001Z"):
            with self.subTest(clock=clock):
                result = iv_freshness([row(event_time=clock)], CUTOFF)
                self.assertEqual(result["unknown_contract_count"], 1)
                self.assertEqual(result["recent_contract_count"], 0)
                self.assertIsNone(result["max_age_seconds"])
        self.assertEqual(iv_freshness([row(event_time="2026-09-04T13:35:00.000001001Z")],
                                     CUTOFF)["future_observation_contract_count"], 1)

    def test_sub_microsecond_capture_ambiguity_is_unknown_without_claiming_future_time(self):
        captured = "2026-10-16T20:59:59.450132Z"
        observed = "2026-10-16T20:59:59.450132845Z"
        for current in (captured, "2026-10-16T21:29:59.450132Z"):
            with self.subTest(model_as_of=current):
                result = iv_freshness([row(event_time=observed, quantity=1416)], current,
                                      capture_as_of=captured)
                self.assertEqual(result["unknown_contract_count"], 1)
                self.assertEqual(result["unknown_quantity"], 1416)
                self.assertEqual(result["capture_precision_ambiguity_contract_count"], 1)
                self.assertEqual(result["capture_precision_ambiguity_quantity"], 1416)
                self.assertEqual(result["future_observation_contract_count"], 0)
                self.assertEqual(result["recent_quantity"], 0)
                self.assertIsNone(result["max_age_seconds"])
                self.assertIn("truncated nanoseconds", result["age_semantics"])

    def test_explicit_sub_microsecond_cutoff_keeps_strict_future_qualification(self):
        result = iv_freshness([row(event_time="2026-09-04T13:35:00.000000002Z")],
                              "2026-09-04T13:35:00.000000001Z")
        self.assertEqual(result["unknown_contract_count"], 1)
        self.assertEqual(result["future_observation_contract_count"], 1)
        self.assertEqual(result["capture_precision_ambiguity_contract_count"], 0)

    def test_timezone_offsets_and_nanosecond_reference_boundary_are_respected(self):
        self.assertEqual(iv_freshness([row(event_time="2026-09-04T06:35:00-07:00")],
                                     AS_OF)["max_age_seconds"], 0)
        result = iv_freshness([row(event_time="2026-09-04T13:30:00Z")],
                              "2026-09-04T13:35:00.000000001Z")
        self.assertEqual(result["older_contract_count"], 1)
        self.assertGreater(result["max_age_seconds"], 300)

    def test_unobserved_defaults_and_unpriced_rows_have_separate_denominators(self):
        rows = [row(100, 2), row(400, 3), row(quantity=5, event_time=None),
                row(quantity=7, iv_source="configured_default"), row(quantity=11, iv_source="legacy_unspecified"),
                row(quantity=13, iv_source=None), row(quantity=17, iv=None, iv_source="unavailable")]
        result = iv_freshness(iter(rows), CUTOFF)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["selected_contract_count"], 7)
        self.assertEqual(result["selected_quantity"], 58)
        self.assertEqual(result["priced_quantity"], 41)
        self.assertEqual(result["not_applicable_contract_count"], 2)
        self.assertEqual(result["not_applicable_quantity"], 18)
        self.assertEqual(result["unknown_quantity"], 18)
        self.assertEqual(result["unpriced_quantity"], 17)
        self.assertEqual(result["known_age_quantity"] + result["unknown_quantity"]
                         + result["not_applicable_quantity"], result["priced_quantity"])
        self.assertEqual(result["recent_quantity"] + result["older_quantity"], result["known_age_quantity"])

    def test_zero_quantity_still_reports_contract_age_without_dividing(self):
        result = iv_freshness([row(700, quantity=0)], CUTOFF)
        self.assertEqual(result["selected_contract_count"], 1)
        self.assertEqual(result["selected_quantity"], 0)
        self.assertEqual(result["older_contract_count"], 1)
        self.assertEqual(result["older_quantity"], 0)
        self.assertEqual(result["max_age_seconds"], 700)

    def test_model_time_advance_increases_age_without_refreshing_capture_clock(self):
        rows = [row(120, quantity=3)]
        before = iv_freshness(rows, CUTOFF)
        after = iv_freshness(rows, CUTOFF + timedelta(minutes=30), capture_as_of=CUTOFF)
        self.assertEqual(before["recent_quantity"], 3)
        self.assertEqual(after["older_quantity"], 3)
        self.assertEqual(after["max_age_seconds"], 1920)
        self.assertEqual(after["time_basis"], "scenario_model_time")
        self.assertEqual(after["model_time_advance_seconds"], 1800)
        self.assertEqual(after["capture_as_of"], AS_OF)
        # A later model clock must never qualify post-capture observations.
        future = iv_freshness([row(-60)], CUTOFF + timedelta(minutes=30), capture_as_of=CUTOFF)
        self.assertEqual(future["future_observation_quantity"], 7)
        self.assertIsNone(future["max_age_seconds"])

    def test_missing_naive_or_inverted_reference_time_keeps_observed_age_unknown(self):
        for current, capture in ((None, None), ("2026-09-04T13:35:00", None),
                                 (CUTOFF, "invalid"), (CUTOFF, CUTOFF + timedelta(seconds=1))):
            with self.subTest(current=current, capture=capture):
                result = iv_freshness([row()], current, capture_as_of=capture)
                self.assertEqual(result["time_basis"], "unknown")
                self.assertEqual(result["unknown_quantity"], 7)
                self.assertIsNone(result["model_time_advance_seconds"])

    def test_empty_unpriced_and_default_only_statuses_have_no_manufactured_age(self):
        for rows, expected in (([], "empty"), ([row(iv_source="unavailable", iv=None)], "unavailable"),
                               ([row(iv_source="configured_default")], "not_applicable")):
            with self.subTest(status=expected):
                result = iv_freshness(rows, CUTOFF)
                self.assertEqual(result["status"], expected)
                self.assertIsNone(result["median_age_seconds"])
                self.assertIsNone(result["max_age_seconds"])


class WindTunnelIvFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_cohort_time_shock_and_expiry_exclusions_match_coverage(self):
        consumer = await consumer_with(option("expiring", volume=2, expiry_timestamp="2026-09-04T13:35:30Z"),
                                       option("remaining", volume=3, event_time="2026-09-04T13:30:00Z"))
        checkpoint = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        result = await wind.calculate({"terminal_checkpoint": checkpoint, "time_advance": 1})
        baseline, scenario = result["baseline"]["iv_freshness"], result["scenario"]["iv_freshness"]
        self.assertEqual((baseline["selected_contract_count"], baseline["selected_quantity"]), (2, 5))
        self.assertEqual((scenario["selected_contract_count"], scenario["selected_quantity"]), (1, 3))
        self.assertEqual(scenario["max_age_seconds"], 360)
        self.assertEqual(scenario["older_quantity"], 3)
        self.assertEqual(scenario["time_basis"], "scenario_model_time")
        self.assertEqual(result["scenario"]["counts"]["expired_rows"], 1)

    async def test_all_unpriced_early_return_discloses_freshness_denominator(self):
        consumer = await consumer_with(unavailable())
        checkpoint = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        result = await wind.calculate({"terminal_checkpoint": checkpoint})
        for state in (result["baseline"], result["scenario"]):
            self.assertEqual(state["status"], "no_data")
            self.assertEqual(state["iv_freshness"]["unpriced_quantity"], 7)
            self.assertEqual(state["iv_freshness"]["priced_quantity"], 0)
            self.assertIsNone(state["iv_freshness"]["max_age_seconds"])


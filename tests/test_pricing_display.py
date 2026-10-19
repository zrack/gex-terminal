"""Coverage presentation never supplies an IV or rewrites captured evidence."""
import copy
import unittest

from gex_terminal.pricing_display import build_pricing_display


class PricingDisplayTests(unittest.TestCase):
    def test_partial_contract_and_quantity_coverage_and_captured_price_reason(self):
        rows = [{"contract_id": "priced", "iv": .2, "accumulated_volume": 1691},
                {"contract_id": "missing", "symbol": "SYN", "option_type": "P", "strike": 130,
                 "expiry": "2026-10-16", "iv": None, "iv_source": "unavailable", "accumulated_volume": 1,
                 "iv_provenance": {"status": "outside_no_arbitrage_bounds", "option_price": 12,
                                   "lower_bound": 13.5, "underlying_price": 116.5,
                                   "underlying_price_age_ms": 493.863}}]
        before = copy.deepcopy(rows)
        display = build_pricing_display(None, rows)
        self.assertEqual(display["status"], "partial")
        self.assertIn("contracts 1/2 (50.00%)", display["summary"])
        self.assertIn("selected quantity 1,691/1,692 (99.94%)", display["summary"])
        self.assertIn("excluded from modeled GEX", display["reason_summary"])
        detail = display["details"][0]
        for expected in ("put 130", "contract missing", "quantity 1", "premium 12 points",
                         "minimum 13.5 points", "gap 1.5 points", "underlying 116.5", "0.494 seconds"):
            self.assertIn(expected, detail)
        self.assertEqual(rows, before)
        self.assertIsNone(rows[1]["iv"])

    def test_complete_all_unpriced_empty_and_unreported_are_distinct(self):
        complete = build_pricing_display(None, [{"iv": .2, "volume": 7}])
        self.assertEqual(complete["status"], "complete")
        self.assertIn("1/1 (100.00%)", complete["summary"])
        self.assertEqual(complete["details"], [])
        unavailable = build_pricing_display(None, [{"iv": None, "iv_source": "unavailable", "volume": 7}])
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertIn("0/1 (0.00%)", unavailable["summary"])
        self.assertIn("0/7 (0.00%)", unavailable["summary"])
        empty = build_pricing_display({"selected_contract_count": 0, "priced_contract_count": 0,
                                       "selected_quantity": 0, "priced_quantity": 0})
        self.assertEqual(empty["status"], "empty")
        self.assertIn("0/0 (n/a)", empty["summary"])
        self.assertNotIn("100", empty["summary"])
        self.assertEqual(build_pricing_display(None)["status"], "unreported")

    def test_partial_coverage_never_rounds_to_complete(self):
        display = build_pricing_display({"selected_contract_count": 1000000, "priced_contract_count": 999999,
                                         "selected_quantity": 1000000, "priced_quantity": 999999})
        self.assertEqual(display["status"], "partial")
        self.assertNotIn("100.00%", display["summary"])
        self.assertIn("<100%", display["summary"])

    def test_partial_quantity_cannot_be_labeled_complete(self):
        display = build_pricing_display({"selected_contract_count": 1, "priced_contract_count": 1,
                                         "selected_quantity": 10, "priced_quantity": 9})
        self.assertEqual(display["status"], "partial")
        self.assertIn("9/10 (90.00%)", display["summary"])
        self.assertIn("excluded", display["reason_summary"])

    def test_missing_provenance_does_not_invent_a_bound_or_market_cause(self):
        display = build_pricing_display(None, [{"iv": None, "iv_source": "unavailable", "volume": 1}])
        self.assertIn("No valid IV", display["details"][0])
        self.assertNotIn("minimum", display["details"][0])
        self.assertNotIn("bad", display["details"][0])

    def test_upper_bound_and_invalid_numeric_evidence_are_handled(self):
        row = {"iv_source": "unavailable", "iv": None, "volume": 1,
               "iv_provenance": {"status": "outside_no_arbitrage_bounds", "option_price": 20,
                                 "upper_bound": 19, "lower_bound": float("nan"),
                                 "underlying_price_age_ms": float("inf")}}
        detail = build_pricing_display(None, [row])["details"][0]
        self.assertIn("above the model maximum 19", detail)
        self.assertNotIn("nan", detail)
        self.assertNotIn("inf", detail)

    def test_retained_iv_is_priced_and_labeled_without_unpriced_reason(self):
        display = build_pricing_display(None, [{"iv": .2, "iv_source": "prior_valid", "volume": 2,
                                                "iv_provenance": {"status": "outside_no_arbitrage_bounds"}}])
        self.assertEqual(display["status"], "complete")
        self.assertIn("1 contract(s) use an earlier valid IV", display["summary"])
        self.assertEqual(display["reason_summary"], "")
        self.assertEqual(display["details"], [])

    def test_wind_excluded_row_explains_failure_without_adding_an_iv(self):
        coverage = {"selected_contract_count": 2, "priced_contract_count": 1,
                    "selected_quantity": 3, "priced_quantity": 2}
        excluded = {"contract_id": "missing", "quantity": 1, "reason": "iv_unavailable",
                    "iv_provenance": {"status": "outside_no_arbitrage_bounds",
                                      "option_price": 12, "lower_bound": 13.5}}
        before = copy.deepcopy(excluded)
        detail = build_pricing_display(coverage, [excluded])["details"][0]
        self.assertIn("below the model minimum 13.5", detail)
        self.assertIn("quantity 1", detail)
        self.assertEqual(excluded, before)


if __name__ == "__main__":
    unittest.main()

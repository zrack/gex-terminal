import unittest

from gex_terminal.tui import GexTerminalApp


def _rows():
    # strike, net_gex, volume vary independently so sorts are distinguishable
    return [
        {"strike": 5875.0, "net_gex": -84_000_000.0, "volume": 11_096},
        {"strike": 5900.0, "net_gex": -160_000_000.0, "volume": 12_187},
        {"strike": 5950.0, "net_gex": 3_450_000_000.0, "volume": 16_524},
        {"strike": 6000.0, "net_gex": 106_000_000.0, "volume": 12_496},
        {"strike": 6050.0, "net_gex": 75_000.0, "volume": 3_386},
    ]


class SortRowsTests(unittest.TestCase):
    def test_default_sorts_by_strike_ascending(self):
        result = GexTerminalApp._sort_rows(_rows(), "strike")
        self.assertEqual([r["strike"] for r in result], [5875, 5900, 5950, 6000, 6050])

    def test_net_sorts_by_absolute_net_descending(self):
        result = GexTerminalApp._sort_rows(_rows(), "net")
        self.assertEqual(result[0]["strike"], 5950.0)  # largest |net|
        self.assertEqual(result[-1]["strike"], 6050.0)  # smallest |net|

    def test_volume_sorts_by_volume_descending(self):
        result = GexTerminalApp._sort_rows(_rows(), "volume")
        self.assertEqual(result[0]["strike"], 5950.0)
        self.assertEqual(result[-1]["strike"], 6050.0)

    def test_unknown_mode_falls_back_to_strike(self):
        result = GexTerminalApp._sort_rows(_rows(), "nonsense")
        self.assertEqual([r["strike"] for r in result], [5875, 5900, 5950, 6000, 6050])


class FilterRowsTests(unittest.TestCase):
    def test_all_returns_everything(self):
        result = GexTerminalApp._filter_rows(_rows(), "all", spot=5943.25, max_volume=16_524)
        self.assertEqual(len(result), 5)

    def test_near_keeps_only_strikes_within_one_percent(self):
        result = GexTerminalApp._filter_rows(_rows(), "near", spot=5943.25, max_volume=16_524)
        strikes = {r["strike"] for r in result}
        # window = 5943.25 * 1% = 59.43 -> 5900 (43.25), 5950 (6.75), 6000 (56.75)
        self.assertEqual(strikes, {5900.0, 5950.0, 6000.0})

    def test_active_drops_low_volume_strikes(self):
        result = GexTerminalApp._filter_rows(_rows(), "active", spot=5943.25, max_volume=16_524)
        # threshold = 25% of 16524 = 4131; the 3,386-volume strike is dropped
        self.assertTrue(all(r["volume"] >= 4131 for r in result))
        self.assertNotIn(6050.0, {r["strike"] for r in result})

    def test_filter_never_empties_a_nonempty_table(self):
        far = [{"strike": 9999.0, "net_gex": 1.0, "volume": 1}]
        result = GexTerminalApp._filter_rows(far, "near", spot=5943.25, max_volume=16_524)
        self.assertEqual(result, far)  # fell back to full set rather than empty


class ArrangeRowsTests(unittest.TestCase):
    def test_filter_then_sort_compose(self):
        result = GexTerminalApp._arrange_rows(
            _rows(), sort_mode="net", filter_mode="near", spot=5943.25, max_volume=16_524
        )
        # near -> {5900, 5950, 6000}; |net| desc -> 5950 (3.45B), 5900 (160M), 6000 (106M)
        self.assertEqual([r["strike"] for r in result], [5950.0, 5900.0, 6000.0])


if __name__ == "__main__":
    unittest.main()

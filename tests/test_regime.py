import unittest

from gex_terminal.regime import build_regime_map


def _data(total_net=1_000_000.0, zero=5914.0, wall=5950.0):
    return {
        "strikes": [5900.0, 5925.0, 5950.0, 5975.0, 6000.0],
        "total_net_gex": total_net,
        "zero_gamma_strike": zero,
        "gamma_wall_strike": wall,
        "call_wall_strike": 5950.0,
        "put_wall_strike": 5900.0,
    }


class RegimeMapTests(unittest.TestCase):
    def test_positive_gamma_regime_when_clear_of_triggers(self):
        regime = build_regime_map(_data(total_net=1_000_000.0), spot=5980.0)

        self.assertEqual(regime["primary_regime"], "positive_gex_proxy")
        self.assertEqual(regime["state"], "positive_gex_proxy")
        self.assertEqual(regime["next_trigger"]["price"], 5950.0)
        self.assertEqual(regime["next_trigger"]["side"], "below")

    def test_negative_gamma_regime_when_total_net_is_negative(self):
        regime = build_regime_map(_data(total_net=-1_000_000.0), spot=5980.0)

        self.assertEqual(regime["primary_regime"], "negative_gex_proxy")
        self.assertEqual(regime["state"], "negative_gex_proxy")

    def test_transition_state_when_spot_is_near_zero_gamma(self):
        regime = build_regime_map(_data(zero=5925.0), spot=5929.0)

        self.assertEqual(regime["state"], "transition")
        self.assertEqual(regime["label"], "COMPATIBILITY PROXIMITY")

    def test_wall_proximity_state_when_spot_is_near_gamma_wall(self):
        regime = build_regime_map(_data(wall=5950.0), spot=5943.25)

        self.assertEqual(regime["state"], "wall_proximity")
        self.assertEqual(regime["label"], "WALL PROXIMITY")
        self.assertAlmostEqual(regime["distance_to_wall"], 6.75)

    def test_zones_include_all_regime_regions(self):
        regime = build_regime_map(_data(), spot=5980.0)
        zone_names = {zone["name"] for zone in regime["zones"]}

        self.assertEqual(
            zone_names,
            {
                "negative_gex_proxy_zone",
                "compatibility_transition",
                "positive_gex_proxy_zone",
                "wall_proximity_zone",
            },
        )


if __name__ == "__main__":
    unittest.main()

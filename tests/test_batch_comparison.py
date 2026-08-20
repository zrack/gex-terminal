import unittest

from gex_terminal.batch_comparison import build_batch_comparison
from gex_terminal.package_data import provider_fixture_path


class BatchComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_groups_sessions_without_summing_position_sources(self):
        report = await build_batch_comparison(
            provider_fixture_path("batch_position_comparison_example.json")
        )
        self.assertEqual(report["result"]["session_count"], 2)
        self.assertFalse(report["result"]["position_sources_summed"])
        self.assertEqual(report["groups"]["day"]["2026-08-06"]["sessions"], 2)
        self.assertEqual(report["result"]["predictive_validity"], "unmeasured")
        self.assertEqual(
            report["sessions"][0]["open_interest"]["position_sources"],
            ["open_interest"],
        )


if __name__ == "__main__":
    unittest.main()

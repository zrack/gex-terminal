import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.demo_lab import (
    DEMO_LAB_SCHEMA,
    build_demo_lab,
    compute_replay_snapshot,
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


class DemoLabTests(unittest.IsolatedAsyncioTestCase):
    async def test_compute_replay_snapshot_keeps_replay_status_without_credentials(self):
        snapshot, consumer, _ = await compute_replay_snapshot(_config())

        self.assertEqual(snapshot["symbol"], "ES")
        self.assertGreater(snapshot["spot"], 0)
        self.assertEqual(consumer.runtime_status, "REPLAY")

    async def test_build_demo_lab_writes_shareable_artifact_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "demo_lab"
            manifest = await build_demo_lab(
                _config(),
                output_dir,
                replay_session_name="zero-gamma-flip",
                screenshot_width=120,
                screenshot_height=36,
            )

            self.assertEqual(manifest["schema"], DEMO_LAB_SCHEMA)
            self.assertEqual(manifest["replay_session"]["name"], "zero-gamma-flip")
            self.assertEqual(manifest["output_dir"], "demo_lab")
            self.assertGreaterEqual(len(manifest["artifacts"]), 10)
            self.assertEqual(manifest["provider_fixture_lab"]["failed"], 0)

            color_svg = output_dir / "gex-terminal-color.svg"
            terminal_svg = output_dir / "terminal-screenshot.svg"
            manifest_path = output_dir / "manifest.json"
            readme_path = output_dir / "README.md"

            self.assertTrue(color_svg.exists())
            self.assertTrue(terminal_svg.exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(readme_path.exists())
            self.assertIn("#38bdf8", color_svg.read_text())
            readme = readme_path.read_text()
            self.assertIn("gex-terminal Demo Lab", readme)
            self.assertIn("manifest.json", readme)
            self.assertEqual(json.loads(manifest_path.read_text())["schema"], DEMO_LAB_SCHEMA)


if __name__ == "__main__":
    unittest.main()

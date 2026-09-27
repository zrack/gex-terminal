import hashlib
from importlib.resources import files
import json
import unittest


class WindTunnelAssetTests(unittest.TestCase):
    def test_offline_chart_and_icon_assets_match_pinned_release_inventory(self):
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        inventory = json.loads(root.joinpath("vendor/manifest.json").read_text())
        self.assertEqual(inventory["schema"], "gex-terminal.vendor-assets.v1")
        for package in inventory["packages"]:
            for name, expected in package["files"].items():
                with self.subTest(asset=name):
                    self.assertEqual(hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest(), expected)
        page = root.joinpath("index.html").read_text()
        self.assertIn('/static/vendor/plotly.min.js', page)
        self.assertNotRegex(page, r'(?:src|href)=["\']https?://')
        self.assertTrue(files("gex_terminal").joinpath("data/wind_tunnel/es_multi_expiry.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from gex_terminal.config import GexConfig


class GexConfigTests(unittest.TestCase):
    def test_defaults_to_demo_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            config = GexConfig.from_env()

        self.assertEqual(config.data_mode, "demo")
        self.assertEqual(config.replay_path, "sample_data/demo_replay.jsonl")


if __name__ == "__main__":
    unittest.main()

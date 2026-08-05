import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.config import GexConfig, _load_working_directory_dotenv


class GexConfigTests(unittest.TestCase):
    def test_defaults_to_demo_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            config = GexConfig.from_env()

        self.assertEqual(config.data_mode, "demo")
        self.assertEqual(config.data_provider, "tradovate")
        self.assertEqual(Path(config.replay_path).name, "demo_replay.jsonl")
        self.assertTrue(Path(config.replay_path).is_file())
        self.assertEqual(config.expiry_filter, "all")

    def test_reads_expiry_filter_from_environment(self):
        with patch.dict(os.environ, {"GEX_EXPIRY_FILTER": "0dte"}, clear=True):
            config = GexConfig.from_env()

        self.assertEqual(config.expiry_filter, "0dte")

    def test_loads_dotenv_from_callers_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "GEX_SYMBOL=NQ\nGEX_DATA_MODE=replay\n",
                encoding="utf-8",
            )
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {}, clear=True):
                    self.assertTrue(_load_working_directory_dotenv())
                    config = GexConfig.from_env()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(config.symbol, "NQ")
        self.assertEqual(config.data_mode, "replay")


if __name__ == "__main__":
    unittest.main()

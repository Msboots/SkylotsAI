"""Тесты конфигурации приложения."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skylots_ai.config import Config


class ConfigTests(unittest.TestCase):

    def test_unknown_keys_are_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "check_interval": 45,
                        "max_price": 30,
                        "unknown_option": "ignored",
                    },
                ),
                encoding="utf-8",
            )

            config = Config(path)

            self.assertEqual(config.check_interval, 45)
            self.assertEqual(config.max_price, 30)

    def test_monitor_settings_survive_save_and_reload(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{}", encoding="utf-8")
            config = Config(path)
            config.monitor_mode = "single"
            config.active_profile_id = "favorites"

            config.save()
            reloaded = Config(path)

            self.assertEqual(reloaded.monitor_mode, "single")
            self.assertEqual(reloaded.active_profile_id, "favorites")

    def test_invalid_monitor_mode_falls_back_to_multi(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{}", encoding="utf-8")
            config = Config(path)

            config.monitor_mode = "unsupported"

            self.assertEqual(config.monitor_mode, "multi")


if __name__ == "__main__":
    unittest.main()

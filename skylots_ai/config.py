"""
Работа с настройками проекта.
"""

from pathlib import Path
import json

from skylots_ai.models import AppSettings


class Config:

    DEFAULT_PATH = Path("settings/config.json")

    def __init__(self, path: Path | None = None):
        self.file = path or self.DEFAULT_PATH
        self.settings = AppSettings()
        self.reload()

    def reload(self):
        with open(self.file, encoding="utf-8") as f:
            self.data = json.load(f)
        self.settings = AppSettings.from_dict(self.data)

    def save(self):
        self.data = self.settings.to_dict()
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(
                self.data,
                f,
                indent=4,
                ensure_ascii=False,
            )

    @property
    def check_interval(self) -> int:
        return self.settings.check_interval

    @property
    def max_price(self) -> int:
        return self.settings.max_price

    @property
    def max_minutes(self) -> int:
        return self.settings.max_minutes

    @property
    def telegram(self) -> bool:
        return self.settings.telegram

    @property
    def sound(self) -> bool:
        return self.settings.sound

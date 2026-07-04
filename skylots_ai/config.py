"""
Работа с настройками проекта.
"""

from pathlib import Path
import json


class Config:

    def __init__(self):

        self.file = Path("settings/config.json")

        self.reload()

    def reload(self):

        with open(self.file, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def save(self):

        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(
                self.data,
                f,
                indent=4,
                ensure_ascii=False
            )

    @property
    def check_interval(self) -> int:
        return self.data["check_interval"]

    @property
    def max_price(self) -> int:
        return self.data["max_price"]

    @property
    def max_minutes(self) -> int:
        return self.data["max_minutes"]

    @property
    def telegram(self) -> bool:
        return self.data["telegram"]

    @property
    def sound(self) -> bool:
        return self.data["sound"]

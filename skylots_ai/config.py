"""
Работа с настройками проекта.
"""

from pathlib import Path
import json

from skylots_ai.models import AppSettings


class Config:

    DEFAULT_PATH = Path("settings/config.json")

    def __init__(self, path: Path | None = None) -> None:
        self.file = path or self.DEFAULT_PATH
        self.settings = AppSettings()
        self.reload()

    def reload(self) -> None:
        with open(self.file, encoding="utf-8") as f:
            self.data = json.load(f)
        self.settings = AppSettings.from_dict(self.data)

    def save(self) -> None:
        self.data = self.settings.to_dict()
        self.file.parent.mkdir(parents=True, exist_ok=True)
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

    @property
    def monitor_mode(self) -> str:
        if self.settings.monitor_mode not in {"multi", "single"}:
            return "multi"
        return self.settings.monitor_mode

    @monitor_mode.setter
    def monitor_mode(self, value: str) -> None:
        if value in {"multi", "single"}:
            self.settings.monitor_mode = value
        else:
            self.settings.monitor_mode = "multi"

    @property
    def active_profile_id(self) -> str:
        return self.settings.active_profile_id

    @active_profile_id.setter
    def active_profile_id(self, value: str) -> None:
        self.settings.active_profile_id = value

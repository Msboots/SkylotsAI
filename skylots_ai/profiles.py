"""
Профили поиска Skylots.
"""

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


@dataclass
class SearchProfile:
    id: str
    name: str
    url: str
    enabled: bool = True
    interval: int = 30
    created_at: str = ""
    last_scan: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchProfile":
        allowed = {field.name for field in fields(cls)}
        profile_data = {key: value for key, value in data.items() if key in allowed}

        if not profile_data.get("created_at"):
            profile_data["created_at"] = _now()

        if "last_scan" not in profile_data:
            profile_data["last_scan"] = None

        return cls(**profile_data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProfileManager:

    DEFAULT_PATH = Path("settings/profiles.json")

    def __init__(self, path: Path | None = None) -> None:
        self.file = path or self.DEFAULT_PATH
        self.profiles: list[SearchProfile] = []
        self.load()

    def load(self) -> list[SearchProfile]:
        if not self.file.exists():
            self._create_default_file()

        with open(self.file, encoding="utf-8") as file:
            data = json.load(file)

        self.profiles = [SearchProfile.from_dict(item) for item in data]
        return self.profiles

    def save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.file, "w", encoding="utf-8") as file:
            json.dump(
                [profile.to_dict() for profile in self.profiles],
                file,
                indent=4,
                ensure_ascii=False,
            )

    def get_all(self) -> list[SearchProfile]:
        return list(self.profiles)

    def get_enabled(self) -> list[SearchProfile]:
        return [profile for profile in self.profiles if profile.enabled]

    def add_profile(
        self,
        name: str,
        url: str,
        interval: int = 30,
        enabled: bool = True,
    ) -> SearchProfile:
        profile = SearchProfile(
            id=self._make_unique_id(name),
            name=name,
            url=url,
            enabled=enabled,
            interval=interval,
            created_at=_now(),
        )
        self.profiles.append(profile)
        self.save()
        return profile

    def remove_profile(self, profile_id: str) -> bool:
        original_count = len(self.profiles)
        self.profiles = [
            profile
            for profile in self.profiles
            if profile.id != profile_id
        ]

        removed = len(self.profiles) != original_count
        if removed:
            self.save()

        return removed

    def rename_profile(self, profile_id: str, name: str) -> bool:
        profile = self._find_profile(profile_id)
        if profile is None:
            return False

        profile.name = name
        self.save()
        return True

    def enable(self, profile_id: str) -> bool:
        return self._set_enabled(profile_id, True)

    def disable(self, profile_id: str) -> bool:
        return self._set_enabled(profile_id, False)

    def update_interval(self, profile_id: str, interval: int) -> bool:
        profile = self._find_profile(profile_id)
        if profile is None:
            return False

        profile.interval = interval
        self.save()
        return True

    def update_last_scan(self, profile_id: str, last_scan: str) -> bool:
        profile = self._find_profile(profile_id)
        if profile is None:
            return False

        profile.last_scan = last_scan
        self.save()
        return True

    def _set_enabled(self, profile_id: str, enabled: bool) -> bool:
        profile = self._find_profile(profile_id)
        if profile is None:
            return False

        profile.enabled = enabled
        self.save()
        return True

    def _find_profile(self, profile_id: str) -> SearchProfile | None:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile

        return None

    def _make_unique_id(self, name: str) -> str:
        base_id = _slugify(name)
        profile_id = base_id
        index = 2
        existing_ids = {profile.id for profile in self.profiles}

        while profile_id in existing_ids:
            profile_id = f"{base_id}-{index}"
            index += 1

        return profile_id

    def _create_default_file(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        default_profiles = [
            {
                "id": "hot",
                "name": "Hot Auctions",
                "url": "https://skylots.org/search.php?orderby=5",
                "enabled": True,
                "interval": 30,
            }
        ]

        with open(self.file, "w", encoding="utf-8") as file:
            json.dump(
                default_profiles,
                file,
                indent=4,
                ensure_ascii=False,
            )


def add_profile_from_url(
    url: str,
    manager: ProfileManager | None = None,
) -> SearchProfile:
    profile_manager = manager or ProfileManager()
    name = input("Profile name: ").strip()
    return profile_manager.add_profile(name=name, url=url)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "profile"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

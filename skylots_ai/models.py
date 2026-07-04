"""
Модели данных проекта.
"""

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class AppSettings:
    check_interval: int = 60
    max_price: int = 20
    max_minutes: int = 15
    telegram: bool = False
    sound: bool = True
    monitor_mode: str = "multi"
    active_profile_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Lot:
    id: str
    title: str
    seller: str
    price: int
    url: str
    city: str | None = None
    rating: float | None = None
    end_time: str | None = None
    remaining_time_text: str | None = None
    bids_count: int | None = None
    profile_name: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None


@dataclass
class PriceHistory:
    lot_id: str
    price: int
    checked_at: str
    id: int | None = None


@dataclass
class Notification:
    lot_id: str
    notification_type: str
    sent_at: str
    id: int | None = None


@dataclass
class Seller:
    seller: str
    rating: float | None = None
    lots_found: int = 0
    blacklisted: int = 0
    favorite: int = 0
    notes: str | None = None

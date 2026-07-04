"""
Консольные уведомления мониторинга.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import sys

from skylots_ai.models import Lot


@dataclass
class ConsoleProfileState:
    name: str
    fetched: int = 0
    new_lots: int = 0
    last_scan: str = "-"


@dataclass
class ConsoleLotState:
    time: str
    title: str
    price: int
    seller: str
    remaining_time: str


class ConsoleNotifier:

    MAX_LOTS = 10

    def __init__(self) -> None:
        self.status = "Starting..."
        self.countdown = 0
        self.profiles_loaded = 0
        self.database_lots_count = 0
        self.profiles: dict[str, ConsoleProfileState] = {}
        self.latest_lots: list[ConsoleLotState] = []

    def start(
        self,
        profiles: list[str],
        database_lots_count: int,
        status: str = "RUNNING",
    ) -> None:
        self.status = status
        self.profiles_loaded = len(profiles)
        self.database_lots_count = database_lots_count
        self.profiles = {
            name: ConsoleProfileState(name=name)
            for name in profiles
        }
        self.render()

    def set_status(self, status: str) -> None:
        self.status = status
        self.render()

    def set_countdown(self, seconds: int) -> None:
        self.countdown = seconds
        self.status = "Waiting..."
        self.render()

    def update_database_lots_count(self, count: int) -> None:
        self.database_lots_count = count

    def print_summary(
        self,
        profile_name: str,
        fetched: int,
        new_lots: int,
    ) -> None:
        profile = self.profiles.setdefault(
            profile_name,
            ConsoleProfileState(name=profile_name),
        )
        profile.fetched = fetched
        profile.new_lots = new_lots
        profile.last_scan = datetime.now().strftime("%H:%M:%S")
        self.render()

    def print_new_lot(self, lot: Lot) -> None:
        self.latest_lots.insert(
            0,
            ConsoleLotState(
                time=datetime.now().strftime("%H:%M:%S"),
                title=lot.title,
                price=lot.price,
                seller=lot.seller or "-",
                remaining_time=lot.end_time or "-",
            ),
        )
        self.latest_lots = self.latest_lots[:self.MAX_LOTS]
        self.render()

    def print_status(
        self,
        title: str,
        lines: Sequence[str] | None = None,
    ) -> None:
        details = " ".join(lines or [])
        self.status = f"{title} {details}".strip()
        self.render()

    def render(self) -> None:
        self._clear()
        lines = [
            "=" * 56,
            "Skylots AI Assistant",
            "",
            f"Status: {self.status}",
            f"Current time: {datetime.now().strftime('%H:%M:%S')}",
            f"Next scan countdown: {self.countdown} sec",
            f"Profiles loaded: {self.profiles_loaded}",
            f"Database lots count: {self.database_lots_count}",
            "=" * 56,
            "",
            "Profiles",
        ]
        lines.extend(self._profile_lines())
        lines.extend(
            [
                "=" * 56,
                "",
                "Latest new lots",
                "",
                self._lot_header(),
            ]
        )
        lines.extend(self._lot_lines())
        lines.extend(
            [
                "=" * 56,
                "",
                "Status",
                "",
                self.status,
                "",
                "=" * 56,
                "",
                "Keyboard",
                "",
                "CTRL+C = Exit",
                "=" * 56,
            ]
        )
        sys.stdout.write("\n".join(lines))
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _profile_lines(self) -> list[str]:
        if not self.profiles:
            return ["-", ""]

        lines: list[str] = []
        for profile in self.profiles.values():
            lines.extend(
                [
                    f"✓ {profile.name}",
                    f"Fetched: {profile.fetched}",
                    f"New: {profile.new_lots}",
                    f"Last scan: {profile.last_scan}",
                    "",
                ]
            )
        return lines

    def _lot_lines(self) -> list[str]:
        if not self.latest_lots:
            return ["No new lots.", ""]

        return [
            (
                f"{lot.time:<8} "
                f"{self._trim(lot.title, 24):<24} "
                f"{lot.price:<8} "
                f"{self._trim(lot.seller, 14):<14} "
                f"{lot.remaining_time}"
            )
            for lot in self.latest_lots
        ] + [""]

    @staticmethod
    def _lot_header() -> str:
        return (
            f"{'Time':<8} "
            f"{'Title':<24} "
            f"{'Price':<8} "
            f"{'Seller':<14} "
            "Remaining time"
        )

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit - 1]}."

    @staticmethod
    def _clear() -> None:
        sys.stdout.write("\033[2J\033[H")

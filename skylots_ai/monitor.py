"""
Мониторинг лотов Skylots.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Protocol

from skylots_ai.config import Config
from skylots_ai.console import ConsoleNotifier
from skylots_ai.database import Database
from skylots_ai.logger import LOG_NAME, setup
from skylots_ai.models import Lot
from skylots_ai.parser import Parser
from skylots_ai.profiles import ProfileManager, SearchProfile


class Notifier(Protocol):

    def start(
        self,
        profiles: list[str],
        database_lots_count: int,
        status: str = "РАБОТАЕТ",
        profile_urls: dict[str, str] | None = None,
    ) -> None:
        ...

    def stop(self) -> None:
        ...

    def set_status(self, status: str) -> None:
        ...

    def set_countdown(self, seconds: int) -> None:
        ...

    def update_database_lots_count(self, count: int) -> None:
        ...

    def print_status(
        self,
        title: str,
        lines: Sequence[str] | None = None,
    ) -> None:
        ...

    def print_summary(
        self,
        profile_name: str,
        fetched: int,
        new_lots: int,
    ) -> None:
        ...

    def print_new_lot(self, lot: Lot) -> None:
        ...


@dataclass
class ProfileScanSummary:
    profile_id: str
    profile_name: str
    fetched: int = 0
    new_lots: int = 0
    existing_lots: int = 0
    new_lot_items: list[Lot] = field(default_factory=list)


class Monitor:

    def __init__(
        self,
        config: Config | None = None,
        database: Database | None = None,
        parser: Parser | None = None,
        profile_manager: ProfileManager | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.config = config or Config()
        self.database = database or Database()
        self.parser = parser or Parser(self.config)
        self.profile_manager = profile_manager or ProfileManager()
        self.notifier = notifier or ConsoleNotifier()
        self.logger = self._get_logger()
        self.database.initialize()

    def run(self) -> None:
        profiles = self.profile_manager.get_enabled()
        self.logger.info("Skylots AI Assistant started")
        self.logger.info("Enabled profiles: %s", len(profiles))
        self.notifier.start(
            profiles=[profile.name for profile in profiles],
            database_lots_count=self.database.count_lots(),
            status="РАБОТАЕТ",
            profile_urls={profile.name: profile.url for profile in profiles},
        )

        try:
            while True:
                try:
                    self.single_run()
                    self._wait()
                except Exception as exc:
                    self.logger.exception("Monitoring loop error: %s", exc)
                    self.notifier.set_status(
                        "ОШИБКА. Подробности в logs/skylots.log.",
                    )
                    self._wait()
        except KeyboardInterrupt:
            self.logger.info("Skylots AI Assistant stopped by user")
            self.notifier.print_status(
                "Остановка...",
                ["До свидания."],
            )
        finally:
            self.notifier.stop()

    def single_run(self) -> list[ProfileScanSummary]:
        summaries: list[ProfileScanSummary] = []

        for profile in self.profile_manager.get_enabled():
            summaries.append(self._scan_profile(profile))

        return summaries

    def _scan_profile(self, profile: SearchProfile) -> ProfileScanSummary:
        self.logger.info("Scanning profile: %s", profile.name)
        self.notifier.set_status(f"Scanning profile: {profile.name}...")

        html = self.parser.fetch(profile.url)
        lots = self.parser.parse(html)
        summary = ProfileScanSummary(
            profile_id=profile.id,
            profile_name=profile.name,
            fetched=len(lots),
        )
        seen_at = self._now()

        for lot in lots:
            existing_lot = self.database.get_lot(lot.id)

            if existing_lot is None:
                self.database.insert_lot(lot, seen_at)
                self.notifier.update_database_lots_count(
                    self.database.count_lots(),
                )
                summary.new_lots += 1
                summary.new_lot_items.append(lot)
                self.logger.info("New lot: %s | %s", lot.title, lot.url)
            else:
                self.database.update_last_seen(lot.id, seen_at)
                summary.existing_lots += 1

        self.profile_manager.update_last_scan(profile.id, seen_at)
        self.logger.info("Total lots: %s", summary.fetched)
        self.logger.info("New lots: %s", summary.new_lots)
        self.logger.info("Existing lots: %s", summary.existing_lots)

        self.notifier.print_summary(
            profile_name=summary.profile_name,
            fetched=summary.fetched,
            new_lots=summary.new_lots,
        )

        for lot in summary.new_lot_items:
            self.notifier.print_new_lot(lot)

        return summary

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _wait(self) -> None:
        seconds = self.config.check_interval
        self.logger.info("Waiting %s seconds", seconds)

        for remaining in range(seconds, 0, -1):
            self.notifier.set_countdown(remaining)
            time.sleep(1)

        self.notifier.set_countdown(0)

    def _get_logger(self) -> logging.Logger:
        logger = logging.getLogger(LOG_NAME)
        if not logger.handlers:
            setup()
        return logging.getLogger(LOG_NAME)

"""
Мониторинг лотов Skylots.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time

from skylots_ai.config import Config
from skylots_ai.database import Database
from skylots_ai.logger import LOG_NAME, setup
from skylots_ai.parser import Parser
from skylots_ai.profiles import ProfileManager, SearchProfile


@dataclass
class ProfileScanSummary:
    profile_id: str
    profile_name: str
    fetched: int = 0
    new_lots: int = 0
    existing_lots: int = 0


class Monitor:

    def __init__(
        self,
        config: Config | None = None,
        database: Database | None = None,
        parser: Parser | None = None,
        profile_manager: ProfileManager | None = None,
    ) -> None:
        self.config = config or Config()
        self.database = database or Database()
        self.parser = parser or Parser(self.config)
        self.profile_manager = profile_manager or ProfileManager()
        self.logger = self._get_logger()
        self.database.initialize()

    def run(self) -> None:
        while True:
            self._scan_due_profiles()
            time.sleep(self._sleep_seconds())

    def single_run(self) -> list[ProfileScanSummary]:
        summaries: list[ProfileScanSummary] = []

        for profile in self.profile_manager.get_enabled():
            summaries.append(self._scan_profile(profile))

        return summaries

    def _scan_due_profiles(self) -> list[ProfileScanSummary]:
        summaries: list[ProfileScanSummary] = []

        for profile in self.profile_manager.get_enabled():
            if self._is_due(profile):
                summaries.append(self._scan_profile(profile))

        return summaries

    def _scan_profile(self, profile: SearchProfile) -> ProfileScanSummary:
        self.logger.info("Scanning profile: %s", profile.name)

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
                summary.new_lots += 1
            else:
                self.database.update_last_seen(lot.id, seen_at)
                summary.existing_lots += 1

        self.profile_manager.update_last_scan(profile.id, seen_at)
        self.logger.info("Total lots: %s", summary.fetched)
        self.logger.info("New lots: %s", summary.new_lots)
        self.logger.info("Existing lots: %s", summary.existing_lots)

        return summary

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_due(self, profile: SearchProfile) -> bool:
        if profile.last_scan is None:
            return True

        try:
            last_scan = datetime.fromisoformat(profile.last_scan)
        except ValueError:
            return True

        elapsed = datetime.now(timezone.utc) - last_scan
        return elapsed.total_seconds() >= profile.interval

    def _sleep_seconds(self) -> int:
        enabled_profiles = self.profile_manager.get_enabled()

        if not enabled_profiles:
            return self.config.check_interval

        now = datetime.now(timezone.utc)
        remaining_times: list[int] = []

        for profile in enabled_profiles:
            if profile.last_scan is None:
                return 1

            try:
                last_scan = datetime.fromisoformat(profile.last_scan)
            except ValueError:
                return 1

            elapsed = (now - last_scan).total_seconds()
            remaining = max(1, int(profile.interval - elapsed))
            remaining_times.append(remaining)

        return min(remaining_times)

    def _get_logger(self) -> logging.Logger:
        logger = logging.getLogger(LOG_NAME)
        if not logger.handlers:
            setup()
        return logging.getLogger(LOG_NAME)

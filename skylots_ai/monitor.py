"""
Мониторинг лотов Skylots.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import select
import sys
import termios
import time
import tty
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

    def set_system_status(self, name: str, ok: bool) -> None:
        ...

    def set_profiles(self, profiles: Sequence[SearchProfile]) -> None:
        ...

    def resume(self) -> None:
        ...

    def prompt_new_profile(self, default_interval: int = 30) -> tuple[str, str, int]:
        ...

    def show_profile_list(self, profiles: Sequence[SearchProfile]) -> None:
        ...

    def add_event(self, message: str) -> None:
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
        self.notifier.set_system_status("SQLite", True)
        self.notifier.set_system_status("Profiles", bool(profiles))
        self.notifier.set_system_status(
            "Cookies",
            bool(self.parser.session.cookies),
        )

        try:
            while True:
                try:
                    self.single_run()
                    if not self._wait():
                        break
                except Exception as exc:
                    self.logger.exception("Monitoring loop error: %s", exc)
                    self.notifier.set_status(
                        "ОШИБКА. Подробности в logs/skylots.log.",
                    )
                    if not self._wait():
                        break
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
        self.notifier.set_system_status("Internet", bool(html))
        self.notifier.set_system_status("Parser", bool(lots) or not html)
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

    def _wait(self) -> bool:
        seconds = self.config.check_interval
        self.logger.info("Waiting %s seconds", seconds)
        terminal_settings = self._enable_hotkeys()

        try:
            for remaining in range(seconds, 0, -1):
                self.notifier.set_countdown(remaining)
                key = self._read_hotkey(1.0)
                if not key:
                    continue

                self._restore_terminal(terminal_settings)
                terminal_settings = None
                should_continue = self._handle_hotkey(key)
                if not should_continue:
                    return False

                terminal_settings = self._enable_hotkeys()
        finally:
            self._restore_terminal(terminal_settings)

        self.notifier.set_countdown(0)
        return True

    def _handle_hotkey(self, key: str) -> bool:
        normalized = key.lower()

        if normalized == "a":
            self._add_profile_from_dashboard()
            return True
        if normalized == "r":
            self._reload_profiles()
            return True
        if normalized == "l":
            self.notifier.show_profile_list(self.profile_manager.get_all())
            self.notifier.resume()
            return True
        if normalized == "q":
            self.logger.info("Skylots AI Assistant stopped by hotkey")
            self.notifier.print_status(
                "Остановка...",
                ["До свидания."],
            )
            return False

        return True

    def _add_profile_from_dashboard(self) -> None:
        name, url, interval = self.notifier.prompt_new_profile(
            default_interval=30,
        )

        error = self._validate_profile_input(name, url)
        if error is not None:
            self.notifier.add_event(error)
            self.notifier.resume()
            return

        safe_interval = interval if interval > 0 else 30
        profile = self.profile_manager.add_profile(
            name=name,
            url=url,
            interval=safe_interval,
        )
        self.logger.info("Profile added from dashboard: %s", profile.name)
        self.notifier.add_event(f"Профиль добавлен: {profile.name}")
        self._sync_profiles_to_dashboard()
        self.notifier.set_system_status(
            "Profiles",
            bool(self.profile_manager.get_enabled()),
        )
        self.notifier.resume()

    def _reload_profiles(self) -> None:
        self.profile_manager.load()
        self._sync_profiles_to_dashboard()
        self.notifier.set_system_status(
            "Profiles",
            bool(self.profile_manager.get_enabled()),
        )
        self.notifier.add_event("Профили обновлены")

    def _sync_profiles_to_dashboard(self) -> None:
        self.notifier.set_profiles(self.profile_manager.get_enabled())

    @staticmethod
    def _validate_profile_input(name: str, url: str) -> str | None:
        if not name.strip():
            return "Ошибка: пустое название профиля"
        if not url.startswith("https://"):
            return "Ошибка: нужен URL с https://"
        if "skylots.org" not in url:
            return "Ошибка: нужен URL skylots.org"
        return None

    @staticmethod
    def _enable_hotkeys() -> list[int | bytes] | None:
        if not sys.stdin.isatty():
            return None

        settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin)
        return settings

    @staticmethod
    def _restore_terminal(settings: list[int | bytes] | None) -> None:
        if settings is not None and sys.stdin.isatty():
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)

    @staticmethod
    def _read_hotkey(timeout: float) -> str:
        if not sys.stdin.isatty():
            time.sleep(timeout)
            return ""

        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if not readable:
            return ""

        return sys.stdin.read(1)

    def _get_logger(self) -> logging.Logger:
        logger = logging.getLogger(LOG_NAME)
        if not logger.handlers:
            setup()
        return logging.getLogger(LOG_NAME)

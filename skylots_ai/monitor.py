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

    def set_profiles(
        self,
        profiles: Sequence[SearchProfile],
        monitor_mode: str = "multi",
        active_profile_id: str = "",
    ) -> None:
        ...

    def resume(self) -> None:
        ...

    def prompt_new_profile(self, default_interval: int = 30) -> tuple[str, str, int]:
        ...

    def show_profile_list(self, profiles: Sequence[SearchProfile]) -> None:
        ...

    def prompt_profile_interval(self, profile_name: str) -> int | None:
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

    def update_ending_lots(self, profile_name: str, lots: Sequence[Lot]) -> None:
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
        self.monitor_mode = self.config.monitor_mode
        self.active_profile_id = self.config.active_profile_id
        self._ensure_active_profile()

    def run(self) -> None:
        profiles = self.profile_manager.get_all()
        self.logger.info("Skylots AI Assistant started")
        self.logger.info("Profiles loaded: %s", len(profiles))
        self.notifier.start(
            profiles=[profile.name for profile in profiles],
            database_lots_count=self.database.count_lots(),
            status="РАБОТАЕТ",
            profile_urls={profile.name: profile.url for profile in profiles},
        )
        self._sync_profiles_to_dashboard()
        self.notifier.set_system_status("SQLite", True)
        self.notifier.set_system_status(
            "Profiles",
            bool(self.profile_manager.get_all()),
        )
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

        for profile in self._profiles_to_scan():
            summaries.append(self._scan_profile(profile))

        return summaries

    def _scan_profile(self, profile: SearchProfile) -> ProfileScanSummary:
        self.logger.info("Scanning profile: %s", profile.name)
        self.notifier.set_status(f"Scanning profile: {profile.name}...")

        html = self.parser.fetch(profile.url)
        lots = self.parser.parse(html)
        for lot in lots:
            lot.profile_name = profile.name
        self.notifier.set_system_status("Internet", bool(html))
        self.notifier.set_system_status("Parser", bool(lots) or not html)
        self.notifier.update_ending_lots(profile.name, lots)
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
        seconds = self._current_wait_seconds()
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
                action = self._handle_hotkey(key)
                if action == "stop":
                    return False
                if action == "scan":
                    self.notifier.set_countdown(0)
                    return True

                terminal_settings = self._enable_hotkeys()
        finally:
            self._restore_terminal(terminal_settings)

        self.notifier.set_countdown(0)
        return True

    def _handle_hotkey(self, key: str) -> str:
        normalized = key.lower()

        if normalized == "a":
            self._add_profile_from_dashboard()
            return "wait"
        if normalized == "e":
            self._toggle_active_profile()
            return "wait"
        if normalized == "m":
            self._toggle_monitor_mode()
            return "wait"
        if normalized == "n":
            self._select_relative_profile(1)
            return "wait"
        if normalized == "p":
            self._select_relative_profile(-1)
            return "wait"
        if normalized == "i":
            self._change_active_profile_interval()
            return "wait"
        if normalized == "r":
            self._reload_profiles()
            return "wait"
        if normalized == "s":
            self.notifier.add_event(
                "Сканирование запущено вручную",
            )
            return "scan"
        if normalized == "l":
            self.notifier.show_profile_list(self.profile_manager.get_all())
            self.notifier.resume()
            return "wait"
        if normalized == "q":
            self.logger.info("Skylots AI Assistant stopped by hotkey")
            self.notifier.print_status(
                "Остановка...",
                ["До свидания."],
            )
            return "stop"

        return "wait"

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
        self._ensure_active_profile()
        self._sync_profiles_to_dashboard()
        self.notifier.set_system_status(
            "Profiles",
            bool(self.profile_manager.get_all()),
        )
        self.notifier.add_event("Профили обновлены")

    def _sync_profiles_to_dashboard(self) -> None:
        self.notifier.set_profiles(
            self.profile_manager.get_all(),
            monitor_mode=self.monitor_mode,
            active_profile_id=self.active_profile_id,
        )

    def _profiles_to_scan(self) -> list[SearchProfile]:
        if self.monitor_mode == "multi":
            return self.profile_manager.get_enabled()

        active_profile = self._active_profile()
        if active_profile is None or not active_profile.enabled:
            return []
        return [active_profile]

    def _current_wait_seconds(self) -> int:
        if self.monitor_mode == "single":
            active_profile = self._active_profile()
            if active_profile is not None and active_profile.enabled:
                return max(active_profile.interval, 5)
            return self.config.check_interval

        intervals = [
            profile.interval
            for profile in self.profile_manager.get_enabled()
            if profile.interval >= 5
        ]
        if intervals:
            return min(intervals)
        return self.config.check_interval

    def _active_profile(self) -> SearchProfile | None:
        return self.profile_manager.get_by_id(self.active_profile_id)

    def _ensure_active_profile(self) -> None:
        profiles = self.profile_manager.get_all()
        if not profiles:
            self.active_profile_id = ""
            self._save_monitor_settings()
            return

        if self.profile_manager.get_by_id(self.active_profile_id) is None:
            self.active_profile_id = profiles[0].id
            self._save_monitor_settings()

    def _toggle_monitor_mode(self) -> None:
        self.monitor_mode = "single" if self.monitor_mode == "multi" else "multi"
        self.config.monitor_mode = self.monitor_mode
        self._ensure_active_profile()
        self._save_monitor_settings()
        self._sync_profiles_to_dashboard()
        event = (
            "Режим: все профили"
            if self.monitor_mode == "multi"
            else "Режим: один профиль"
        )
        self.notifier.add_event(event)

    def _select_relative_profile(self, step: int) -> None:
        profiles = self.profile_manager.get_all()
        if not profiles:
            self.active_profile_id = ""
            self._save_monitor_settings()
            self._sync_profiles_to_dashboard()
            self.notifier.add_event("Профили не найдены")
            return

        profile_ids = [profile.id for profile in profiles]
        try:
            current_index = profile_ids.index(self.active_profile_id)
        except ValueError:
            current_index = 0

        next_index = (current_index + step) % len(profile_ids)
        self.active_profile_id = profile_ids[next_index]
        self._save_monitor_settings()
        self._sync_profiles_to_dashboard()
        active_profile = self._active_profile()
        if active_profile is not None:
            self.notifier.add_event(
                f"Активный профиль: {active_profile.name}",
            )

    def _toggle_active_profile(self) -> None:
        active_profile = self._active_profile()
        if active_profile is None:
            self.notifier.add_event("Профили не найдены")
            return

        if active_profile.enabled:
            self.profile_manager.disable(active_profile.id)
            self.notifier.add_event(
                f"Профиль отключен: {active_profile.name}",
            )
        else:
            self.profile_manager.enable(active_profile.id)
            self.notifier.add_event(
                f"Профиль включен: {active_profile.name}",
            )

        self.profile_manager.load()
        self._ensure_active_profile()
        self._sync_profiles_to_dashboard()
        self.notifier.set_system_status(
            "Profiles",
            bool(self.profile_manager.get_all()),
        )

    def _change_active_profile_interval(self) -> None:
        active_profile = self._active_profile()
        if active_profile is None:
            self.notifier.add_event("Профили не найдены")
            return

        interval = self.notifier.prompt_profile_interval(active_profile.name)
        if interval is None or interval < 5:
            self.notifier.add_event(
                "Ошибка: интервал должен быть >= 5",
            )
            self.notifier.resume()
            return

        self.profile_manager.update_interval(active_profile.id, interval)
        self.profile_manager.load()
        self._sync_profiles_to_dashboard()
        self.notifier.add_event(
            (
                f"Интервал профиля {active_profile.name} "
                f"изменён на {interval} сек"
            ),
        )
        self.notifier.resume()

    def _save_monitor_settings(self) -> None:
        self.config.monitor_mode = self.monitor_mode
        self.config.active_profile_id = self.active_profile_id
        self.config.save()

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

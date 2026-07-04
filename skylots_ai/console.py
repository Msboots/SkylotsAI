"""
Консольный dashboard мониторинга.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
import re
import webbrowser

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skylots_ai.models import Lot
from skylots_ai.profiles import SearchProfile


@dataclass
class ConsoleProfileState:
    profile_id: str
    name: str
    url: str = "-"
    enabled: bool = True
    interval: int = 30
    max_price: int = 20
    status: str = "ОЖИДАНИЕ"
    fetched: int = 0
    new_lots: int = 0
    last_scan: str = "-"


@dataclass
class ConsoleLotState:
    lot_id: str
    time: str
    title: str
    price: int
    seller: str
    remaining_time: str
    bids: str
    url: str


@dataclass
class ConsoleEndingLotState:
    lot_id: str
    profile_id: str
    profile_name: str
    title: str
    price: int
    seller: str
    remaining_time: str
    bids: str
    url: str


class ConsoleNotifier:
    """
    Rich dashboard для долгого мониторинга в терминале.
    """

    MAX_LOTS = 10
    MAX_ENDING_LOTS = 10
    MAX_EVENTS = 5

    def __init__(self, live_enabled: bool = True) -> None:
        self.console = Console()
        self.live_enabled = live_enabled
        self.live: Live | None = None
        self.status = "ЗАПУСК"
        self.countdown = 0
        self.profiles_loaded = 0
        self.database_lots_count = 0
        self.profiles: dict[str, ConsoleProfileState] = {}
        self.latest_lots: list[ConsoleLotState] = []
        self.ending_lots: dict[str, list[ConsoleEndingLotState]] = {}
        self.selected_hot_index = 0
        self.events: list[str] = []
        self.monitor_mode = "multi"
        self.active_profile_id = ""
        self.total_fetched = 0
        self.total_new_lots = 0
        self.total_existing_lots = 0
        self.new_today = 0
        self.total_today = 0
        self.today = date.today()
        self.system_statuses: dict[str, bool] = {
            "Internet": True,
            "Cookies": True,
            "Parser": True,
            "SQLite": True,
            "Profiles": True,
        }

    def start(
        self,
        profiles: list[str],
        database_lots_count: int,
        status: str = "РАБОТАЕТ",
        profile_urls: dict[str, str] | None = None,
    ) -> None:
        self.status = self._translate_status(status)
        self.profiles_loaded = len(profiles)
        self.database_lots_count = database_lots_count
        self.profiles = {
            name: ConsoleProfileState(
                profile_id=name,
                name=name,
                url=(profile_urls or {}).get(name, "-"),
            )
            for name in profiles
        }
        self.add_event("Skylots AI Assistant запущен")

        if self.live_enabled and self.live is None:
            self.live = Live(
                self.render(),
                console=self.console,
                refresh_per_second=1,
                screen=True,
            )
            self.live.start()
        self.refresh()

    def stop(self) -> None:
        if self.live is not None:
            self.live.stop()
            self.live = None

    def set_status(self, status: str) -> None:
        self.status = self._translate_status(status)
        profile_name = self._extract_scanning_profile(status)

        if profile_name:
            self._set_profiles_status("ОЖИДАНИЕ")
            self._set_profile_status(profile_name, "СКАНИРОВАНИЕ")
            self.add_event(f"Сканирование профиля: {profile_name}")

        self.refresh()

    def set_countdown(self, seconds: int) -> None:
        self.countdown = seconds
        self.status = "ОЖИДАНИЕ"
        self._set_profiles_status("ОЖИДАНИЕ")
        self.refresh()

    def update_database_lots_count(self, count: int) -> None:
        self.database_lots_count = count
        self.refresh()

    def set_system_status(self, name: str, ok: bool) -> None:
        self.system_statuses[name] = ok
        self.refresh()

    def set_profiles(
        self,
        profiles: Sequence[SearchProfile],
        monitor_mode: str = "multi",
        active_profile_id: str = "",
        profile_max_prices: dict[str, int] | None = None,
    ) -> None:
        existing = self.profiles
        self.monitor_mode = monitor_mode
        self.active_profile_id = active_profile_id
        self.profiles_loaded = len(profiles)
        self.profiles = {}
        for profile in profiles:
            current = existing.get(profile.id)
            self.profiles[profile.id] = ConsoleProfileState(
                profile_id=profile.id,
                name=profile.name,
                url=profile.url,
                enabled=profile.enabled,
                interval=profile.interval,
                max_price=(profile_max_prices or {}).get(profile.id, 20),
                status=current.status if current else "ОЖИДАНИЕ",
                fetched=current.fetched if current else 0,
                new_lots=current.new_lots if current else 0,
                last_scan=current.last_scan if current else "-",
            )
        known_profile_ids = {profile.id for profile in profiles}
        self.ending_lots = {
            profile_id: lots
            for profile_id, lots in self.ending_lots.items()
            if profile_id in known_profile_ids
        }
        self.refresh()

    def select_hot_lot(self, step: int) -> None:
        hot_lots = self._hot_lots()
        if not hot_lots:
            self.selected_hot_index = 0
            self.refresh()
            return

        self.selected_hot_index = (
            self.selected_hot_index + step
        ) % len(hot_lots)
        self.refresh()

    def open_selected_hot_lot(self) -> None:
        hot_lots = self._hot_lots()
        if not hot_lots:
            self.add_event("HOT LOTS пуст")
            return

        selected_lot = hot_lots[self.selected_hot_index]
        if not selected_lot.url or selected_lot.url == "-":
            self.add_event("У выбранного лота нет ссылки")
            return

        webbrowser.open(selected_lot.url)
        self.add_event(f"Открыт лот: {selected_lot.lot_id}")

    def resume(self) -> None:
        if self.live_enabled and self.live is None:
            self.live = Live(
                self.render(),
                console=self.console,
                refresh_per_second=1,
                screen=True,
            )
            self.live.start()
        self.refresh()

    def prompt_new_profile(self, default_interval: int = 30) -> tuple[str, str, int]:
        self.stop()
        self.console.print("[bold cyan]Добавление профиля[/]")
        name = input("Введите название профиля: ").strip()
        url = input("Вставьте ссылку Skylots: ").strip()
        interval_text = input(
            f"Интервал проверки, сек [{default_interval}]: ",
        ).strip()

        interval = default_interval
        if interval_text:
            try:
                interval = int(interval_text)
            except ValueError:
                interval = default_interval

        return name, url, interval

    def prompt_profile_interval(self, profile_name: str) -> int | None:
        self.stop()
        self.console.print(
            f"[bold cyan]Интервал профиля: {profile_name}[/]",
        )
        interval_text = input(
            "Новый интервал проверки в секундах: ",
        ).strip()
        try:
            return int(interval_text)
        except ValueError:
            return None

    def show_profile_list(self, profiles: Sequence[SearchProfile]) -> None:
        self.stop()
        table = Table(title="Список профилей", box=None)
        table.add_column("Статус")
        table.add_column("Название")
        table.add_column("Интервал", justify="right")
        table.add_column("URL")

        for profile in profiles:
            status = "Включён" if profile.enabled else "Выключен"
            table.add_row(
                status,
                profile.name,
                str(profile.interval),
                profile.url,
            )

        self.console.print(table)
        input("Нажмите Enter, чтобы вернуться к dashboard...")

    def print_summary(
        self,
        profile_name: str,
        fetched: int,
        new_lots: int,
    ) -> None:
        self._reset_today_if_needed()
        profile = self._find_profile_state(profile_name)
        if profile is None:
            profile = ConsoleProfileState(
                profile_id=profile_name,
                name=profile_name,
            )
            self.profiles[profile.profile_id] = profile
        profile.status = "РАБОТАЕТ"
        profile.fetched = fetched
        profile.new_lots = new_lots
        profile.last_scan = datetime.now().strftime("%H:%M:%S")

        existing_lots = max(fetched - new_lots, 0)
        self.total_fetched += fetched
        self.total_new_lots += new_lots
        self.total_existing_lots += existing_lots
        self.total_today += fetched
        self.new_today += new_lots
        self.add_event(f"{profile_name}: получено лотов {fetched}")
        if new_lots:
            self.add_event(f"{profile_name}: новых лотов {new_lots}")
        else:
            self.add_event(f"{profile_name}: новых лотов нет")
        self.refresh()

    def print_new_lot(self, lot: Lot) -> None:
        bids = "-" if lot.bids_count is None else str(lot.bids_count)
        self.latest_lots.insert(
            0,
            ConsoleLotState(
                lot_id=lot.id,
                time=datetime.now().strftime("%H:%M:%S"),
                title=lot.title or "-",
                price=lot.price,
                seller=lot.seller or "-",
                remaining_time=lot.remaining_time_text or lot.end_time or "-",
                bids=bids,
                url=lot.url or "-",
            ),
        )
        self.latest_lots = self.latest_lots[:self.MAX_LOTS]
        self.latest_lots.sort(key=self._lot_sort_key)
        self.add_event(f"Новый лот: {lot.title}")
        self.refresh()

    def update_ending_lots(self, profile_name: str, lots: Sequence[Lot]) -> None:
        profile = self._find_profile_state(profile_name)
        if profile is None:
            return

        ending_lots: list[ConsoleEndingLotState] = []
        for lot in lots:
            bids = "-" if lot.bids_count is None else str(lot.bids_count)
            ending_lots.append(
                ConsoleEndingLotState(
                    lot_id=lot.id,
                    profile_id=profile.profile_id,
                    profile_name=profile.name,
                    title=lot.title or "-",
                    price=lot.price,
                    seller=lot.seller or "-",
                    remaining_time=lot.remaining_time_text or lot.end_time or "-",
                    bids=bids,
                    url=lot.url or "-",
                ),
            )

        self.ending_lots[profile.profile_id] = sorted(
            ending_lots,
            key=self._ending_lot_sort_key,
        )
        self.refresh()

    def print_status(
        self,
        title: str,
        lines: Sequence[str] | None = None,
    ) -> None:
        details = " ".join(lines or [])
        self.status = self._translate_status(f"{title} {details}".strip())
        self.add_event(self.status)
        self.refresh()

    def print_once_summary(self, summaries: Sequence[object]) -> None:
        table = Table(title="Итоги сканирования", box=None)
        table.add_column("Профиль", style="bold")
        table.add_column("Получено", justify="right", style="cyan")
        table.add_column("Новых", justify="right", style="green")
        table.add_column("Известных", justify="right", style="yellow")

        total_fetched = 0
        total_new = 0
        total_existing = 0
        for summary in summaries:
            fetched = int(getattr(summary, "fetched", 0))
            new_lots = int(getattr(summary, "new_lots", 0))
            existing = int(getattr(summary, "existing_lots", 0))
            total_fetched += fetched
            total_new += new_lots
            total_existing += existing
            table.add_row(
                str(getattr(summary, "profile_name", "-")),
                str(fetched),
                str(new_lots),
                str(existing),
            )

        self.console.print(Panel.fit("Skylots AI Assistant", style="bold cyan"))
        self.console.print(table)
        self.console.print(
            f"[cyan]Всего получено:[/] {total_fetched}  "
            f"[green]Новых:[/] {total_new}  "
            f"[yellow]Известных:[/] {total_existing}",
        )
        if total_new == 0:
            self.console.print("[green]Новых лотов нет[/]")

    def refresh(self) -> None:
        if self.live is not None:
            self.live.update(self.render())

    def render(self) -> Panel:
        return Panel(
            Group(
                self._hot_lots_table(),
                self._ending_lots_table(),
                self._profiles_table(),
                self._stats_line(),
                self._events_panel(),
                self._status_bar(),
            ),
            title=(
                "[bold cyan]Skylots AI Assistant[/] "
                "[bold]Auction Workstation[/]"
            ),
            border_style="bright_blue",
        )

    def _header_table(self) -> Table:
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_row(
            self._metric("Статус", self.status, self._status_style(self.status)),
            self._metric("Режим", self._mode_label(), "cyan"),
            self._metric("Активный", self._active_profile_name(), "cyan"),
            self._metric(
                "Время",
                datetime.now().strftime("%H:%M:%S"),
                "cyan",
            ),
            self._metric(
                "До скана",
                f"{self.countdown} сек",
                "cyan",
            ),
            self._metric("Профилей", str(self.profiles_loaded), "cyan"),
            self._metric(
                "Лотов в базе",
                str(self.database_lots_count),
                "cyan",
            ),
        )
        return Panel(table, title="ОБЗОР", border_style="blue")

    def _system_status_line(self) -> Panel:
        labels = []
        for name in ("Internet", "Cookies", "Parser", "SQLite", "Profiles"):
            ok = self.system_statuses.get(name, False)
            style = "green" if ok else "red"
            value = "OK" if ok else "Error"
            labels.append(f"[{style}]{name}: {value}[/]")
        return Panel("   ".join(labels), border_style="bright_black")

    def _profiles_table(self) -> Panel:
        lines = [
            f"Режим: {self._mode_label()} | Активный профиль: {self._active_profile_name()}",
            (
                f"{'':<1} "
                f"{'Вкл':<3} "
                f"{'Профиль':<18} "
                f"{'Режим':<7} "
                f"{'Инт':>5} "
                f"{'Получ':>6} "
                f"{'Нов':>4} "
                f"{'Скан':>8}"
            )
        ]

        if not self.profiles:
            lines.append(
                "Профили не найдены. "
                "Нажмите A чтобы добавить профиль.",
            )

        for profile in self.profiles.values():
            marker = "*" if profile.profile_id == self.active_profile_id else " "
            enabled = "✓" if profile.enabled else "✗"
            mode_status = self._profile_mode_status(profile)
            lines.append(
                f"{marker:<1} "
                f"{enabled:<3} "
                f"{self._trim(profile.name, 18):<18} "
                f"{mode_status:<7} "
                f"{profile.interval:>4}s "
                f"{profile.fetched:>6} "
                f"{profile.new_lots:>4} "
                f"{profile.last_scan:>8}"
            )

        return Panel(
            Text("\n".join(lines)),
            title="ПРОФИЛИ",
            border_style="blue",
        )

    def _lots_table(self) -> Panel:
        table = Table(expand=True, padding=(0, 1), box=None)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("До", style="bold", no_wrap=True)
        table.add_column("Цена", justify="right", style="cyan", no_wrap=True)
        table.add_column("Название", overflow="ellipsis", no_wrap=True)
        table.add_column("Продавец", overflow="ellipsis", no_wrap=True)
        table.add_column("Ст", justify="right")
        table.add_column("URL", no_wrap=True)

        if not self.latest_lots:
            table.add_row("-", "-", "-", "Новых лотов нет", "-", "-", "-")
        for lot in sorted(self.latest_lots, key=self._lot_sort_key):
            remaining_style = self._remaining_style(lot.remaining_time)
            table.add_row(
                lot.lot_id,
                Text(self._short_remaining(lot.remaining_time), style=remaining_style),
                str(lot.price),
                self._trim(lot.title, 42),
                self._trim(lot.seller, 16),
                lot.bids,
                Text("Открыть", style=f"link {lot.url} cyan"),
            )

        return Panel(table, title="НОВЫЕ ЛОТЫ", border_style="green")

    def _hot_lots_table(self) -> Panel:
        table = Table(expand=True, padding=(0, 1), box=None)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Осталось", style="bold", no_wrap=True)
        table.add_column("Цена", justify="right", no_wrap=True)
        table.add_column("Ставок", justify="right")
        table.add_column("Название", overflow="ellipsis", no_wrap=True)
        table.add_column("Продавец", overflow="ellipsis", no_wrap=True)
        table.add_column("Профиль", overflow="ellipsis", no_wrap=True)

        hot_lots = self._hot_lots()
        if self.selected_hot_index >= len(hot_lots):
            self.selected_hot_index = 0

        if not hot_lots:
            table.add_row("-", "-", "-", "-", "Подходящих лотов нет", "-", "-")

        for index, lot in enumerate(hot_lots):
            selected = index == self.selected_hot_index
            row_style = "reverse" if selected else None
            table.add_row(
                lot.lot_id,
                Text(
                    self._short_remaining(lot.remaining_time),
                    style=self._ending_remaining_style(lot.remaining_time),
                ),
                self._price_text(lot.price),
                self._bids_text(lot.bids),
                self._trim(lot.title, 34),
                self._trim(lot.seller, 14),
                self._trim(lot.profile_name, 14),
                style=row_style,
            )

        return Panel(table, title="🔥 HOT LOTS", border_style="red")

    def _ending_lots_table(self) -> Panel:
        table = Table(expand=True, padding=(0, 1), box=None)
        table.add_column("Осталось", style="bold", no_wrap=True)
        table.add_column("Цена", justify="right", style="cyan", no_wrap=True)
        table.add_column("Ставок", justify="right")
        table.add_column("Название", overflow="ellipsis", no_wrap=True)
        table.add_column("Продавец", overflow="ellipsis", no_wrap=True)
        table.add_column("Профиль", overflow="ellipsis", no_wrap=True)

        ending_lots = self._visible_ending_lots()
        if not ending_lots:
            table.add_row("-", "-", "-", "Лотов нет", "-", "-")

        for lot in ending_lots:
            remaining_style = self._ending_remaining_style(lot.remaining_time)
            table.add_row(
                Text(self._short_remaining(lot.remaining_time), style=remaining_style),
                self._price_text(lot.price),
                self._bids_text(lot.bids),
                self._trim(lot.title, 34),
                self._trim(lot.seller, 14),
                self._trim(lot.profile_name, 14),
            )

        return Panel(
            table,
            title="⏳ ENDING SOON",
            border_style="yellow",
        )

    def _stats_line(self) -> Panel:
        stats = Text()
        stats.append(f"Получ {self.total_fetched}", style="cyan")
        stats.append("  |  ")
        stats.append(f"Нов {self.total_new_lots}", style="green")
        stats.append("  |  ")
        stats.append(f"База {self.database_lots_count}", style="cyan")
        stats.append("  |  ")
        stats.append(f"Сегодня {self.new_today}", style="green")
        return Panel(
            Align.center(stats),
            title="СТАТИСТИКА",
            border_style="magenta",
        )

    def _events_panel(self) -> Panel:
        if not self.events:
            content = Text("Событий пока нет", style="dim")
        else:
            content = Text("\n".join(self.events[:self.MAX_EVENTS]))
        return Panel(
            content,
            title="ПОСЛЕДНИЕ СОБЫТИЯ",
            border_style="yellow",
        )

    def _status_bar(self) -> Panel:
        text = (
            f"[bold]{self.status}[/] | "
            f"[cyan]{self.countdown} сек[/] | "
            "↑/↓ HOT | ENTER открыть | A профиль | E вкл/выкл | "
            "M режим | N/P профиль | I инт. | S скан | R обновить | "
            "L список | Q"
        )
        return Panel(text, border_style=self._status_style(self.status))

    def add_event(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.insert(0, f"[{timestamp}] {message}")
        self.events = self.events[:self.MAX_EVENTS]

    def _set_profiles_status(self, status: str) -> None:
        for profile in self.profiles.values():
            profile.status = status

    def _set_profile_status(self, profile_name: str, status: str) -> None:
        profile = self._find_profile_state(profile_name)
        if profile is not None:
            profile.status = status

    def _find_profile_state(self, profile_name: str) -> ConsoleProfileState | None:
        for profile in self.profiles.values():
            if profile.name == profile_name:
                return profile
        return None

    def _reset_today_if_needed(self) -> None:
        current_day = date.today()
        if current_day != self.today:
            self.today = current_day
            self.new_today = 0
            self.total_today = 0

    def _last_scan(self) -> str:
        scans = [
            profile.last_scan
            for profile in self.profiles.values()
            if profile.last_scan != "-"
        ]
        return max(scans) if scans else "-"

    @staticmethod
    def _metric(label: str, value: str, style: str) -> Text:
        text = Text()
        text.append(f"{label}\n", style="dim")
        text.append(value, style=f"bold {style}")
        return text

    def _mode_label(self) -> str:
        if self.monitor_mode == "multi":
            return "Все профили"
        return "Один профиль"

    def _active_profile_name(self) -> str:
        profile = self.profiles.get(self.active_profile_id)
        if profile is None:
            return "-"
        return self._trim(profile.name, 18)

    def _profile_mode_status(self, profile: ConsoleProfileState) -> str:
        if self.monitor_mode == "multi":
            return "все" if profile.enabled else "выкл"
        if profile.profile_id == self.active_profile_id:
            return "актив"
        return "-"

    @staticmethod
    def _translate_status(status: str) -> str:
        normalized = status.lower()
        if "scanning profile:" in normalized:
            profile = status.split(":", 1)[1].replace("...", "").strip()
            return f"СКАНИРОВАНИЕ: {profile}"
        if "waiting" in normalized:
            return "ОЖИДАНИЕ"
        if "stopping" in normalized or "good bye" in normalized:
            return "ОСТАНОВКА"
        if "error" in normalized:
            return "ОШИБКА"
        if "running" in normalized:
            return "РАБОТАЕТ"
        if "starting" in normalized:
            return "ЗАПУСК"
        return status

    @staticmethod
    def _extract_scanning_profile(status: str) -> str | None:
        if "Scanning profile:" not in status:
            return None
        return status.split(":", 1)[1].replace("...", "").strip()

    @staticmethod
    def _status_style(status: str) -> str:
        if "ОШИБКА" in status:
            return "red"
        if "СКАНИРОВАНИЕ" in status:
            return "yellow"
        if "ОЖИДАНИЕ" in status:
            return "cyan"
        if "ОСТАНОВКА" in status:
            return "yellow"
        return "green"

    @staticmethod
    def _remaining_style(value: str) -> str:
        seconds = ConsoleNotifier.parse_remaining_seconds(value)
        if seconds is None or seconds > 600:
            return "green"
        if seconds >= 300:
            return "yellow"
        if seconds >= 120:
            return "orange1"
        return "red"

    @staticmethod
    def _ending_remaining_style(value: str) -> str:
        seconds = ConsoleNotifier.parse_remaining_seconds(value)
        if seconds is None or seconds > 600:
            return "green"
        if seconds >= 120:
            return "yellow"
        return "red"

    @staticmethod
    def _extract_minutes(value: str) -> int | None:
        hours_match = re.search(r"(\d+)\s*(?:ч|h)", value, re.IGNORECASE)
        minutes_match = re.search(
            r"(\d+)\s*(?:мин|min|m)",
            value,
            re.IGNORECASE,
        )

        minutes = 0
        if hours_match:
            minutes += int(hours_match.group(1)) * 60
        if minutes_match:
            minutes += int(minutes_match.group(1))
        if hours_match or minutes_match:
            return minutes
        return None

    @staticmethod
    def _lot_sort_key(lot: ConsoleLotState) -> tuple[int, str]:
        minutes = ConsoleNotifier._extract_minutes(lot.remaining_time)
        if minutes is None:
            minutes = 10_000
        return minutes, lot.time

    @staticmethod
    def _ending_lot_sort_key(lot: ConsoleEndingLotState) -> tuple[int, str]:
        seconds = ConsoleNotifier.parse_remaining_seconds(lot.remaining_time)
        if seconds is None:
            seconds = 10_000_000
        return seconds, lot.title

    def _hot_lots(self) -> list[ConsoleEndingLotState]:
        hot_lots = []
        for lot in self._visible_ending_lots(limit=None):
            profile = self.profiles.get(lot.profile_id)
            if profile is None:
                continue
            if lot.price <= profile.max_price:
                hot_lots.append(lot)

        return sorted(hot_lots, key=self._hot_lot_sort_key)[:self.MAX_LOTS]

    @staticmethod
    def _hot_lot_sort_key(lot: ConsoleEndingLotState) -> tuple[int, int, str]:
        seconds = ConsoleNotifier.parse_remaining_seconds(lot.remaining_time)
        if seconds is None:
            seconds = 10_000_000
        return seconds, lot.price, lot.title

    def _visible_ending_lots(
        self,
        limit: int | None = MAX_ENDING_LOTS,
    ) -> list[ConsoleEndingLotState]:
        visible_profile_ids = self._visible_profile_ids()
        lots: list[ConsoleEndingLotState] = []
        for profile_id in visible_profile_ids:
            lots.extend(self.ending_lots.get(profile_id, []))

        sorted_lots = sorted(lots, key=self._ending_lot_sort_key)
        if limit is None:
            return sorted_lots
        return sorted_lots[:limit]

    def _visible_profile_ids(self) -> list[str]:
        if self.monitor_mode == "single":
            profile = self.profiles.get(self.active_profile_id)
            if profile is None or not profile.enabled:
                return []
            return [profile.profile_id]

        return [
            profile.profile_id
            for profile in self.profiles.values()
            if profile.enabled
        ]

    @staticmethod
    def _short_remaining(value: str) -> str:
        seconds = ConsoleNotifier.parse_remaining_seconds(value)
        if seconds is None:
            return ConsoleNotifier._trim(value, 14)
        if seconds < 60:
            return f"{seconds}с"
        minutes = seconds // 60
        rest_seconds = seconds % 60
        if minutes >= 60:
            hours = minutes // 60
            rest = minutes % 60
            if rest:
                return f"{hours}ч{rest}м"
            return f"{hours}ч"
        if minutes < 10 and rest_seconds:
            return f"{minutes}м{rest_seconds}с"
        return f"{minutes}м"

    @staticmethod
    def _price_text(price: int) -> Text:
        value = f"{price} грн"
        if price <= 10:
            return Text(value, style="bright_green")
        if price <= 50:
            return Text(value, style="yellow")
        return Text(value)

    @staticmethod
    def _bids_text(bids: str) -> Text:
        if bids == "0":
            return Text(bids, style="bright_green")
        return Text(bids)

    @staticmethod
    def parse_remaining_seconds(value: str) -> int | None:
        normalized = value.lower()
        hours_match = re.search(r"(\d+)\s*(?:ч|h)", normalized)
        minutes_match = re.search(r"(\d+)\s*(?:мин|min|m)", normalized)
        seconds_match = re.search(r"(\d+)\s*(?:сек|sec|s)", normalized)
        clock_match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", normalized)

        if clock_match:
            first = int(clock_match.group(1))
            second = int(clock_match.group(2))
            third = clock_match.group(3)
            if third is not None:
                return first * 3600 + second * 60 + int(third)
            return first * 60 + second

        seconds = 0
        if hours_match:
            seconds += int(hours_match.group(1)) * 3600
        if minutes_match:
            seconds += int(minutes_match.group(1)) * 60
        if seconds_match:
            seconds += int(seconds_match.group(1))
        if hours_match or minutes_match or seconds_match:
            return seconds
        return None

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit - 1]}…"

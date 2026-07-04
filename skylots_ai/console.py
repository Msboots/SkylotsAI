"""
Консольный dashboard мониторинга.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
import re

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from skylots_ai.models import Lot


@dataclass
class ConsoleProfileState:
    name: str
    url: str = "-"
    status: str = "ОЖИДАНИЕ"
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
    bids: str
    url: str


class ConsoleNotifier:
    """
    Rich dashboard для долгого мониторинга в терминале.
    """

    MAX_LOTS = 10
    MAX_EVENTS = 8

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
        self.events: list[str] = []
        self.total_fetched = 0
        self.total_new_lots = 0
        self.total_existing_lots = 0
        self.new_today = 0
        self.total_today = 0
        self.today = date.today()

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

    def print_summary(
        self,
        profile_name: str,
        fetched: int,
        new_lots: int,
    ) -> None:
        self._reset_today_if_needed()
        profile = self.profiles.setdefault(
            profile_name,
            ConsoleProfileState(name=profile_name),
        )
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
        self.latest_lots.insert(
            0,
            ConsoleLotState(
                time=datetime.now().strftime("%H:%M:%S"),
                title=lot.title or "-",
                price=lot.price,
                seller=lot.seller or "-",
                remaining_time=lot.end_time or "-",
                bids="-",
                url=lot.url or "-",
            ),
        )
        self.latest_lots = self.latest_lots[:self.MAX_LOTS]
        self.add_event(f"Новый лот: {lot.title}")
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
                self._header_table(),
                self._profiles_table(),
                self._lots_table(),
                self._stats_and_events_table(),
                self._controls_panel(),
                self._status_bar(),
            ),
            title="[bold cyan]Skylots AI Assistant[/]",
            border_style="bright_blue",
        )

    def _header_table(self) -> Table:
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_row(
            self._metric("Статус", self.status, self._status_style(self.status)),
            self._metric(
                "Текущее время",
                datetime.now().strftime("%H:%M:%S"),
                "cyan",
            ),
            self._metric(
                "До следующего скана",
                f"{self.countdown} сек",
                "cyan",
            ),
            self._metric("Профилей", str(self.profiles_loaded), "cyan"),
        )
        table.add_row(
            self._metric(
                "Лотов в базе",
                str(self.database_lots_count),
                "cyan",
            ),
            self._metric("Последний скан", self._last_scan(), "cyan"),
            "",
            "",
        )
        return Panel(table, title="ОБЗОР", border_style="blue")

    def _profiles_table(self) -> Panel:
        table = Table(expand=True)
        table.add_column("Статус", style="bold")
        table.add_column("Название профиля", style="bold")
        table.add_column("URL / Ключевые слова", overflow="fold")
        table.add_column("Получено", justify="right", style="cyan")
        table.add_column("Новых", justify="right", style="green")
        table.add_column("Последний скан", justify="right", style="cyan")

        if not self.profiles:
            table.add_row(
                "-",
                "Профили не загружены",
                "-",
                "0",
                "0",
                "-",
            )
        for profile in self.profiles.values():
            table.add_row(
                Text(profile.status, style=self._status_style(profile.status)),
                profile.name,
                profile.url,
                str(profile.fetched),
                str(profile.new_lots),
                profile.last_scan,
            )

        return Panel(table, title="ПРОФИЛИ", border_style="blue")

    def _lots_table(self) -> Panel:
        table = Table(expand=True)
        table.add_column("До конца", style="bold")
        table.add_column("Осталось", style="bold")
        table.add_column("Цена", justify="right", style="cyan")
        table.add_column("Название лота", overflow="fold")
        table.add_column("Продавец")
        table.add_column("Ставки", justify="right")
        table.add_column("Ссылка", overflow="fold")

        if not self.latest_lots:
            table.add_row("-", "-", "-", "Новых лотов нет", "-", "-", "-")
        for lot in self.latest_lots:
            remaining_style = self._remaining_style(lot.remaining_time)
            table.add_row(
                Text(lot.remaining_time, style=remaining_style),
                Text(lot.time, style="cyan"),
                f"{lot.price} грн",
                lot.title,
                lot.seller,
                lot.bids,
                lot.url,
            )

        return Panel(table, title="НОВЫЕ ЛОТЫ", border_style="green")

    def _stats_and_events_table(self) -> Table:
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(self._stats_panel(), self._events_panel())
        return grid

    def _stats_panel(self) -> Panel:
        table = Table.grid(expand=True)
        table.add_column()
        table.add_column(justify="right")
        table.add_row(
            "Всего получено",
            Text(str(self.total_fetched), style="cyan"),
        )
        table.add_row(
            "Новых лотов",
            Text(str(self.total_new_lots), style="green"),
        )
        table.add_row(
            "Известных лотов",
            Text(str(self.total_existing_lots), style="yellow"),
        )
        table.add_row(
            "Новых сегодня",
            Text(str(self.new_today), style="green"),
        )
        table.add_row(
            "Всего сегодня",
            Text(str(self.total_today), style="cyan"),
        )
        return Panel(table, title="СТАТИСТИКА", border_style="magenta")

    def _events_panel(self) -> Panel:
        if not self.events:
            content = Text("Событий пока нет", style="dim")
        else:
            content = Text("\n".join(self.events[-self.MAX_EVENTS:]))
        return Panel(
            content,
            title="ПОСЛЕДНИЕ СОБЫТИЯ",
            border_style="yellow",
        )

    @staticmethod
    def _controls_panel() -> Panel:
        controls = (
            "S - Сканировать сейчас   "
            "R - Обновить профили   "
            "L - Список профилей   "
            "Q - Выход   "
            "CTRL+C - Выход"
        )
        return Panel(
            Align.center(controls),
            title="УПРАВЛЕНИЕ",
            border_style="cyan",
        )

    def _status_bar(self) -> Panel:
        text = (
            f"[bold]{self.status}[/]    "
            f"[cyan]До следующего скана: {self.countdown} сек[/]"
        )
        return Panel(text, border_style=self._status_style(self.status))

    def add_event(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.append(f"[{timestamp}] {message}")
        self.events = self.events[-self.MAX_EVENTS:]

    def _set_profiles_status(self, status: str) -> None:
        for profile in self.profiles.values():
            profile.status = status

    def _set_profile_status(self, profile_name: str, status: str) -> None:
        profile = self.profiles.get(profile_name)
        if profile is not None:
            profile.status = status

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
        minutes = ConsoleNotifier._extract_minutes(value)
        if minutes is None or minutes > 10:
            return "green"
        if minutes >= 2:
            return "yellow"
        return "red"

    @staticmethod
    def _extract_minutes(value: str) -> int | None:
        hours_match = re.search(r"(\d+)\s*ч", value)
        minutes_match = re.search(r"(\d+)\s*мин", value)

        minutes = 0
        if hours_match:
            minutes += int(hours_match.group(1)) * 60
        if minutes_match:
            minutes += int(minutes_match.group(1))
        if hours_match or minutes_match:
            return minutes
        return None

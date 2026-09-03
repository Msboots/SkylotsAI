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

from skylots_ai.models import Lot, PriceChange
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
    rating: float | None = None


class ConsoleNotifier:
    """
    Rich dashboard для долгого мониторинга в терминале.
    """

    MAX_LOTS = 10
    MAX_ENDING_LOTS = 10
    MAX_EVENTS = 7
    SORT_MODES = ("ending", "price", "title")
    LOT_PANELS = ("hot_lots", "ending_lots", "favorites")
    PANELS = (*LOT_PANELS, "events")

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
        self.active_panel = "hot_lots"
        self.workspace_panel = "hot_lots"
        self.profiles_expanded = False
        self.selected_lot_index = 0
        self.selected_event_index = 0
        self.events: list[str] = []
        self.monitor_mode = "multi"
        self.active_profile_id = ""
        self.total_fetched = 0
        self.total_new_lots = 0
        self.total_existing_lots = 0
        self.new_today = 0
        self.total_today = 0
        self.today = date.today()
        self.keyboard_debug = False
        self.last_key = "-"
        self.last_success = "-"
        self.favorite_urls: set[str] = set()
        self.favorites_only = False
        self.sort_mode = "ending"
        self.compact_mode = self.console.size.width < 120
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
        self.add_event("Skylots AI Assistant запущен", refresh=False)

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
            self.add_event(
                f"Сканирование профиля: {profile_name}",
                refresh=False,
            )

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

    def set_last_success(self, value: str) -> None:
        self.last_success = value
        self.refresh()

    def set_favorites(self, urls: set[str]) -> None:
        self.favorite_urls = set(urls)
        self._clamp_selection()
        self.refresh()

    def cycle_lot_sort(self) -> None:
        current_index = self.SORT_MODES.index(self.sort_mode)
        self.sort_mode = self.SORT_MODES[
            (current_index + 1) % len(self.SORT_MODES)
        ]
        self.selected_lot_index = 0
        self.add_event(f"Сортировка: {self._sort_mode_label()}")

    def toggle_favorites_filter(self) -> None:
        self.favorites_only = not self.favorites_only
        self.selected_lot_index = 0
        label = (
            "только избранные" if self.favorites_only else "все лоты"
        )
        self.add_event(f"Фильтр: {label}")

    def toggle_compact_mode(self) -> None:
        self.compact_mode = not self.compact_mode
        label = "включён" if self.compact_mode else "выключен"
        self.add_event(f"Компактный режим {label}")

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

    def select_next_panel(self) -> None:
        self._select_relative_panel(1)

    def select_previous_panel(self) -> None:
        self._select_relative_panel(-1)

    def _select_relative_panel(self, step: int) -> None:
        current_panel = (
            self.workspace_panel
            if self.active_panel == "profiles"
            else self.active_panel
        )
        current_index = self.PANELS.index(current_panel)
        panel = self.PANELS[
            (current_index + step) % len(self.PANELS)
        ]
        self.show_panel(panel)

    def show_panel(self, panel: str) -> None:
        if panel not in self.PANELS:
            return
        self.active_panel = panel
        self.profiles_expanded = False
        if panel in self.LOT_PANELS:
            self.workspace_panel = panel
            self.selected_lot_index = 0
        self._clamp_selection()
        self.refresh()

    def toggle_profiles_panel(self) -> None:
        self.profiles_expanded = not self.profiles_expanded
        self.active_panel = (
            "profiles" if self.profiles_expanded else self.workspace_panel
        )
        self._clamp_selection()
        self.refresh()

    def select_active_row(self, step: int) -> None:
        if self.active_panel in self.LOT_PANELS:
            lots = self._selectable_lots()
            if not lots:
                self.selected_lot_index = 0
                self.refresh()
                return
            self.selected_lot_index = (
                self.selected_lot_index + step
            ) % len(lots)
        elif self.active_panel == "profiles":
            self._select_profile_row(step)
        elif self.active_panel == "events":
            if not self.events:
                self.selected_event_index = 0
                self.refresh()
                return
            self.selected_event_index = (
                self.selected_event_index + step
            ) % min(len(self.events), self.MAX_EVENTS)

        self.refresh()

    def select_hot_lot(self, step: int) -> None:
        self.active_panel = "hot_lots"
        self.select_active_row(step)

    def open_selected_hot_lot(self) -> None:
        self.open_selected_lot()

    def open_selected_lot(self) -> None:
        selected_lot = self.selected_lot()
        if selected_lot is None:
            self.add_event("Лот не выбран", refresh=False)
            self.refresh()
            return

        webbrowser.open(selected_lot.url)
        self.add_event(
            f"Открыт лот: {selected_lot.lot_id}",
            refresh=False,
        )
        self.refresh()

    def selected_lot(self) -> ConsoleEndingLotState | None:
        if self.active_panel not in self.LOT_PANELS:
            return None
        lots = self._selectable_lots()
        if not lots:
            return None
        self.selected_lot_index = min(self.selected_lot_index, len(lots) - 1)
        return lots[self.selected_lot_index]

    def selected_profile_id(self) -> str | None:
        profiles = list(self.profiles.values())
        if not profiles:
            return None
        if self.active_profile_id not in self.profiles:
            return profiles[0].profile_id
        return self.active_profile_id

    def clear_events(self) -> None:
        self.events = []
        self.selected_event_index = 0
        self.refresh()

    def current_panel(self) -> str:
        return self.active_panel

    def set_keyboard_debug(self, enabled: bool, last_key: str) -> None:
        self.keyboard_debug = enabled
        self.last_key = last_key
        self.refresh()

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

    def prompt_confirm(self, message: str) -> bool:
        self.stop()
        answer = input(f"{message} [y/N]: ").strip().lower()
        return answer in {"y", "yes", "д", "да"}

    def prompt_profile_edit(
        self,
        profile_name: str,
        profile_url: str,
    ) -> tuple[str, str] | None:
        self.stop()
        self.console.print(
            f"[bold cyan]Редактирование профиля: {profile_name}[/]",
        )
        name = input(f"Новое название [{profile_name}]: ").strip()
        url = input(f"Новая ссылка [{profile_url}]: ").strip()

        next_name = name or profile_name
        next_url = url or profile_url
        if next_name == profile_name and next_url == profile_url:
            return None
        return next_name, next_url

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
        self.add_event(
            f"{profile_name}: получено лотов {fetched}",
            refresh=False,
        )
        if new_lots:
            self.add_event(
                f"{profile_name}: новых лотов {new_lots}",
                refresh=False,
            )
        else:
            self.add_event(
                f"{profile_name}: новых лотов нет",
                refresh=False,
            )
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
        self.add_event(f"Новый лот: {lot.title}", refresh=False)
        self.refresh()

    def print_price_change(self, change: PriceChange) -> None:
        direction = "↓" if change.decreased else "↑"
        label = "Цена снижена" if change.decreased else "Цена повышена"
        self.add_event(
            (
                f"{direction} {label}: {change.lot.title} "
                f"{change.previous_price} → {change.current_price} грн"
            ),
        )

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
                    rating=lot.rating,
                ),
            )

        self.ending_lots[profile.profile_id] = sorted(
            ending_lots,
            key=self._lot_view_sort_key,
        )
        self.refresh()

    def print_status(
        self,
        title: str,
        lines: Sequence[str] | None = None,
    ) -> None:
        details = " ".join(lines or [])
        self.status = self._translate_status(f"{title} {details}".strip())
        self.add_event(self.status, refresh=False)
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
        workspaces: list[Panel] = (
            [self._profiles_table()]
            if self.profiles_expanded
            else [
                self._hot_lots_table(),
                self._ending_lots_table(),
                self._favorites_table(),
            ]
        )
        return Panel(
            Group(
                self._header_table(),
                *workspaces,
                self._events_panel(),
                self._status_bar(),
            ),
            title="[bold cyan]Skylots AI Assistant[/] — [bold]Монитор аукционов[/]",
            border_style="bright_blue",
        )

    def _header_table(self) -> Table:
        table = Table.grid(expand=True)
        system_ok = sum(self.system_statuses.values())
        system_total = len(self.system_statuses)
        system_style = "green" if system_ok == system_total else "yellow"
        metrics = [
            self._metric("Статус", self.status, self._status_style(self.status)),
            self._metric("Режим", self._mode_label(), "cyan"),
            self._metric("Активный", self._active_profile_name(), "cyan"),
            self._metric(
                "До скана",
                f"{self.countdown} сек",
                "cyan",
            ),
            self._metric(
                "Новых сегодня",
                str(self.new_today),
                "green",
            ),
            self._metric(
                "Лотов в базе",
                str(self.database_lots_count),
                "cyan",
            ),
            self._metric(
                "Система",
                f"{system_ok}/{system_total}",
                system_style,
            ),
            self._metric("Успешный запрос", self.last_success, "green"),
        ]
        column_count = 4 if self.compact_mode else len(metrics)
        for _ in range(column_count):
            table.add_column(ratio=1)
        for start in range(0, len(metrics), column_count):
            row = metrics[start : start + column_count]
            row.extend(Text() for _ in range(column_count - len(row)))
            table.add_row(*row)
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
        table = Table(expand=True, padding=(0, 1), box=None)
        table.add_column("", no_wrap=True)
        table.add_column("Вкл", no_wrap=True)
        table.add_column("Профиль", overflow="ellipsis", no_wrap=True)
        table.add_column("Режим", no_wrap=True)
        table.add_column("Инт", justify="right", no_wrap=True)
        table.add_column("Получ", justify="right", no_wrap=True)
        table.add_column("Нов", justify="right", no_wrap=True)
        table.add_column("Скан", justify="right", no_wrap=True)

        if not self.profiles:
            table.add_row(
                "",
                "",
                "Профили не найдены. "
                "Нажмите A чтобы добавить профиль.",
                "",
                "",
                "",
                "",
                "",
            )

        for profile in self.profiles.values():
            marker = "*" if profile.profile_id == self.active_profile_id else " "
            enabled = "✓" if profile.enabled else "✗"
            mode_status = self._profile_mode_status(profile)
            row_style = (
                "reverse"
                if (
                    self.active_panel == "profiles"
                    and profile.profile_id == self.active_profile_id
                )
                else None
            )
            table.add_row(
                marker,
                enabled,
                self._trim(profile.name, 18),
                mode_status,
                f"{profile.interval}s",
                str(profile.fetched),
                str(profile.new_lots),
                profile.last_scan,
                style=row_style,
            )

        title = self._panel_title("profiles", "ПРОФИЛИ")
        subtitle = (
            f"Режим: {self._mode_label()} | "
            f"Активный профиль: {self._active_profile_name()}"
        )
        return Panel(
            Group(Text(subtitle), table),
            title=title,
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
        return self._lot_workspace_table(
            lots=self._hot_lots(),
            panel="hot_lots",
            title=f"🔥 HOT LOTS{self._lot_view_suffix()}",
            empty_message="Подходящих лотов нет",
            border_style="red",
        )

    def _ending_lots_table(self) -> Panel:
        return self._lot_workspace_table(
            lots=self._visible_ending_lots(),
            panel="ending_lots",
            title=f"⏳ ENDING SOON{self._lot_view_suffix()}",
            empty_message="Лотов нет",
            border_style="yellow",
        )

    def _favorites_table(self) -> Panel:
        return self._lot_workspace_table(
            lots=self._favorite_lots(),
            panel="favorites",
            title=f"★ ИЗБРАННОЕ{self._lot_view_suffix()}",
            empty_message="Избранных лотов нет",
            border_style="magenta",
        )

    def _workspace_table(self) -> Panel:
        tables = {
            "hot_lots": self._hot_lots_table,
            "ending_lots": self._ending_lots_table,
            "favorites": self._favorites_table,
        }
        return tables[self.workspace_panel]()

    def _lot_workspace_table(
        self,
        lots: Sequence[ConsoleEndingLotState],
        panel: str,
        title: str,
        empty_message: str,
        border_style: str,
    ) -> Panel:
        narrow = self.console.size.width < 100 or self.compact_mode
        table = Table(
            expand=True,
            padding=(0, 1),
            collapse_padding=True,
            box=None,
        )
        table.add_column("★", style="yellow", width=1, no_wrap=True)
        table.add_column(
            "До",
            style="bold",
            width=8,
            min_width=5,
            no_wrap=True,
        )
        table.add_column(
            "Цена",
            justify="right",
            width=10,
            min_width=7,
            no_wrap=True,
        )
        table.add_column(
            "Ст.",
            justify="right",
            width=5,
            min_width=3,
            no_wrap=True,
        )
        table.add_column(
            "Название",
            ratio=3,
            min_width=8,
            overflow="ellipsis",
            no_wrap=True,
        )
        table.add_column(
            "Продавец (★)",
            ratio=2,
            min_width=6,
            overflow="ellipsis",
            no_wrap=True,
        )
        table.add_column(
            "ID",
            style="cyan",
            width=10,
            min_width=6,
            no_wrap=True,
        )
        self._clamp_selection()

        if not lots:
            table.add_row("-", "-", "-", "-", empty_message, "-", "-")

        for index, lot in enumerate(lots):
            selected = (
                self.active_panel == panel
                and index == self.selected_lot_index
            )
            row_style = "reverse" if selected else None
            row: list[str | Text] = [
                self._favorite_marker(lot),
                Text(
                    self._short_remaining(lot.remaining_time),
                    style=self._ending_remaining_style(lot.remaining_time),
                ),
                self._price_text(lot.price),
                self._bids_text(lot.bids),
                self._trim(lot.title, 20 if narrow else 48),
                self._seller_rating_text(lot),
                lot.lot_id,
            ]
            table.add_row(*row, style=row_style)

        return Panel(
            table,
            title=self._panel_title(panel, title),
            border_style=border_style,
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
            content = Text(
                "• Событий пока нет. Новые сканирования и изменения "
                "появятся здесь.",
                style="dim",
            )
        else:
            content = Text()
            for index, event in enumerate(self.events[:self.MAX_EVENTS]):
                style = (
                    "reverse"
                    if (
                        self.active_panel == "events"
                        and index == self.selected_event_index
                    )
                    else ""
                )
                selected = (
                    self.active_panel == "events"
                    and index == self.selected_event_index
                )
                marker = "▶" if selected else " "
                content.append(
                    f"{marker} {self._event_icon(event)} {event}",
                    style=style,
                )
                if index < min(len(self.events), self.MAX_EVENTS) - 1:
                    content.append("\n")
        return Panel(
            content,
            title=self._panel_title(
                "events",
                "📋 СОБЫТИЯ · G фокус · K очистить",
            ),
            border_style=(
                "bright_yellow"
                if self.active_panel == "events"
                else "yellow"
            ),
        )

    def _status_bar(self) -> Panel:
        text = self._context_menu()
        return Panel(text, border_style=self._status_style(self.status))

    def add_event(self, message: str, refresh: bool = True) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.insert(0, f"[{timestamp}] {message}")
        self.events = self.events[:self.MAX_EVENTS]
        if refresh:
            self.refresh()

    def _context_menu(self) -> str:
        debug = self._keyboard_debug_text()
        if self.active_panel == "profiles":
            return (
                f"[bold]{self.status}[/]  [cyan]{self.countdown} сек[/]"
                "\n[bold cyan]ПРОФИЛИ[/]  "
                "P закрыть  ↑↓ выбрать  Enter изменить  "
                "A добавить  T вкл/выкл  I интервал  "
                f"D удалить  M режим  S сканировать  Q выход{debug}"
            )

        actions = (
            "K очистить  ↑↓ выбрать событие"
            if self.active_panel == "events"
            else (
                "↑↓ выбрать лот  Enter открыть  Z избранное  "
                "C ссылка  B блок продавца  O сортировка"
            )
        )
        return (
            f"[bold]{self.status}[/]  [cyan]{self.countdown} сек[/]  |  "
            "[bold cyan]РАЗДЕЛЫ[/]  H/Н HOT  E ENDING  "
            "F ИЗБРАННОЕ  P ПРОФИЛИ  G СОБЫТИЯ"
            f"\n[bold cyan]ДЕЙСТВИЯ[/]  {actions}  "
            f"S сканировать  Q выход{debug}"
        )

    @staticmethod
    def _event_icon(event: str) -> str:
        normalized = event.casefold()
        if "ошиб" in normalized or "error" in normalized:
            return "✖"
        if "сканирован" in normalized:
            return "↻"
        if "избран" in normalized:
            return "★"
        if "цен" in normalized:
            return "₴"
        if "нов" in normalized or "лот" in normalized:
            return "●"
        return "•"

    def _keyboard_debug_text(self) -> str:
        if not self.keyboard_debug:
            return ""
        return f" | [yellow]Клавиша: {self.last_key}[/]"

    def _has_active_item(self) -> bool:
        if self.active_panel in self.LOT_PANELS:
            return self.selected_lot() is not None
        if self.active_panel == "profiles":
            return self.selected_profile_id() is not None
        if self.active_panel == "events":
            return bool(self.events)
        return False

    def _panel_title(self, panel: str, title: str) -> str:
        if self.active_panel == panel:
            return f"▶ {title}"
        return title

    def _clamp_selection(self) -> None:
        lots = self._selectable_lots()
        if lots:
            self.selected_lot_index = min(self.selected_lot_index, len(lots) - 1)
        else:
            self.selected_lot_index = 0

        if self.events:
            self.selected_event_index = min(
                self.selected_event_index,
                min(len(self.events), self.MAX_EVENTS) - 1,
            )
        else:
            self.selected_event_index = 0

        if self.profiles and self.active_profile_id not in self.profiles:
            self.active_profile_id = next(iter(self.profiles))

    def _select_profile_row(self, step: int) -> None:
        profiles = list(self.profiles.values())
        if not profiles:
            self.active_profile_id = ""
            return

        profile_ids = [profile.profile_id for profile in profiles]
        try:
            current_index = profile_ids.index(self.active_profile_id)
        except ValueError:
            current_index = 0

        next_index = (current_index + step) % len(profile_ids)
        self.active_profile_id = profile_ids[next_index]

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

    def _hot_lots(self) -> list[ConsoleEndingLotState]:
        hot_lots = []
        for lot in self._visible_ending_lots(limit=None):
            profile = self.profiles.get(lot.profile_id)
            if profile is None:
                continue
            if lot.price <= profile.max_price:
                hot_lots.append(lot)

        return sorted(hot_lots, key=self._lot_view_sort_key)[:self.MAX_LOTS]

    def _selectable_lots(self) -> list[ConsoleEndingLotState]:
        if self.active_panel == "hot_lots":
            return self._hot_lots()
        if self.active_panel == "ending_lots":
            return self._visible_ending_lots()
        if self.active_panel == "favorites":
            return self._favorite_lots()
        return []

    def _favorite_lots(self) -> list[ConsoleEndingLotState]:
        lots_by_url: dict[str, ConsoleEndingLotState] = {}
        for profile_lots in self.ending_lots.values():
            for lot in profile_lots:
                if lot.url in self.favorite_urls:
                    lots_by_url[lot.url] = lot
        return sorted(lots_by_url.values(), key=self._lot_view_sort_key)[
            :self.MAX_ENDING_LOTS
        ]

    def _visible_ending_lots(
        self,
        limit: int | None = MAX_ENDING_LOTS,
    ) -> list[ConsoleEndingLotState]:
        visible_profile_ids = self._visible_profile_ids()
        lots: list[ConsoleEndingLotState] = []
        for profile_id in visible_profile_ids:
            lots.extend(self.ending_lots.get(profile_id, []))

        if self.favorites_only:
            lots = [lot for lot in lots if lot.url in self.favorite_urls]

        sorted_lots = sorted(lots, key=self._lot_view_sort_key)
        if limit is None:
            return sorted_lots
        return sorted_lots[:limit]

    def _lot_view_sort_key(
        self,
        lot: ConsoleEndingLotState,
    ) -> tuple[int, int, str]:
        seconds = self.parse_remaining_seconds(lot.remaining_time)
        if seconds is None:
            seconds = 10_000_000
        if self.sort_mode == "price":
            return lot.price, seconds, lot.title.casefold()
        if self.sort_mode == "title":
            return 0, 0, lot.title.casefold()
        return seconds, lot.price, lot.title.casefold()

    def _favorite_marker(self, lot: ConsoleEndingLotState) -> str:
        return "★" if lot.url in self.favorite_urls else ""

    def _seller_rating_text(self, lot: ConsoleEndingLotState) -> str:
        seller = self._trim(lot.seller, 18)
        if lot.rating is None:
            return seller
        rating = f"{lot.rating:g}"
        return f"{seller} ({rating})"

    def _hot_reason(self, lot: ConsoleEndingLotState) -> str:
        profile = self.profiles.get(lot.profile_id)
        if profile is None:
            return "-"
        return f"цена ≤ {profile.max_price} грн"

    def _lot_view_suffix(self) -> str:
        favorite_label = " · только ★" if self.favorites_only else ""
        compact_label = " · компактно" if self.compact_mode else ""
        return (
            f" · {self._sort_mode_label()}"
            f"{favorite_label}{compact_label}"
        )

    def _sort_mode_label(self) -> str:
        labels = {
            "ending": "по времени",
            "price": "по цене",
            "title": "по названию",
        }
        return labels[self.sort_mode]

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

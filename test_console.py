from io import StringIO
import unittest
from unittest.mock import Mock, patch

from rich.console import Console

from skylots_ai.console import (
    ConsoleEndingLotState,
    ConsoleNotifier,
    ConsoleProfileState,
)
from skylots_ai.models import Lot
from skylots_ai.monitor import Monitor


class ConsoleNotifierNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.notifier = ConsoleNotifier(live_enabled=False)
        self.notifier.profiles = {
            "hot": ConsoleProfileState(
                profile_id="hot",
                name="Hot",
                max_price=20,
            ),
        }
        self.cheap_lot = self._lot("cheap", 10)
        self.expensive_lot = self._lot("expensive", 100)
        self.notifier.ending_lots = {
            "hot": [self.cheap_lot, self.expensive_lot],
        }

    @staticmethod
    def _lot(lot_id: str, price: int) -> ConsoleEndingLotState:
        return ConsoleEndingLotState(
            lot_id=lot_id,
            profile_id="hot",
            profile_name="Hot",
            title=lot_id,
            price=price,
            seller="seller",
            remaining_time="5 мин",
            bids="0",
            url=f"https://example.test/{lot_id}",
        )

    def test_tab_visits_workspaces_without_opening_profiles(self) -> None:
        self.assertEqual(self.notifier.current_panel(), "hot_lots")

        self.notifier.select_next_panel()
        self.assertEqual(self.notifier.current_panel(), "ending_lots")

        self.notifier.select_next_panel()
        self.assertEqual(self.notifier.current_panel(), "favorites")
        self.assertFalse(self.notifier.profiles_expanded)

    def test_previous_panel_moves_backwards(self) -> None:
        self.notifier.select_previous_panel()

        self.assertEqual(self.notifier.current_panel(), "events")

    def test_each_lot_panel_uses_its_own_rows(self) -> None:
        self.assertIs(self.notifier.selected_lot(), self.cheap_lot)

        self.notifier.select_next_panel()
        self.notifier.select_active_row(1)

        self.assertIs(self.notifier.selected_lot(), self.expensive_lot)

    def test_non_lot_panel_has_no_selected_lot(self) -> None:
        self.notifier.active_panel = "profiles"

        self.assertIsNone(self.notifier.selected_lot())

    def test_summary_refreshes_dashboard_once(self) -> None:
        self.notifier.refresh = Mock()

        self.notifier.print_summary("Hot", fetched=48, new_lots=2)

        self.notifier.refresh.assert_called_once_with()

    def test_unchanged_fetched_count_is_not_repeated_in_events(self) -> None:
        self.notifier.print_summary("Hot", fetched=1000, new_lots=0)
        self.notifier.print_summary("Hot", fetched=1000, new_lots=0)

        fetched_events = [
            event for event in self.notifier.events if "лотов 1000" in event
        ]
        self.assertEqual(len(fetched_events), 1)

    def test_favorites_filter_keeps_only_starred_lots(self) -> None:
        self.notifier.set_favorites({self.expensive_lot.url})
        self.notifier.active_panel = "ending_lots"

        self.notifier.toggle_favorites_filter()

        self.assertIs(self.notifier.selected_lot(), self.expensive_lot)

    def test_sort_mode_changes_lot_order(self) -> None:
        low_price = self._lot("low-price", 5)
        low_price.remaining_time = "10 мин"
        ending_soon = self._lot("ending-soon", 100)
        ending_soon.remaining_time = "1 мин"
        self.notifier.ending_lots = {"hot": [low_price, ending_soon]}
        self.notifier.active_panel = "ending_lots"

        self.assertIs(self.notifier.selected_lot(), ending_soon)

        self.notifier.cycle_lot_sort()

        self.assertIs(self.notifier.selected_lot(), low_price)

    def test_update_ending_lots_uses_current_sorting(self) -> None:
        self.notifier.update_ending_lots(
            "Hot",
            [
                Lot(
                    id="later",
                    title="Later",
                    seller="seller",
                    price=5,
                    url="https://example.test/later",
                    remaining_time_text="10 мин",
                ),
                Lot(
                    id="sooner",
                    title="Sooner",
                    seller="seller",
                    price=10,
                    url="https://example.test/sooner",
                    remaining_time_text="1 мин",
                ),
            ],
        )

        lots = self.notifier.ending_lots["hot"]
        self.assertEqual([lot.lot_id for lot in lots], ["sooner", "later"])

    def test_lot_table_uses_requested_columns_without_profile(self) -> None:
        self.notifier.compact_mode = False
        self.cheap_lot.rating = 42.0
        self.notifier.set_favorites({self.cheap_lot.url})
        output = StringIO()
        console = Console(
            file=output,
            width=160,
            color_system=None,
        )

        console.print(self.notifier._hot_lots_table())
        rendered = output.getvalue()

        self.assertIn("★", rendered)
        self.assertIn("Продавец (★)", rendered)
        self.assertIn("seller (42)", rendered)
        self.assertNotIn("Профиль", rendered)
        self.assertNotIn("Почему HOT", rendered)

    def test_compact_table_keeps_requested_columns(self) -> None:
        self.notifier.compact_mode = True
        output = StringIO()
        console = Console(
            file=output,
            width=80,
            color_system=None,
        )

        console.print(self.notifier._ending_lots_table())
        rendered = output.getvalue()

        self.assertIn("Продавец", rendered)
        self.assertIn("Ст.", rendered)
        self.assertNotIn("Профиль", rendered)

    def test_favorites_workspace_contains_starred_lots(self) -> None:
        self.notifier.set_favorites({self.expensive_lot.url})
        self.notifier.show_panel("favorites")

        self.assertIs(self.notifier.selected_lot(), self.expensive_lot)

    def test_profiles_are_hidden_until_toggled(self) -> None:
        output = StringIO()
        console = Console(file=output, width=160, color_system=None)
        console.print(self.notifier.render())
        hidden_render = output.getvalue()

        self.notifier.toggle_profiles_panel()
        output = StringIO()
        console = Console(file=output, width=160, color_system=None)
        console.print(self.notifier.render())
        shown_render = output.getvalue()

        self.assertNotIn("Вкл", hidden_render)
        self.assertIn("Вкл", shown_render)
        self.assertIn("🔥 HOT LOTS", hidden_render)
        self.assertNotIn("🔥 HOT LOTS", shown_render)
        self.assertEqual(self.notifier.current_panel(), "profiles")

        self.notifier.toggle_profiles_panel()
        self.assertEqual(self.notifier.current_panel(), "hot_lots")

    def test_all_lot_workspaces_remain_visible_when_focus_changes(self) -> None:
        self.notifier.show_panel("favorites")
        output = StringIO()
        console = Console(file=output, width=160, color_system=None)
        console.print(self.notifier.render())
        rendered = output.getvalue()

        self.assertIn("HOT LOTS", rendered)
        self.assertIn("ENDING SOON", rendered)
        self.assertIn("ИЗБРАННОЕ", rendered)
        self.assertIn("▶ ★ ИЗБРАННОЕ", rendered)

    def test_narrow_layout_keeps_time_price_and_bids(self) -> None:
        output = StringIO()
        self.notifier.console = Console(
            file=output,
            width=58,
            color_system=None,
        )

        self.notifier.console.print(self.notifier._hot_lots_table())
        rendered = output.getvalue()

        self.assertIn("До", rendered)
        self.assertIn("Цена", rendered)
        self.assertIn("Ст.", rendered)
        self.assertIn("5м", rendered)
        self.assertIn("10 грн", rendered)

    def test_events_have_icons_and_clear_hint(self) -> None:
        self.notifier.add_event("Сканирование профиля: Hot")
        output = StringIO()
        console = Console(file=output, width=120, color_system=None)

        console.print(self.notifier._events_panel())
        rendered = output.getvalue()

        self.assertIn("↻", rendered)
        self.assertIn("G фокус", rendered)
        self.assertIn("K очистить", rendered)

    def test_event_types_have_intuitive_colors(self) -> None:
        self.assertIn("red", self.notifier._event_style("Ошибка сети"))
        self.assertIn("cyan", self.notifier._event_style("Сканирование"))
        self.assertIn("magenta", self.notifier._event_style("В избранное"))
        self.assertIn("yellow", self.notifier._event_style("Цена снижена"))
        self.assertIn("green", self.notifier._event_style("Новый лот"))

    def test_hotkey_help_is_split_into_sections(self) -> None:
        menu = self.notifier._context_menu()

        self.assertIn("РАЗДЕЛЫ", menu)
        self.assertIn("ДЕЙСТВИЯ", menu)
        self.assertIn("\n", menu)
        self.assertIn("[bold red]H/Н[/]", menu)
        self.assertIn("[bold yellow]E[/]", menu)
        self.assertIn("[bold magenta]F[/]", menu)
        self.assertIn("[bold blue]P[/]", menu)

    def test_new_lots_block_appears_between_favorites_and_events(self) -> None:
        self.notifier.print_new_lot(
            Lot(
                id="new-lot",
                title="New lot",
                seller="seller",
                price=15,
                url="https://example.test/new-lot",
                remaining_time_text="4 мин",
                bids_count=2,
                rating=99,
            ),
        )
        output = StringIO()
        console = Console(file=output, width=160, color_system=None)
        console.print(self.notifier.render())
        rendered = output.getvalue()

        favorites_index = rendered.index("ИЗБРАННОЕ")
        new_lots_index = rendered.index("НОВЫЕ ЛОТЫ")
        events_index = rendered.index("СОБЫТИЯ")
        self.assertLess(favorites_index, new_lots_index)
        self.assertLess(new_lots_index, events_index)

    def test_overview_uses_vertical_metric_pairs(self) -> None:
        output = StringIO()
        console = Console(file=output, width=120, color_system=None)
        console.print(self.notifier._header_table())
        lines = output.getvalue().splitlines()
        status_line = next(line for line in lines if "Статус" in line)
        scan_line = next(line for line in lines if "До скана" in line)
        mode_line = next(line for line in lines if "Режим" in line)
        active_line = next(line for line in lines if "Активный" in line)

        self.assertLessEqual(
            abs(status_line.index("Статус") - scan_line.index("До скана")),
            1,
        )
        self.assertLessEqual(
            abs(mode_line.index("Режим") - active_line.index("Активный")),
            1,
        )


class MonitorHotkeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.monitor = Monitor.__new__(Monitor)
        self.monitor.notifier = Mock()

    def test_left_moves_to_previous_panel(self) -> None:
        action = self.monitor._handle_hotkey("LEFT")

        self.assertEqual(action, "wait")
        self.monitor.notifier.select_previous_panel.assert_called_once_with()

    def test_enter_opens_lot_from_each_lot_panel(self) -> None:
        for panel in ("hot_lots", "ending_lots", "favorites"):
            with self.subTest(panel=panel):
                self.monitor.notifier.reset_mock()
                self.monitor.notifier.current_panel.return_value = panel

                action = self.monitor._handle_hotkey("ENTER")

                self.assertEqual(action, "wait")
                self.monitor.notifier.open_selected_lot.assert_called_once_with()

    def test_view_hotkeys_change_sort_filter_and_layout(self) -> None:
        actions = {
            "O": "cycle_lot_sort",
            "V": "toggle_favorites_filter",
            "X": "toggle_compact_mode",
        }

        for key, method_name in actions.items():
            with self.subTest(key=key):
                self.monitor.notifier.reset_mock()

                action = self.monitor._handle_hotkey(key)

                self.assertEqual(action, "wait")
                getattr(self.monitor.notifier, method_name).assert_called_once_with()

    def test_workspace_hotkeys_have_one_destination(self) -> None:
        destinations = {
            "H": "hot_lots",
            "Н": "hot_lots",
            "E": "ending_lots",
            "F": "favorites",
            "G": "events",
        }

        for key, panel in destinations.items():
            with self.subTest(key=key):
                self.monitor.notifier.reset_mock()

                action = self.monitor._handle_hotkey(key)

                self.assertEqual(action, "wait")
                self.monitor.notifier.show_panel.assert_called_once_with(panel)

    def test_profiles_hotkey_toggles_expanded_menu(self) -> None:
        action = self.monitor._handle_hotkey("P")

        self.assertEqual(action, "wait")
        self.monitor.notifier.toggle_profiles_panel.assert_called_once_with()

    def test_favorite_action_has_its_own_hotkey(self) -> None:
        self.monitor.notifier.current_panel.return_value = "hot_lots"

        with patch.object(self.monitor, "_favorite_selected_lot") as favorite:
            action = self.monitor._handle_hotkey("Z")

        self.assertEqual(action, "wait")
        favorite.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

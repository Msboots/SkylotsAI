import unittest
from unittest.mock import Mock

from skylots_ai.console import (
    ConsoleEndingLotState,
    ConsoleNotifier,
    ConsoleProfileState,
)
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

    def test_tab_visits_both_lot_panels(self) -> None:
        self.assertEqual(self.notifier.current_panel(), "hot_lots")

        self.notifier.select_next_panel()
        self.assertEqual(self.notifier.current_panel(), "ending_lots")

        self.notifier.select_next_panel()
        self.assertEqual(self.notifier.current_panel(), "profiles")

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


class MonitorHotkeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.monitor = Monitor.__new__(Monitor)
        self.monitor.notifier = Mock()

    def test_left_moves_to_previous_panel(self) -> None:
        action = self.monitor._handle_hotkey("LEFT")

        self.assertEqual(action, "wait")
        self.monitor.notifier.select_previous_panel.assert_called_once_with()

    def test_enter_opens_lot_from_each_lot_panel(self) -> None:
        for panel in ("hot_lots", "ending_lots"):
            with self.subTest(panel=panel):
                self.monitor.notifier.reset_mock()
                self.monitor.notifier.current_panel.return_value = panel

                action = self.monitor._handle_hotkey("ENTER")

                self.assertEqual(action, "wait")
                self.monitor.notifier.open_selected_lot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

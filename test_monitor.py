"""Тесты расписания мониторинга."""

import unittest
from unittest.mock import Mock, patch

from skylots_ai.models import Lot, PriceChange
from skylots_ai.monitor import Monitor
from skylots_ai.profiles import SearchProfile


class MonitorScheduleTests(unittest.TestCase):

    def setUp(self) -> None:
        self.monitor = Monitor.__new__(Monitor)
        self.monitor.monitor_mode = "multi"
        self.monitor.active_profile_id = ""
        self.monitor.config = Mock(check_interval=60)
        self.monitor.profile_manager = Mock()
        self.monitor._force_scan = False
        self.monitor._last_scan_times = {}
        self.profiles = [
            SearchProfile("new", "New", "https://example.test/new", interval=30),
            SearchProfile("due", "Due", "https://example.test/due", interval=30),
            SearchProfile("wait", "Wait", "https://example.test/wait", interval=30),
        ]
        self.monitor.profile_manager.get_enabled.return_value = self.profiles

    @patch("skylots_ai.monitor.time.monotonic", return_value=100.0)
    def test_profiles_to_scan_returns_only_due_profiles(self, _: Mock) -> None:
        self.monitor._last_scan_times = {"due": 60.0, "wait": 90.0}

        profiles = self.monitor._profiles_to_scan()

        self.assertEqual([profile.id for profile in profiles], ["new", "due"])

    @patch("skylots_ai.monitor.time.monotonic", return_value=100.0)
    def test_wait_uses_nearest_profile_deadline(self, _: Mock) -> None:
        self.monitor._last_scan_times = {
            "new": 85.0,
            "due": 90.0,
            "wait": 95.0,
        }

        self.assertEqual(self.monitor._current_wait_seconds(), 15)

    def test_manual_scan_forces_all_enabled_profiles(self) -> None:
        self.monitor._force_scan = True
        self.monitor._last_scan_times = {
            profile.id: 100.0 for profile in self.profiles
        }

        self.assertEqual(self.monitor._profiles_to_scan(), self.profiles)


class MonitorScanTests(unittest.TestCase):

    def setUp(self) -> None:
        self.monitor = Monitor.__new__(Monitor)
        self.monitor.logger = Mock()
        self.monitor.notifier = Mock()
        self.monitor.parser = Mock()
        self.monitor.database = Mock()
        self.profile = SearchProfile(
            "hot",
            "Hot",
            "https://example.test/hot",
        )
        self.lot = Lot(
            "1",
            "Discounted lot",
            "seller",
            15,
            "https://example.test/1",
        )

    def test_successful_scan_updates_last_success(self) -> None:
        self.monitor.parser.fetch.return_value = "<html></html>"
        self.monitor.parser.parse.return_value = [self.lot]
        self.monitor.database.sync_lots.return_value = ([], [], 1)

        summary = self.monitor._scan_profile(self.profile)

        self.assertEqual(summary.fetched, 1)
        self.monitor.notifier.set_last_success.assert_called_once()
        self.monitor.notifier.set_system_status.assert_any_call(
            "Internet",
            True,
        )

    def test_price_change_reaches_notifier(self) -> None:
        change = PriceChange(
            lot=self.lot,
            previous_price=25,
            current_price=15,
        )
        self.monitor.parser.fetch.return_value = "<html></html>"
        self.monitor.parser.parse.return_value = [self.lot]
        self.monitor.database.sync_lots.return_value = ([], [change], 1)

        summary = self.monitor._scan_profile(self.profile)

        self.assertEqual(summary.price_changes, [change])
        self.monitor.notifier.print_price_change.assert_called_once_with(
            change,
        )

    def test_failed_fetch_does_not_update_last_success(self) -> None:
        self.monitor.parser.fetch.return_value = ""
        self.monitor.parser.parse.return_value = []
        self.monitor.database.sync_lots.return_value = ([], [], 0)

        self.monitor._scan_profile(self.profile)

        self.monitor.notifier.set_last_success.assert_not_called()
        self.monitor.notifier.set_system_status.assert_any_call(
            "Internet",
            False,
        )


if __name__ == "__main__":
    unittest.main()

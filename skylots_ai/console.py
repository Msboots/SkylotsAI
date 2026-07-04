"""
Консольные уведомления мониторинга.
"""

from collections.abc import Sequence

from skylots_ai.models import Lot


class ConsoleNotifier:

    def print_status(
        self,
        title: str,
        lines: Sequence[str] | None = None,
    ) -> None:
        self._print_separator("=")
        print(title)

        if lines:
            print()
            for line in lines:
                print(line)

        self._print_separator("=")

    def print_summary(
        self,
        profile_name: str,
        fetched: int,
        new_lots: int,
    ) -> None:
        self._print_separator("=")
        print("Profile")
        print()
        print(profile_name)
        print()
        print("Fetched")
        print()
        print(fetched)
        print()
        print("New")
        print()
        print(new_lots)

    def print_new_lot(self, lot: Lot) -> None:
        self._print_separator("-")
        print("NEW LOT")
        print()
        print(lot.title)
        print()
        print("Price")
        print()
        print(f"{lot.price} грн")
        print()

        if lot.seller:
            print("Seller")
            print()
            print(lot.seller)
            print()

        if lot.end_time:
            print("Ends")
            print()
            print(lot.end_time)
            print()

        print("URL")
        print()
        print(lot.url)

    @staticmethod
    def _print_separator(symbol: str) -> None:
        print(symbol * 56)

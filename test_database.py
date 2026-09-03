"""Тесты пакетной синхронизации SQLite."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skylots_ai.database import Database
from skylots_ai.models import Lot


class DatabaseSyncTests(unittest.TestCase):

    def test_sync_lots_inserts_then_updates_in_one_batch(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "skylots.db")
            database.initialize()
            lots = [
                Lot("1", "First", "seller", 10, "https://example.test/1"),
                Lot("2", "Second", "seller", 20, "https://example.test/2"),
            ]

            new_lots, changes, total = database.sync_lots(lots, "first")
            repeated_lots, repeated_changes, repeated_total = (
                database.sync_lots(lots, "second")
            )

            self.assertEqual([lot.id for lot in new_lots], ["1", "2"])
            self.assertEqual(changes, [])
            self.assertEqual(total, 2)
            self.assertEqual(repeated_lots, [])
            self.assertEqual(repeated_changes, [])
            self.assertEqual(repeated_total, 2)
            self.assertEqual(database.get_lot("1").first_seen, "first")
            self.assertEqual(database.get_lot("1").last_seen, "second")
            self.assertEqual(
                [entry.price for entry in database.get_price_history("1")],
                [10],
            )

    def test_sync_lots_records_only_real_price_changes(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "skylots.db")
            database.initialize()
            original = Lot(
                "1",
                "Original title",
                "seller",
                25,
                "https://example.test/1",
            )
            discounted = Lot(
                "1",
                "Updated title",
                "seller",
                15,
                "https://example.test/1",
            )

            database.sync_lots([original], "first")
            _, changes, _ = database.sync_lots([discounted], "second")
            _, repeated_changes, _ = database.sync_lots(
                [discounted],
                "third",
            )

            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0].previous_price, 25)
            self.assertEqual(changes[0].current_price, 15)
            self.assertTrue(changes[0].decreased)
            self.assertEqual(repeated_changes, [])
            self.assertEqual(database.get_lot("1").price, 15)
            self.assertEqual(database.get_lot("1").title, "Updated title")
            self.assertEqual(
                [entry.price for entry in database.get_price_history("1")],
                [25, 15],
            )


if __name__ == "__main__":
    unittest.main()

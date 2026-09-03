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

            new_lots, total = database.sync_lots(lots, "first")
            repeated_lots, repeated_total = database.sync_lots(lots, "second")

            self.assertEqual([lot.id for lot in new_lots], ["1", "2"])
            self.assertEqual(total, 2)
            self.assertEqual(repeated_lots, [])
            self.assertEqual(repeated_total, 2)
            self.assertEqual(database.get_lot("1").first_seen, "first")
            self.assertEqual(database.get_lot("1").last_seen, "second")


if __name__ == "__main__":
    unittest.main()

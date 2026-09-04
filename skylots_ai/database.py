"""Работа с базой данных SQLite."""

from collections.abc import Sequence
from pathlib import Path
import sqlite3

from skylots_ai.models import Lot, PriceChange, PriceHistory


class Database:

    DB_PATH = Path("data/skylots.db")
    SCHEMA_VERSION = 1
    LOT_COLUMNS = {
        "id": "TEXT PRIMARY KEY",
        "title": "TEXT",
        "seller": "TEXT",
        "price": "INTEGER",
        "url": "TEXT",
        "city": "TEXT",
        "rating": "REAL",
        "end_time": "TEXT",
        "first_seen": "TEXT",
        "last_seen": "TEXT",
    }

    SCHEMA = (
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS lots (
            id TEXT PRIMARY KEY,
            title TEXT,
            seller TEXT,
            price INTEGER,
            url TEXT,
            city TEXT,
            rating REAL,
            end_time TEXT,
            first_seen TEXT,
            last_seen TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id TEXT,
            price INTEGER,
            checked_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id TEXT,
            notification_type TEXT,
            sent_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sellers (
            seller TEXT PRIMARY KEY,
            rating REAL,
            lots_found INTEGER DEFAULT 0,
            blacklisted INTEGER DEFAULT 0,
            favorite INTEGER DEFAULT 0,
            notes TEXT
        )
        """,
    )

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or self.DB_PATH

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self.connect()
        try:
            self._initialize(conn)
        except sqlite3.DatabaseError:
            conn.rollback()
            if self._confirm_rebuild():
                self._rebuild(conn)
            else:
                raise
        finally:
            conn.close()

    def get_schema_version(self) -> int:
        conn = self.connect()
        cur = conn.cursor()

        if not self._table_exists(cur, "schema_version"):
            conn.close()
            return 0

        cur.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return int(row["version"]) if row else 0

    def _initialize(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        for statement in self.SCHEMA:
            cur.execute(statement)

        self._migrate_lots_table(cur)
        self._set_schema_version(cur, self.SCHEMA_VERSION)
        conn.commit()

    def _migrate_lots_table(self, cur: sqlite3.Cursor) -> None:
        if not self._table_exists(cur, "lots"):
            return

        existing_columns = self._get_columns(cur, "lots")

        for column, definition in self.LOT_COLUMNS.items():
            if column in existing_columns:
                continue

            if "PRIMARY KEY" in definition.upper():
                raise sqlite3.DatabaseError(
                    f"Cannot migrate missing primary key column: {column}",
                )

            cur.execute(
                f"ALTER TABLE lots ADD COLUMN {column} {definition}",
            )

    def _set_schema_version(self, cur: sqlite3.Cursor, version: int) -> None:
        cur.execute("DELETE FROM schema_version")
        cur.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (version,),
        )

    def _rebuild(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS lots")
        cur.execute("DROP TABLE IF EXISTS history")
        cur.execute("DROP TABLE IF EXISTS notifications")
        cur.execute("DROP TABLE IF EXISTS sellers")
        cur.execute("DROP TABLE IF EXISTS schema_version")

        for statement in self.SCHEMA:
            cur.execute(statement)

        self._set_schema_version(cur, self.SCHEMA_VERSION)
        conn.commit()

    @staticmethod
    def _confirm_rebuild() -> bool:
        print("Database schema outdated.")
        answer = input("Rebuild database? [y/N] ").strip().lower()
        return answer == "y"

    @staticmethod
    def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table,),
        )
        return cur.fetchone() is not None

    @staticmethod
    def _get_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
        cur.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in cur.fetchall()}

    def get_lot(self, lot_id: str) -> Lot | None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM lots WHERE id = ?", (lot_id,))
        row = cur.fetchone()
        conn.close()

        if row is None:
            return None

        return self._row_to_lot(row)

    def insert_lot(self, lot: Lot, seen_at: str) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO lots (
                id,
                title,
                seller,
                price,
                url,
                city,
                rating,
                end_time,
                first_seen,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lot.id,
                lot.title,
                lot.seller,
                lot.price,
                lot.url,
                lot.city,
                lot.rating,
                lot.end_time,
                seen_at,
                seen_at,
            ),
        )
        conn.commit()
        conn.close()

    def sync_lots(
        self,
        lots: Sequence[Lot],
        seen_at: str,
    ) -> tuple[list[Lot], list[PriceChange], int]:
        unique_lots = list({lot.id: lot for lot in lots}.values())
        conn = self.connect()

        try:
            cur = conn.cursor()
            existing_prices = self._get_existing_lot_prices(
                cur,
                [lot.id for lot in unique_lots],
            )
            new_lots = [
                lot for lot in unique_lots if lot.id not in existing_prices
            ]
            price_changes = [
                PriceChange(
                    lot=lot,
                    previous_price=existing_prices[lot.id],
                    current_price=lot.price,
                )
                for lot in unique_lots
                if (
                    lot.id in existing_prices
                    and existing_prices[lot.id] != lot.price
                )
            ]

            cur.executemany(
                """
                INSERT INTO lots (
                    id,
                    title,
                    seller,
                    price,
                    url,
                    city,
                    rating,
                    end_time,
                    first_seen,
                    last_seen
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    seller = excluded.seller,
                    price = excluded.price,
                    url = excluded.url,
                    city = excluded.city,
                    rating = excluded.rating,
                    end_time = excluded.end_time,
                    last_seen = excluded.last_seen
                """,
                [
                    (
                        lot.id,
                        lot.title,
                        lot.seller,
                        lot.price,
                        lot.url,
                        lot.city,
                        lot.rating,
                        lot.end_time,
                        seen_at,
                        seen_at,
                    )
                    for lot in unique_lots
                ],
            )
            history_lots = new_lots + [change.lot for change in price_changes]
            cur.executemany(
                """
                INSERT INTO history (lot_id, price, checked_at)
                VALUES (?, ?, ?)
                """,
                [
                    (lot.id, lot.price, seen_at)
                    for lot in history_lots
                ],
            )
            cur.execute("SELECT COUNT(*) FROM lots")
            total_count = int(cur.fetchone()[0])
            conn.commit()
            return new_lots, price_changes, total_count
        except sqlite3.DatabaseError:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_last_seen(self, lot_id: str, seen_at: str) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE lots SET last_seen = ? WHERE id = ?",
            (seen_at, lot_id),
        )
        conn.commit()
        conn.close()

    def count_lots(self) -> int:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM lots")
        count = cur.fetchone()[0]
        conn.close()
        return int(count)

    def get_price_history(self, lot_id: str) -> list[PriceHistory]:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, lot_id, price, checked_at
            FROM history
            WHERE lot_id = ?
            ORDER BY id
            """,
            (lot_id,),
        )
        history = [
            PriceHistory(
                id=int(row["id"]),
                lot_id=str(row["lot_id"]),
                price=int(row["price"]),
                checked_at=str(row["checked_at"]),
            )
            for row in cur.fetchall()
        ]
        conn.close()
        return history

    @staticmethod
    def _get_existing_lot_prices(
        cur: sqlite3.Cursor,
        lot_ids: Sequence[str],
    ) -> dict[str, int]:
        existing_prices: dict[str, int] = {}
        batch_size = 900

        for start in range(0, len(lot_ids), batch_size):
            batch = lot_ids[start : start + batch_size]
            placeholders = ", ".join("?" for _ in batch)
            cur.execute(
                f"SELECT id, price FROM lots WHERE id IN ({placeholders})",
                batch,
            )
            existing_prices.update(
                {
                    str(row["id"]): int(row["price"])
                    for row in cur.fetchall()
                },
            )

        return existing_prices

    @staticmethod
    def _row_to_lot(row: sqlite3.Row) -> Lot:
        return Lot(
            id=row["id"],
            title=row["title"],
            seller=row["seller"],
            price=row["price"],
            url=row["url"],
            city=row["city"],
            rating=row["rating"],
            end_time=row["end_time"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )

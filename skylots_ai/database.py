"""
Работа с базой данных SQLite.
"""

from pathlib import Path
import sqlite3

from skylots_ai.models import Lot


class Database:

    DB_PATH = Path("data/skylots.db")

    SCHEMA = (
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
        cur = conn.cursor()

        for statement in self.SCHEMA:
            cur.execute(statement)

        conn.commit()
        conn.close()

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

    def update_last_seen(self, lot_id: str, seen_at: str) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE lots SET last_seen = ? WHERE id = ?",
            (seen_at, lot_id),
        )
        conn.commit()
        conn.close()

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

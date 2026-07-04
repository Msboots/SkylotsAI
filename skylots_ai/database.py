"""
Работа с базой данных SQLite.
"""

from pathlib import Path
import sqlite3


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

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or self.DB_PATH

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self.connect()
        cur = conn.cursor()

        for statement in self.SCHEMA:
            cur.execute(statement)

        conn.commit()
        conn.close()

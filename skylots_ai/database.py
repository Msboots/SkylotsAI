"""
Работа с базой данных SQLite.
"""

from pathlib import Path
import sqlite3


class Database:
    def __init__(self):
        self.db_path = Path("data/skylots.db")

    def initialize(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
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
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id TEXT,
            price INTEGER,
            checked_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id TEXT,
            notification_type TEXT,
            sent_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sellers (
            seller TEXT PRIMARY KEY,
            rating REAL,
            lots_found INTEGER DEFAULT 0,
            blacklisted INTEGER DEFAULT 0,
            favorite INTEGER DEFAULT 0,
            notes TEXT
        )
        """)

        conn.commit()
        conn.close()

        print("[ OK ] Database initialized")

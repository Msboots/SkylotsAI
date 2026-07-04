from pathlib import Path
import json
import sqlite3


class Bootstrap:
    def __init__(self):
        self.root = Path.cwd()

    def run(self):
        print("=" * 50)
        print("Skylots AI Assistant")
        print("=" * 50)

        self.create_folders()
        self.create_files()
        self.create_database()

        print("\nInitialization complete.")

    def create_folders(self):

        for folder in (
            "settings",
            "data",
            "logs",
            "cache"
        ):
            path = self.root / folder

            path.mkdir(exist_ok=True)

            print(f"[ OK ] {folder}")

    def create_files(self):

        files = {

            "config.json": {
                "check_interval": 60,
                "max_price": 20,
                "max_minutes": 15,
                "telegram": False,
                "sound": True
            },

            "keywords.txt": "",

            "blacklist.txt": "",

            "favorites.txt": "",

            "whitelist.txt": ""

        }

        settings = self.root / "settings"

        for filename, content in files.items():

            file = settings / filename

            if file.exists():

                print(f"[ OK ] {filename}")

                continue

            if filename.endswith(".json"):

                file.write_text(
                    json.dumps(content, indent=4),
                    encoding="utf-8"
                )

            else:

                file.write_text(
                    content,
                    encoding="utf-8"
                )

            print(f"[ OK ] {filename}")

    def create_database(self):

        db = self.root / "data" / "skylots.db"

        conn = sqlite3.connect(db)

        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS lots(

            id TEXT PRIMARY KEY,

            title TEXT,

            seller TEXT,

            price INTEGER,

            url TEXT,

            end_time TEXT,

            first_seen TEXT,

            last_seen TEXT

        )
        """)

        conn.commit()

        conn.close()

        print("[ OK ] skylots.db")

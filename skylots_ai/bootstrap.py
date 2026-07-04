"""
Проверка и инициализация структуры проекта.
"""

from pathlib import Path
import json

from skylots_ai import __version__
from skylots_ai.database import Database
from skylots_ai.logger import LOG_FILE, setup
from skylots_ai.models import AppSettings


class Bootstrap:

    FOLDERS = ("settings", "data", "logs", "cache")

    DEFAULT_FILES = {
        "config.json": AppSettings().to_dict(),
        "keywords.txt": "",
        "blacklist.txt": "",
        "favorites.txt": "",
        "whitelist.txt": "",
    }

    def __init__(self, root: Path | None = None):
        self.root = root or Path.cwd()
        self.status: list[str] = []

    def run(self):
        self._print_header()
        self.create_folders()
        self.create_files()
        self.create_database()
        self.initialize_logger()
        self._print_status()

    def create_folders(self):
        for folder in self.FOLDERS:
            path = self.root / folder
            path.mkdir(exist_ok=True)
            self._ok(folder)

    def create_files(self):
        settings = self.root / "settings"

        for filename, content in self.DEFAULT_FILES.items():
            file = settings / filename

            if file.exists():
                self._ok(filename)
                continue

            if filename.endswith(".json"):
                file.write_text(
                    json.dumps(content, indent=4, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                file.write_text(content, encoding="utf-8")

            self._ok(f"{filename} (created)")

    def create_database(self):
        Database(self.root / Database.DB_PATH).initialize()
        self._ok("skylots.db")

    def initialize_logger(self):
        logger = setup(self.root)
        logger.info("Skylots AI Assistant v%s — core initialized", __version__)
        self._ok(f"logger -> logs/{LOG_FILE}")

    def _print_header(self):
        print("=" * 50)
        print(f"Skylots AI Assistant v{__version__}")
        print("=" * 50)

    def _print_status(self):
        print("\n" + "-" * 50)
        print("Status: ready")
        print("-" * 50)

    def _ok(self, message: str):
        line = f"[ OK ] {message}"
        print(line)
        self.status.append(line)

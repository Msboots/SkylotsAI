"""
Мониторинг лотов Skylots.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time

from skylots_ai.config import Config
from skylots_ai.database import Database
from skylots_ai.logger import LOG_NAME, setup
from skylots_ai.parser import Parser


@dataclass
class MonitorSummary:
    total_lots: int = 0
    new_lots: int = 0
    existing_lots: int = 0


class Monitor:

    def __init__(
        self,
        config: Config | None = None,
        database: Database | None = None,
        parser: Parser | None = None,
    ) -> None:
        self.config = config or Config()
        self.database = database or Database()
        self.parser = parser or Parser(self.config)
        self.logger = self._get_logger()
        self.database.initialize()

    def run(self) -> None:
        while True:
            self.single_run()
            time.sleep(self.config.check_interval)

    def single_run(self) -> MonitorSummary:
        lots = self.parser.parse()
        summary = MonitorSummary(total_lots=len(lots))
        seen_at = self._now()

        for lot in lots:
            existing_lot = self.database.get_lot(lot.id)

            if existing_lot is None:
                self.database.insert_lot(lot, seen_at)
                summary.new_lots += 1
            else:
                self.database.update_last_seen(lot.id, seen_at)
                summary.existing_lots += 1

        self.logger.info("Total lots: %s", summary.total_lots)
        self.logger.info("New lots: %s", summary.new_lots)
        self.logger.info("Existing lots: %s", summary.existing_lots)

        return summary

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_logger(self) -> logging.Logger:
        logger = logging.getLogger(LOG_NAME)
        if not logger.handlers:
            setup()
        return logging.getLogger(LOG_NAME)

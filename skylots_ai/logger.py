"""
Настройка логирования проекта.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "skylots"
LOG_FILE = "skylots.log"


def setup(root: Path | None = None) -> logging.Logger:
    logs_dir = (root or Path.cwd()) / "logs"
    logs_dir.mkdir(exist_ok=True)

    logger = logging.getLogger(LOG_NAME)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        logs_dir / LOG_FILE,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger

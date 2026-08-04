"""Sırları maskeleyen, dönen dosya günlüğü yapılandırması."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from autogit.utils.masking import redact_text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def create_logger(root: Path) -> logging.Logger:
    log_dir = root / ".autogit" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"autogit.{root}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(log_dir / "autogit.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def close_logger(root: Path) -> None:
    """Release file handles held by a completed AutoGit command."""
    logger = logging.getLogger(f"autogit.{root}")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

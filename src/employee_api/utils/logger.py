"""Centralised logging configuration."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

ROOT_LOGGER_NAME = "employee_api"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def setup_logging(level: str = "INFO", log_file: Optional[Union[str, Path]] = None) -> logging.Logger:
    """Configure the package logger once (console + rotating file)."""
    global _configured
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.propagate = False
    formatter = logging.Formatter(_LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file:
        try:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("File logging disabled: %s", exc)

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger of the package logger, configuring logging if needed."""
    if not _configured:
        from employee_api.config import get_settings

        settings = get_settings()
        setup_logging(settings.log_level, settings.log_file)
    full_name = name if name.startswith(ROOT_LOGGER_NAME) else f"{ROOT_LOGGER_NAME}.{name}"
    return logging.getLogger(full_name)
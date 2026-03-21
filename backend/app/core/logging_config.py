"""Central logging configuration for the backend application."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _build_formatter() -> logging.Formatter:
    if settings.LOG_FORMAT.lower() == "json":
        return JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    return logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def setup_logging() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    configured_path = Path(settings.LOG_FILE_PATH)
    log_file = configured_path if configured_path.is_absolute() else backend_root / configured_path
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = _build_formatter()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if getattr(root_logger, "_nexus_logging_configured", False):
        return log_file

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger._nexus_logging_configured = True  # type: ignore[attr-defined]

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        named_logger = logging.getLogger(logger_name)
        named_logger.handlers.clear()
        named_logger.propagate = True
        named_logger.setLevel(level)

    logging.getLogger("nexus.logging").info("Logging configured. Writing to %s", log_file)
    return log_file

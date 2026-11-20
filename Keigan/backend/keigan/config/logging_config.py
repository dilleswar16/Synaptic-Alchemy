"""Structured JSON logging with a correlation id carried through requests and jobs."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

_correlation_id_variable: ContextVar[str] = ContextVar("keigan_correlation_id", default="")


def current_correlation_id() -> str:
    return _correlation_id_variable.get()


def set_correlation_id(correlation_id: str | None = None) -> str:
    effective_correlation_id = (correlation_id or uuid.uuid4().hex)[:64]
    _correlation_id_variable.set(effective_correlation_id)
    return effective_correlation_id


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": current_correlation_id() or None,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


class ReadableLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        correlation_suffix = f" [{current_correlation_id()[:8]}]" if current_correlation_id() else ""
        formatted_message = f"{datetime.now().strftime('%H:%M:%S')} {record.levelname:<7} {record.name}{correlation_suffix}: {record.getMessage()}"
        if record.exc_info:
            formatted_message += "\n" + self.formatException(record.exc_info)
        return formatted_message


def configure_logging(log_level: str, use_json_format: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter() if use_json_format else ReadableLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
    for noisy_logger_name in ("httpx", "httpcore", "azure", "urllib3", "aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)

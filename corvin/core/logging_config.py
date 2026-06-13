"""
Structured logging configuration.

``setup_logging()`` installs a single stdout handler on the root logger that
emits one JSON object per log line (``CORVIN_LOG_FORMAT=json``, the default)
or a classic human-readable line (``CORVIN_LOG_FORMAT=text``) for local
development.

Every JSON record carries the current request ID from
``corvin.core.request_context`` when one is bound, so all log lines produced
while handling an HTTP request — including those deep inside adapters and
LLM generators — can be correlated with the ``X-Request-ID`` response header.

Extra fields passed via ``logger.info(..., extra={...})`` are merged into the
JSON payload, enabling per-call structured fields (status_code, duration_ms)
without custom formatters.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

from corvin.core.request_context import get_request_id

# Attributes present on every LogRecord — anything else came in via `extra=`.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
    }
)

_TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"


class JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None) -> None:
    """Configure root logging for the API process. Safe to call more than once.

    Env vars:
        CORVIN_LOG_LEVEL   — DEBUG | INFO | WARNING | ERROR (default: INFO)
        CORVIN_LOG_FORMAT  — json | text (default: json)
    """
    resolved_level = (level or os.environ.get("CORVIN_LOG_LEVEL", "INFO")).upper()
    log_format = os.environ.get("CORVIN_LOG_FORMAT", "json").strip().lower()

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "text":
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    # Route uvicorn through the root handler for one uniform stream.
    # uvicorn.access is raised to WARNING because RequestContextMiddleware
    # already emits a structured access line (with request_id) per request.
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = True
    access_logger.setLevel(logging.WARNING)

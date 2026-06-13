"""
Request-scoped context propagation.

Holds the current HTTP request ID in a ContextVar so any log line emitted
while handling a request — from routes, services, or adapters — can be
correlated without threading the ID through every call signature.

The ID is assigned by ``apps.api.middleware.RequestContextMiddleware`` and
read by ``corvin.core.logging_config.JsonFormatter``. Outside of a request
(CLI, background tasks) the ID is ``None`` and log lines simply omit it.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_request_id_var: ContextVar[str | None] = ContextVar("corvin_request_id", default=None)


def new_request_id() -> str:
    """Generate a short, URL-safe request ID."""
    return uuid.uuid4().hex[:16]


def get_request_id() -> str | None:
    """Return the request ID for the current context, or None outside a request."""
    return _request_id_var.get()


def set_request_id(request_id: str | None) -> Token:
    """Bind *request_id* to the current context. Returns a reset token."""
    return _request_id_var.set(request_id)


def reset_request_id(token: Token) -> None:
    """Restore the previous request ID using the token from set_request_id()."""
    _request_id_var.reset(token)

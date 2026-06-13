"""
ASGI middleware for the Corvin API.

RequestContextMiddleware
    Assigns a request ID to every HTTP request (honouring an inbound
    X-Request-ID header so gateway-issued IDs propagate end to end), binds it
    to corvin.core.request_context for log correlation, echoes it back in the
    X-Request-ID response header, and emits one structured access-log line per
    request with method, path, status, and duration.

ApiVersionMiddleware
    Serves the API under both the legacy root paths and the versioned /v1
    prefix (TD-M3). Inbound /v1/... paths are rewritten to /... before routing
    so both forms reach the same handlers; every response carries an
    X-API-Version header. New clients should use /v1; root paths remain for
    backward compatibility with the existing frontend.

Both are pure ASGI middlewares — not Starlette BaseHTTPMiddleware — so they
cannot buffer or interfere with the SSE streaming endpoints.
"""

from __future__ import annotations

import logging
import time

from corvin.core.request_context import new_request_id, reset_request_id, set_request_id

_access_log = logging.getLogger("corvin.api.access")

API_VERSION = "1"
_VERSION_PREFIX = "/v1"


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound_id = ""
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                inbound_id = value.decode("latin-1").strip()
                break
        request_id = inbound_id or new_request_id()

        token = set_request_id(request_id)
        started = time.perf_counter()
        response_status = {"code": 0}

        async def send_with_request_id(message) -> None:
            if message["type"] == "http.response.start":
                response_status["code"] = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            _access_log.info(
                "%s %s -> %s (%.1f ms)",
                scope.get("method", "-"),
                scope.get("path", "-"),
                response_status["code"] or "ERR",
                duration_ms,
                extra={
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "status_code": response_status["code"],
                    "duration_ms": round(duration_ms, 1),
                },
            )
            reset_request_id(token)


class ApiVersionMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == _VERSION_PREFIX or path.startswith(_VERSION_PREFIX + "/"):
            scope = dict(scope)
            scope["path"] = path[len(_VERSION_PREFIX):] or "/"
            raw_path = scope.get("raw_path")
            if isinstance(raw_path, bytes) and raw_path.startswith(b"/v1"):
                scope["raw_path"] = raw_path[len(b"/v1"):] or b"/"

        async def send_with_version(message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-api-version", API_VERSION.encode("latin-1"))
                )
            await send(message)

        await self.app(scope, receive, send_with_version)

"""
RFC 7807 problem+json error responses (TD-M9).

``install_error_handlers(app)`` converts every HTTPException, request
validation failure, and unhandled exception into an
``application/problem+json`` body:

    {
      "type": "about:blank",
      "title": "Not Found",
      "status": 404,
      "detail": "Investigation abc123 not found",
      "instance": "/investigations/abc123",
      "request_id": "f3a91c0d2b7e4a18"
    }

The standard ``detail`` member is always a plain string, so existing clients
that read ``payload.detail`` (the web frontend, the CLI) keep working
unchanged. Validation errors additionally expose the field-level breakdown in
an ``errors`` extension member.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from corvin.core.request_context import get_request_id

_log = logging.getLogger("corvin.api.errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"


def problem_response(
    request: Request,
    status_code: int,
    detail: str,
    *,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    **extensions: object,
) -> JSONResponse:
    """Build an RFC 7807 problem document for *request*."""
    try:
        default_title = HTTPStatus(status_code).phrase
    except ValueError:
        default_title = "Error"
    body: dict[str, object] = {
        "type": "about:blank",
        "title": title or default_title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    request_id = get_request_id()
    if request_id:
        body["request_id"] = request_id
    body.update(extensions)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register problem+json handlers on *app*. Call once at startup."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        extensions: dict[str, object] = {}
        if not isinstance(detail, str):
            # A handful of routes raise HTTPException with structured detail —
            # surface it under `errors` and keep `detail` a string for clients.
            extensions["errors"] = jsonable_encoder(detail)
            try:
                detail = HTTPStatus(exc.status_code).phrase
            except ValueError:
                detail = "Error"
        return problem_response(
            request, exc.status_code, detail, headers=getattr(exc, "headers", None), **extensions
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        summary = first.get("msg", "Request validation failed")
        detail = f"{location}: {summary}" if location else str(summary)
        return problem_response(
            request, 422, detail, title="Validation Error", errors=errors
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        _log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return problem_response(
            request,
            500,
            "An internal error occurred. Quote the request_id when reporting this issue.",
        )

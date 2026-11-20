"""Exception hierarchy and FastAPI handlers producing RFC 9457 problem+json responses."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from keigan.config.logging_config import current_correlation_id

logger = logging.getLogger(__name__)


class KeiganException(Exception):
    status_code = 500
    error_code = "internal_error"
    title = "Something went wrong"

    def __init__(self, detail: str | None = None, *, error_code: str | None = None, extra: dict[str, Any] | None = None):
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        if error_code:
            self.error_code = error_code
        self.extra = extra or {}


class NotFoundException(KeiganException):
    status_code = 404
    error_code = "not_found"
    title = "Not found"


class ForbiddenException(KeiganException):
    status_code = 403
    error_code = "forbidden"
    title = "You do not have access to this resource"


class AuthenticationException(KeiganException):
    status_code = 401
    error_code = "authentication_required"
    title = "Authentication required"


class BusinessValidationException(KeiganException):
    status_code = 422
    error_code = "validation_failed"
    title = "The request is not valid"

    def __init__(self, detail: str, *, field_errors: list[dict[str, str]] | None = None, error_code: str | None = None):
        super().__init__(detail, error_code=error_code, extra={"fieldErrors": field_errors or []})


class ConflictException(KeiganException):
    status_code = 409
    error_code = "conflict"
    title = "The resource changed or already exists"


class RateLimitedException(KeiganException):
    status_code = 429
    error_code = "rate_limited"
    title = "Too many requests"


class IntegrationException(KeiganException):
    """An external system (Azure, ServiceNow, Graph, a log tool) failed or refused."""

    status_code = 502
    error_code = "integration_failed"
    title = "An external system did not respond as expected"


class AmbiguousGroupNameException(IntegrationException):
    """Two or more Entra groups share a display name, so Keigan cannot tell which one the application means."""

    status_code = 409
    error_code = "entra_group_name_ambiguous"
    title = "More than one Entra group has this name"


class ReaderNotAvailableException(IntegrationException):
    status_code = 501
    error_code = "reader_not_available"
    title = "Keigan cannot read this tool yet"


class TokenBudgetExceededException(KeiganException):
    status_code = 429
    error_code = "token_budget_exceeded"
    title = "The daily AI token budget for this application is used up"


class LlmUnavailableException(KeiganException):
    status_code = 503
    error_code = "ai_unavailable"
    title = "The AI service is unavailable"


class LlmOutputValidationException(KeiganException):
    status_code = 502
    error_code = "ai_output_invalid"
    title = "The AI returned an answer Keigan could not validate"


def build_problem_response(status_code: int, title: str, detail: str, error_code: str, extra: dict[str, Any] | None = None) -> JSONResponse:
    problem_body: dict[str, Any] = {
        "type": f"https://keigan.metlife/errors/{error_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "errorCode": error_code,
        "correlationId": current_correlation_id(),
    }
    if extra:
        problem_body.update(extra)
    return JSONResponse(problem_body, status_code=status_code, media_type="application/problem+json")


def register_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(KeiganException)
    async def handle_keigan_exception(_request: Request, exception: KeiganException) -> JSONResponse:
        if exception.status_code >= 500:
            logger.warning("Request failed: %s (%s)", exception.detail, exception.error_code)
        return build_problem_response(exception.status_code, exception.title, exception.detail, exception.error_code, exception.extra)

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation(_request: Request, exception: RequestValidationError) -> JSONResponse:
        field_errors = [
            {"field": ".".join(str(location_part) for location_part in error.get("loc", []) if location_part != "body"), "message": error.get("msg", "")}
            for error in exception.errors()
        ]
        return build_problem_response(422, "The request is not valid", "One or more fields are invalid.", "validation_failed", {"fieldErrors": field_errors})

    @application.exception_handler(Exception)
    async def handle_unexpected_exception(_request: Request, exception: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exception)
        return build_problem_response(500, "Something went wrong", "An unexpected error occurred. Quote the correlation id when reporting it.", "internal_error")

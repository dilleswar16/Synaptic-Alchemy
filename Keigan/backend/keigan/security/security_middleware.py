"""HTTP hardening: correlation ids, security headers, request size limits and simple rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from keigan.config.logging_config import set_correlation_id
from keigan.config.settings import get_settings
from keigan.exceptions.keigan_exceptions import RateLimitedException, build_problem_response

DOCUMENTATION_PATH_PREFIXES = ("/api/docs", "/api/redoc", "/api/openapi.json")


class SecurityMiddleware(BaseHTTPMiddleware):
    """One middleware for correlation id, payload limit and security headers (keeps the stack lean)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        correlation_id = set_correlation_id(request.headers.get("x-correlation-id"))

        declared_length = request.headers.get("content-length")
        maximum_bytes = (
            settings.alert_intake_max_payload_bytes if request.url.path.startswith("/api/alerts/in/") else settings.max_request_body_bytes
        )
        if declared_length and declared_length.isdigit() and int(declared_length) > maximum_bytes:
            return build_problem_response(413, "Payload too large", f"The request body exceeds {maximum_bytes} bytes.", "payload_too_large")

        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.url.path.startswith(DOCUMENTATION_PATH_PREFIXES):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            response.headers.setdefault("Cache-Control", "no-store")
        if not settings.is_local_environment:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class SlidingWindowRateLimiter:
    """In-process sliding-window limiter. In AKS the ingress also rate-limits; this protects each pod."""

    def __init__(self) -> None:
        self._request_times_by_key: dict[str, deque[float]] = defaultdict(deque)

    def check(self, limiter_key: str, maximum_requests_per_minute: int) -> None:
        now = time.monotonic()
        request_times = self._request_times_by_key[limiter_key]
        while request_times and now - request_times[0] > 60:
            request_times.popleft()
        if len(request_times) >= maximum_requests_per_minute:
            raise RateLimitedException("Too many requests. Please slow down and try again shortly.")
        request_times.append(now)


rate_limiter = SlidingWindowRateLimiter()

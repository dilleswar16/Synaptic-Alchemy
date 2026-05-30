"""Bring-Your-Own-API connector — generic parametric HTTP connector."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from corvin.connectors.base import BaseConnector, TestResult

_log = logging.getLogger(__name__)


def _inject_auth(headers: dict, auth_type: str, credential_value: str | None) -> dict:
    if not credential_value:
        return headers
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {credential_value}"
    elif auth_type == "basic":
        headers["Authorization"] = f"Basic {credential_value}"  # base64-encoded user:pass
    elif auth_type == "api_key":
        # credential_value format: "Header-Name:value"
        if ":" in credential_value:
            header_name, value = credential_value.split(":", 1)
            headers[header_name.strip()] = value.strip()
    return headers


class ByoaConnector(BaseConnector):
    """
    Generic HTTP connector for any API that exposes logs and metrics endpoints.

    config keys:
        base_url (required): e.g. "https://my-logging-api.internal"
        health_endpoint (default "/health"): endpoint for connectivity test
        logs_endpoint (default "/logs"): endpoint for log queries
        metrics_endpoint (default "/metrics"): endpoint for metrics queries
        auth_type (default "bearer"): bearer|basic|api_key
        timeout_seconds (default 10): HTTP request timeout
        extra_headers (default {}): additional headers to include
        service_param_name (default "service"): query param name for service filter
        time_range_param_name (default "minutes"): query param name for time range
    credential_value: opaque string interpreted per auth_type
    """

    def __init__(self, config: dict[str, Any], credential_value: str | None = None) -> None:
        self._base_url: str = config.get("base_url", "").rstrip("/")
        self._health_ep: str = config.get("health_endpoint", "/health")
        self._logs_ep: str = config.get("logs_endpoint", "/logs")
        self._metrics_ep: str = config.get("metrics_endpoint", "/metrics")
        self._auth_type: str = config.get("auth_type", "bearer")
        self._timeout: int = int(config.get("timeout_seconds", 10))
        self._extra_headers: dict = config.get("extra_headers", {})
        self._service_param: str = config.get("service_param_name", "service")
        self._time_param: str = config.get("time_range_param_name", "minutes")
        self._credential_value = credential_value

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", **self._extra_headers}
        return _inject_auth(h, self._auth_type, self._credential_value)

    def test_connection(self) -> TestResult:
        if not self._base_url:
            return TestResult(ok=False, message="base_url is empty")
        t0 = time.monotonic()
        try:
            resp = httpx.get(
                f"{self._base_url}{self._health_ep}",
                headers=self._headers(),
                timeout=self._timeout,
                follow_redirects=True,
                verify=False,
            )
            ms = (time.monotonic() - t0) * 1000
            if resp.status_code < 400:
                return TestResult(ok=True, message=f"HTTP {resp.status_code}", latency_ms=ms)
            return TestResult(ok=False, message=f"HTTP {resp.status_code}: {resp.text[:200]}", latency_ms=ms)
        except Exception as exc:
            ms = (time.monotonic() - t0) * 1000
            return TestResult(ok=False, message=str(exc), latency_ms=ms)

    def fetch_logs(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        if not self._base_url:
            return []
        try:
            resp = httpx.get(
                f"{self._base_url}{self._logs_ep}",
                params={self._service_param: service_name, self._time_param: time_range_minutes},
                headers=self._headers(),
                timeout=self._timeout,
                follow_redirects=True,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("logs", data.get("data", []))
        except Exception as exc:
            _log.debug("ByoaConnector.fetch_logs: %s", exc)
            return []

    def fetch_metrics(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        if not self._base_url:
            return []
        try:
            resp = httpx.get(
                f"{self._base_url}{self._metrics_ep}",
                params={self._service_param: service_name, self._time_param: time_range_minutes},
                headers=self._headers(),
                timeout=self._timeout,
                follow_redirects=True,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("metrics", data.get("data", []))
        except Exception as exc:
            _log.debug("ByoaConnector.fetch_metrics: %s", exc)
            return []

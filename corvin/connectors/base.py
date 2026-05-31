"""Abstract base class for all Corvin data-source connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestResult:
    ok: bool
    message: str
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """Common interface for every log/metrics source."""

    @abstractmethod
    def test_connection(self) -> TestResult: ...

    @abstractmethod
    def fetch_logs(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]: ...

    @abstractmethod
    def fetch_metrics(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]: ...

    def get_availability(self, service_name: str, window_days: int = 30) -> dict[str, Any] | None:
        """
        Return {"pct": float, "raw": dict} for the availability SLI, or None if unsupported/no data.
        Subclasses should override to provide real metric values.
        """
        return None

    def get_latency_pct(self, service_name: str, threshold_ms: int = 500, window_days: int = 30) -> dict[str, Any] | None:
        """
        Return {"pct": float, "raw": dict} for the latency SLI (% of requests below threshold_ms),
        or None if unsupported/no data.
        Subclasses should override to provide real metric values.
        """
        return None

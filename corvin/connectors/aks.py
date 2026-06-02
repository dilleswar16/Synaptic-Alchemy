"""AKS connector for connector-registry testability and DB-driven onboarding."""
from __future__ import annotations

import logging
import time
from typing import Any

from corvin.connectors.base import BaseConnector, TestResult
from corvin.evidence.aks_adapter import AKSAdapter

_log = logging.getLogger(__name__)


class AKSConnector(BaseConnector):
    """Connector wrapper around AKSAdapter for app-panel connector tests.

    This connector validates required AKS identity fields and probes Kubernetes
    access using the same runtime mode as the AKSAdapter.
    """

    def __init__(self, config: dict[str, Any], credential_value: str | None = None) -> None:
        del credential_value  # AKS uses ambient Azure/kube credentials.
        self._config = dict(config or {})

    def test_connection(self) -> TestResult:
        cluster_name = str(self._config.get("cluster_name", "")).strip()
        resource_group = str(self._config.get("resource_group", "")).strip()
        subscription_id = str(self._config.get("subscription_id", "")).strip()
        namespace = str(self._config.get("default_namespace", "default") or "default")

        if not cluster_name:
            return TestResult(ok=False, message="cluster_name is empty")
        if not resource_group:
            return TestResult(ok=False, message="resource_group is empty")
        if not subscription_id:
            return TestResult(ok=False, message="subscription_id is empty")

        t0 = time.monotonic()
        try:
            adapter = AKSAdapter(config=self._config)
            if getattr(adapter, "_core_v1", None) is None:
                ms = (time.monotonic() - t0) * 1000
                return TestResult(
                    ok=False,
                    message="Kubernetes client not initialized. Ensure kubeconfig/in-cluster auth is available.",
                    latency_ms=ms,
                )
            snapshot = adapter.list_all_pods(namespace=namespace)
            services = snapshot.get("services", []) if isinstance(snapshot, dict) else []
            ms = (time.monotonic() - t0) * 1000
            return TestResult(
                ok=True,
                message=f"Connected successfully (namespace={namespace}, services={len(services)})",
                latency_ms=ms,
            )
        except Exception as exc:  # noqa: BLE001
            _log.debug("AKSConnector.test_connection failed: %s", exc)
            ms = (time.monotonic() - t0) * 1000
            return TestResult(ok=False, message=str(exc), latency_ms=ms)

    def fetch_logs(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        del service_name, time_range_minutes
        # Logs/metrics come from dedicated adapters (Container Insights / Elastic).
        return []

    def fetch_metrics(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        del service_name, time_range_minutes
        # Logs/metrics come from dedicated adapters (Container Insights / Elastic).
        return []

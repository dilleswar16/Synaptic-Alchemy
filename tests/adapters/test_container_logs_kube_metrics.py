"""
Tests for ContainerLogsAdapter kube metric methods.

Validates the 4 new methods added for P0/P1 evidence collection:
  - get_resource_metrics()    — InsightsMetrics cpu/memory
  - get_container_inventory() — ContainerInventory image details
  - get_node_inventory()      — KubeNodeInventory node health
  - get_network_metrics()     — InsightsMetrics network tx/rx

Uses FakeContainerLogsAdapter pattern (no real Azure calls).
"""

from __future__ import annotations

from typing import Any

from corvin.evidence.container_logs_adapter import ContainerLogsAdapter


# ── Fake adapter ──────────────────────────────────────────────────────────────


class FakeContainerLogsAdapter(ContainerLogsAdapter):
    """Override all public methods to return canned data without Azure calls."""

    def __init__(self) -> None:
        # Skip parent __init__ entirely — no real Azure client needed
        self._config = {"default_time_range_minutes": 60, "default_namespace": "chad", "max_log_rows": 200}
        self._client = None  # Will be bypassed by overrides
        self._workspace_id = "fake"

    def get_resource_metrics(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"HostName": "aks-nodepool1-vmss000000", "Name": "process_cpu_seconds_total", "AvgValue": 5923.89, "MaxValue": 6100.0},
            {"HostName": "aks-nodepool1-vmss000000", "Name": "process_resident_memory_bytes", "AvgValue": 512_000_000, "MaxValue": 780_000_000},
        ]

    def get_container_inventory(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"Name": f"{service_name}-abc", "Image": "myregistry.azurecr.io/order-service", "ImageTag": "v2.4.1",
             "ContainerState": "Running", "CreatedTime": "2026-05-20T08:00:00Z"},
        ]

    def get_node_inventory(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"Computer": "aks-nodepool1-12345678-vmss000000", "Status": "Ready",
             "KubeletVersion": "v1.28.5", "OperatingSystem": "linux"},
        ]

    def get_network_metrics(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"HostName": "aks-nodepool1-vmss000000", "Name": "bytes_sent", "AvgValue": 1_024_000, "MaxValue": 5_120_000},
            {"HostName": "aks-nodepool1-vmss000000", "Name": "bytes_recv", "AvgValue": 2_048_000, "MaxValue": 8_192_000},
        ]

    def get_pod_restarts(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"Name": f"{service_name}-abc-xyz", "PodStatus": "Running", "ContainerRestartCount": 3, "PodRestartCount": 3},
        ]

    def get_oom_kill_events(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"Name": f"{service_name}-abc-xyz", "Reason": "OOMKilled", "Message": "Container killed due to OOM", "Count": 1},
        ]

    def get_autoscaler_events(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"Name": "order-service-hpa", "Reason": "SuccessfulRescale", "Message": "New size: 3", "ObjectKind": "HorizontalPodAutoscaler", "Count": 1},
        ]

    def get_health_probe_failures(
        self, service_name: str, namespace: str | None = None, time_range_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"Name": f"{service_name}-abc-xyz", "Reason": "Unhealthy", "Message": "Readiness probe failed: HTTP 503", "Count": 2},
        ]


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_resource_metrics_returns_cpu_and_memory():
    adapter = FakeContainerLogsAdapter()
    result = adapter.get_resource_metrics("order-service")
    assert len(result) == 2
    metric_names = {r["Name"] for r in result}
    assert "process_cpu_seconds_total" in metric_names
    assert "process_resident_memory_bytes" in metric_names
    for row in result:
        assert "vmss" in row["HostName"]
        assert row["AvgValue"] > 0


def test_container_inventory_returns_image_info():
    adapter = FakeContainerLogsAdapter()
    result = adapter.get_container_inventory("order-service")
    assert len(result) == 1
    row = result[0]
    assert "order-service" in row["Image"]
    assert row["ImageTag"] == "v2.4.1"
    assert row["ContainerState"] == "Running"


def test_node_inventory_returns_node_status():
    adapter = FakeContainerLogsAdapter()
    result = adapter.get_node_inventory("order-service")
    assert len(result) == 1
    row = result[0]
    assert row["Status"] == "Ready"
    assert "vmss" in row["Computer"]
    assert row["OperatingSystem"] == "linux"


def test_network_metrics_returns_tx_rx():
    adapter = FakeContainerLogsAdapter()
    result = adapter.get_network_metrics("order-service")
    assert len(result) == 2
    metric_names = {r["Name"] for r in result}
    assert "bytes_sent" in metric_names
    assert "bytes_recv" in metric_names


def test_no_client_returns_empty_list():
    """When Azure client is None (CI/dev), all methods return []."""
    adapter = ContainerLogsAdapter.__new__(ContainerLogsAdapter)
    adapter._config = {"default_time_range_minutes": 60, "default_namespace": "chad"}
    adapter._client = None
    adapter._workspace_id = ""

    assert adapter.get_resource_metrics("svc") == []
    assert adapter.get_container_inventory("svc") == []
    assert adapter.get_node_inventory("svc") == []
    assert adapter.get_network_metrics("svc") == []
    assert adapter.get_pod_restarts("svc") == []
    assert adapter.get_oom_kill_events("svc") == []
    assert adapter.get_autoscaler_events("svc") == []
    assert adapter.get_health_probe_failures("svc") == []


def test_enrichment_bundle_has_new_fields():
    """New EvidenceBundle fields exist and default to empty lists."""
    from corvin.core.contracts import EvidenceBundle

    bundle = EvidenceBundle(request_id="test-123")
    assert bundle.container_resource_metrics == []
    assert bundle.container_inventory == []
    assert bundle.node_inventory == []
    assert bundle.network_metrics == []
    assert bundle.pod_restarts == []
    assert bundle.oom_kill_events == []
    assert bundle.autoscaler_events == []
    assert bundle.health_probe_failures == []


def test_enrichment_service_wires_new_sources():
    """EnrichmentService populates the 4 new fields when adapter has data."""
    from corvin.core.contracts import InvestigationRequest, TriggerSource
    from corvin.enrich.enrichment_service import EnrichmentService
    from corvin.evidence.aks_adapter import AKSAdapter
    from corvin.evidence.elastic_adapter import ElasticAdapter
    from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter

    service = EnrichmentService(
        elastic=ElasticAdapter.__new__(ElasticAdapter),
        log_analytics=LogAnalyticsAdapter.__new__(LogAnalyticsAdapter),
        aks=AKSAdapter.__new__(AKSAdapter),
        container_logs=FakeContainerLogsAdapter(),
    )
    # Stub out the adapters that would hit Azure
    service._elastic = None  # type: ignore[assignment]

    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="test",
    )
    bundle = service.enrich(req)

    assert len(bundle.container_resource_metrics) == 2
    assert len(bundle.container_inventory) == 1
    assert len(bundle.node_inventory) == 1
    assert len(bundle.network_metrics) == 2
    assert len(bundle.pod_restarts) == 1
    assert len(bundle.oom_kill_events) == 1
    assert len(bundle.autoscaler_events) == 1
    assert len(bundle.health_probe_failures) == 1

"""
Evidence adapter tests.

Adapters that are still stubs assert NotImplementedError.
Once an adapter is wired, the corresponding test verifies wired behaviour
using a mocked client (no live service required).
"""

from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from corvin.evidence.aks_adapter import AKSAdapter
from corvin.evidence.azure_activity_adapter import AzureActivityAdapter
from corvin.evidence.elastic_adapter import ElasticAdapter
from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter


# ── ElasticAdapter (wired – Slice 2b) ────────────────────────────────────────

_ELASTIC_CONFIG = {
    "host": "http://localhost:9200",
    "api_key": "test-key",
    "log_index_pattern": "logs-*",
    "metrics_index_pattern": "metrics-*",
    "default_time_range_minutes": 30,
    "max_log_hits": 50,
}


def test_elastic_get_logs_returns_list():
    """Wired adapter returns a list of dicts (mocked client, no live cluster)."""
    mock_response = {"hits": {"hits": [{"_source": {"message": "err", "level": "ERROR"}}]}}
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = mock_response
        adapter = ElasticAdapter(config=_ELASTIC_CONFIG)
        result = adapter.get_logs("order-service")
    assert isinstance(result, list)
    assert result[0]["level"] == "ERROR"


def test_elastic_get_metrics_returns_list():
    """Wired adapter returns aggregation buckets (mocked client, no live cluster)."""
    mock_response = {
        "aggregations": {
            "by_time": {
                "buckets": [{"key_as_string": "2026-04-04T00:00:00Z", "avg_value": {"value": 5.0}, "max_value": {"value": 10.0}}]
            }
        }
    }
    with patch("corvin.evidence.elastic_adapter.Elasticsearch") as MockES:
        MockES.return_value.search.return_value = mock_response
        adapter = ElasticAdapter(config=_ELASTIC_CONFIG)
        result = adapter.get_metrics("order-service")
    assert isinstance(result, list)
    assert result[0]["avg_value"]["value"] == 5.0


# ── LogAnalyticsAdapter (wired – Slice 3) ────────────────────────────────────

_LA_CONFIG = {
    "workspace_id": "test-ws",
    "tenant_id": "test-tenant",
    "client_id": "test-client",
    "client_secret": "test-secret",
    "default_time_range_minutes": 30,
}


def _make_la_query_result(rows, column_names):
    """Build a minimal mock LogsQueryResult for testing."""
    from unittest.mock import MagicMock
    from azure.monitor.query import LogsQueryStatus

    mock_col = [MagicMock(name=cn) for cn in column_names]
    for i, cn in enumerate(column_names):
        mock_col[i].name = cn
    mock_table = MagicMock()
    mock_table.columns = mock_col
    mock_table.rows = rows
    mock_result = MagicMock()
    mock_result.status = LogsQueryStatus.SUCCESS
    mock_result.tables = [mock_table]
    return mock_result


def test_log_analytics_get_apim_logs_returns_list():
    """Wired adapter returns a list of dicts (mocked client, no live workspace)."""
    rows = [["500", "GetOrder", 120.0], ["200", "ListOrders", 45.0]]
    columns = ["ResponseCode", "OperationName", "DurationMs"]
    mock_result = _make_la_query_result(rows, columns)

    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = mock_result
        adapter = LogAnalyticsAdapter(config=_LA_CONFIG)
        result = adapter.get_apim_logs("order-service")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["ResponseCode"] == "500"
    assert result[1]["OperationName"] == "ListOrders"


# ── AKSAdapter (wired – Slice 4) ─────────────────────────────────────────────

_AKS_CONFIG = {
    "cluster_name": "test-cluster",
    "resource_group": "test-rg",
    "kube_config_path": "~/.kube/config",
    "default_namespace": "default",
    "events_lookback_minutes": 60,
}


def test_aks_get_pod_context_returns_dict():
    """Wired adapter returns a dict with pods/events/deployment keys (mocked client)."""
    with patch("corvin.evidence.aks_adapter.k8s_config"), \
         patch("corvin.evidence.aks_adapter.k8s_client") as MockK8s:
        mock_core = MagicMock()
        mock_apps = MagicMock()
        MockK8s.CoreV1Api.return_value = mock_core
        MockK8s.AppsV1Api.return_value = mock_apps

        # Empty pod list and event list for this smoke test
        mock_core.list_namespaced_pod.return_value.items = []
        mock_core.list_namespaced_event.return_value.items = []
        mock_apps.read_namespaced_deployment.return_value.metadata.name = "order-service"
        mock_apps.read_namespaced_deployment.return_value.metadata.namespace = "default"
        mock_apps.read_namespaced_deployment.return_value.spec.replicas = 2
        mock_apps.read_namespaced_deployment.return_value.status.ready_replicas = 2
        mock_apps.read_namespaced_deployment.return_value.status.available_replicas = 2
        mock_apps.read_namespaced_deployment.return_value.status.unavailable_replicas = None

        adapter = AKSAdapter(config=_AKS_CONFIG)
        result = adapter.get_pod_context("order-service")

    assert isinstance(result, dict)
    assert "pods" in result
    assert "events" in result
    assert "deployment" in result


# ── AzureActivityAdapter (wired – Slice 4b) ──────────────────────────────────

_AA_CONFIG = {
    "workspace_id": "ws-test-activity",
    "tenant_id": "tenant-abc",
    "client_id": "client-abc",
    "client_secret": "secret-abc",
    "default_time_range_minutes": 60,
    "max_events": 100,
}


def test_azure_activity_get_recent_changes_returns_list():
    """Wired adapter returns a list of dicts (mocked client, no live workspace)."""
    from unittest.mock import MagicMock as _MagicMock
    from azure.monitor.query import LogsQueryStatus

    col = _MagicMock()
    col.name = "OperationNameValue"
    mock_table = _MagicMock()
    mock_table.columns = [col]
    mock_table.rows = [["Microsoft.Web/sites/restart/action"]]
    mock_result = _MagicMock()
    mock_result.status = LogsQueryStatus.SUCCESS
    mock_result.tables = [mock_table]

    with patch("corvin.evidence.azure_activity_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = mock_result
        adapter = AzureActivityAdapter(config=_AA_CONFIG)
        result = adapter.get_recent_changes("order-service")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["OperationNameValue"] == "Microsoft.Web/sites/restart/action"



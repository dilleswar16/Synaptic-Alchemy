"""
Slice 3 – Log Analytics APIM adapter tests.

Uses unittest.mock.patch to mock DefaultAzureCredential and LogsQueryClient
so no live Azure workspace is required.  Tests cover:
  - Successful query returns list of row dicts keyed by column name.
  - query_workspace exception returns empty list (graceful degradation).
  - Empty tables list in result returns empty list.
  - Partial/non-SUCCESS status returns empty list.
  - environment filter is omitted when not provided.
  - environment filter is included in query when provided.
  - env-var placeholders in config are expanded from os.environ.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from azure.monitor.query import LogsQueryStatus

from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter

# ---------------------------------------------------------------------------
# Shared config and helpers
# ---------------------------------------------------------------------------

_CONFIG = {
    "workspace_id": "ws-test-123",
    "tenant_id": "tenant-abc",
    "client_id": "client-abc",
    "client_secret": "secret-abc",
    "default_time_range_minutes": 30,
    "apim_table": "ApiManagementGatewayLogs",
}

_COLUMNS = ["ResponseCode", "OperationName", "DurationMs", "ServiceName"]
_ROWS = [
    ["500", "GetOrder", 200.0, "order-service"],
    ["200", "ListOrders", 35.0, "order-service"],
]


def _make_success_result(rows=None, columns=None):
    """Build a minimal mock LogsQueryResult with SUCCESS status."""
    rows = rows if rows is not None else _ROWS
    columns = columns if columns is not None else _COLUMNS

    mock_cols = []
    for cn in columns:
        col = MagicMock()
        col.name = cn
        mock_cols.append(col)

    mock_table = MagicMock()
    mock_table.columns = mock_cols
    mock_table.rows = rows

    mock_result = MagicMock()
    mock_result.status = LogsQueryStatus.SUCCESS
    mock_result.tables = [mock_table]
    return mock_result


# ---------------------------------------------------------------------------
# Successful query tests
# ---------------------------------------------------------------------------


def test_get_apim_logs_returns_list_of_dicts():
    """Successful query returns each row as a dict keyed by column name."""
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = LogAnalyticsAdapter(config=_CONFIG)
        result = adapter.get_apim_logs("order-service", environment="production")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {
        "ResponseCode": "500",
        "OperationName": "GetOrder",
        "DurationMs": 200.0,
        "ServiceName": "order-service",
    }
    assert result[1]["ResponseCode"] == "200"


def test_get_apim_logs_without_environment_still_works():
    """Omitting environment does not raise; no env filter clause is added to query."""
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = LogAnalyticsAdapter(config=_CONFIG)
        result = adapter.get_apim_logs("order-service")

    assert isinstance(result, list)
    assert len(result) == 2

    # Verify the query sent to Log Analytics did not include an Environment filter
    call_kwargs = MockClient.return_value.query_workspace.call_args.kwargs
    query_text = call_kwargs["query"]
    assert "Environment =~" not in query_text, "environment filter should be absent when not provided"


def test_get_apim_logs_with_environment_adds_filter():
    """When environment is provided, the KQL query should include the filter."""
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = LogAnalyticsAdapter(config=_CONFIG)
        adapter.get_apim_logs("order-service", environment="production")

    call_kwargs = MockClient.return_value.query_workspace.call_args.kwargs
    query_text = call_kwargs["query"]
    assert "production" in query_text


# ---------------------------------------------------------------------------
# Error / empty result tests
# ---------------------------------------------------------------------------


def test_get_apim_logs_connection_error_returns_empty_list():
    """If query_workspace raises, get_apim_logs returns [] without re-raising."""
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.side_effect = Exception("Connection refused")
        adapter = LogAnalyticsAdapter(config=_CONFIG)
        result = adapter.get_apim_logs("order-service")

    assert result == []


def test_get_apim_logs_empty_tables_returns_empty_list():
    """If the result has no tables (no data), an empty list is returned."""
    mock_result = MagicMock()
    mock_result.status = LogsQueryStatus.SUCCESS
    mock_result.tables = []

    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = mock_result
        adapter = LogAnalyticsAdapter(config=_CONFIG)
        result = adapter.get_apim_logs("order-service")

    assert result == []


def test_get_apim_logs_non_success_status_returns_empty_list():
    """If result status is not SUCCESS (any non-success value), return empty list."""
    mock_result = MagicMock()
    mock_result.status = "PartialError"  # anything != LogsQueryStatus.SUCCESS
    mock_result.tables = []

    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = mock_result
        adapter = LogAnalyticsAdapter(config=_CONFIG)
        result = adapter.get_apim_logs("order-service")

    assert result == []


# ---------------------------------------------------------------------------
# Credential construction tests
# ---------------------------------------------------------------------------


def test_credential_built_with_config_values():
    """DefaultAzureCredential is constructed (no explicit args — uses env or CLI session)."""
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential") as MockCred, \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient"):
        LogAnalyticsAdapter(config=_CONFIG)

    MockCred.assert_called_once_with()


def test_env_placeholders_expanded_from_os_environ(monkeypatch):
    """${AZURE_*} placeholders in config are resolved from os.environ."""
    monkeypatch.setenv("AZURE_TENANT_ID", "real-tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "real-client")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "real-secret")
    monkeypatch.setenv("LOG_ANALYTICS_WORKSPACE_ID", "real-ws")

    config_with_placeholders = {
        "workspace_id": "${LOG_ANALYTICS_WORKSPACE_ID}",
        "tenant_id": "${AZURE_TENANT_ID}",
        "client_id": "${AZURE_CLIENT_ID}",
        "client_secret": "${AZURE_CLIENT_SECRET}",
        "default_time_range_minutes": 30,
    }

    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential") as MockCred, \
         patch("corvin.evidence.log_analytics_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = LogAnalyticsAdapter(config=config_with_placeholders)
        adapter.get_apim_logs("svc")

    MockCred.assert_called_once_with()  # DefaultAzureCredential takes no args
    call_kwargs = MockClient.return_value.query_workspace.call_args.kwargs
    assert call_kwargs["workspace_id"] == "real-ws"

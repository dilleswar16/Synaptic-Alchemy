"""
Slice 4b – Azure Activity Log adapter tests.

Uses unittest.mock.patch to mock ClientSecretCredential and LogsQueryClient
so no live Azure workspace is required.  Tests cover:
  - Successful query returns list of row dicts keyed by column name.
  - query_workspace exception returns empty list (graceful degradation).
  - Empty tables list in result returns empty list.
  - Non-SUCCESS status returns empty list.
  - service_name filter appears in the KQL query.
  - env-var placeholders in config are expanded from os.environ.
  - Unconfigured client (bad credentials) returns empty list.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from azure.monitor.query import LogsQueryStatus

from corvin.evidence.azure_activity_adapter import AzureActivityAdapter

# ---------------------------------------------------------------------------
# Shared config and helpers
# ---------------------------------------------------------------------------

_CONFIG = {
    "workspace_id": "ws-activity-test",
    "tenant_id": "tenant-abc",
    "client_id": "client-abc",
    "client_secret": "secret-abc",
    "default_time_range_minutes": 60,
    "max_events": 100,
}

_COLUMNS = ["TimeGenerated", "OperationNameValue", "ActivityStatusValue", "ResourceGroup"]
_ROWS = [
    ["2026-04-04T00:01:00Z", "Microsoft.Web/sites/restart/action", "Succeeded", "rg-order"],
    ["2026-04-04T00:00:00Z", "Microsoft.Web/sites/config/write", "Succeeded", "rg-order"],
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


def test_get_recent_changes_returns_list_of_dicts():
    """Successful query returns each row as a dict keyed by column name."""
    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = AzureActivityAdapter(config=_CONFIG)
        result = adapter.get_recent_changes("order-service")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["OperationNameValue"] == "Microsoft.Web/sites/restart/action"
    assert result[0]["ActivityStatusValue"] == "Succeeded"
    assert result[1]["OperationNameValue"] == "Microsoft.Web/sites/config/write"


def test_get_recent_changes_service_name_in_kql_query():
    """The KQL query sent to Log Analytics contains the service_name filter."""
    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = AzureActivityAdapter(config=_CONFIG)
        adapter.get_recent_changes("order-service")

    call_kwargs = MockClient.return_value.query_workspace.call_args.kwargs
    query_text = call_kwargs["query"]
    assert "order-service" in query_text
    assert "AzureActivity" in query_text


def test_get_recent_changes_with_custom_time_range():
    """time_range_minutes overrides config default and appears in the KQL query."""
    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = AzureActivityAdapter(config=_CONFIG)
        adapter.get_recent_changes("order-service", time_range_minutes=15)

    call_kwargs = MockClient.return_value.query_workspace.call_args.kwargs
    query_text = call_kwargs["query"]
    assert "15m" in query_text


# ---------------------------------------------------------------------------
# Error / empty result tests
# ---------------------------------------------------------------------------


def test_get_recent_changes_connection_error_returns_empty_list():
    """If query_workspace raises, get_recent_changes returns [] without re-raising."""
    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.side_effect = Exception("Connection refused")
        adapter = AzureActivityAdapter(config=_CONFIG)
        result = adapter.get_recent_changes("order-service")

    assert result == []


def test_get_recent_changes_empty_tables_returns_empty_list():
    """If the result has no tables, an empty list is returned."""
    mock_result = MagicMock()
    mock_result.status = LogsQueryStatus.SUCCESS
    mock_result.tables = []

    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = mock_result
        adapter = AzureActivityAdapter(config=_CONFIG)
        result = adapter.get_recent_changes("order-service")

    assert result == []


def test_get_recent_changes_non_success_status_returns_empty_list():
    """If result status is not SUCCESS, return empty list."""
    mock_result = MagicMock()
    mock_result.status = "PartialError"  # anything != LogsQueryStatus.SUCCESS
    mock_result.tables = []

    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential"), \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = mock_result
        adapter = AzureActivityAdapter(config=_CONFIG)
        result = adapter.get_recent_changes("order-service")

    assert result == []


def test_get_recent_changes_unconfigured_client_returns_empty_list():
    """When ClientSecretCredential raises (empty creds), get_recent_changes returns []."""
    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential") as MockCred:
        MockCred.side_effect = ValueError("client_id required")
        adapter = AzureActivityAdapter(config=_CONFIG)
        result = adapter.get_recent_changes("order-service")

    assert result == []


# ---------------------------------------------------------------------------
# Credential and env-var tests
# ---------------------------------------------------------------------------


def test_credential_built_with_config_values():
    """ClientSecretCredential is constructed using tenant_id, client_id, client_secret."""
    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential") as MockCred, \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient"):
        AzureActivityAdapter(config=_CONFIG)

    MockCred.assert_called_once_with(
        tenant_id="tenant-abc",
        client_id="client-abc",
        client_secret="secret-abc",
    )


def test_env_placeholders_expanded_from_os_environ(monkeypatch):
    """${AZURE_*} placeholders in config are resolved from os.environ."""
    monkeypatch.setenv("AZURE_TENANT_ID", "real-tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "real-client")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "real-secret")
    monkeypatch.setenv("AZURE_ACTIVITY_WORKSPACE_ID", "real-ws-activity")

    config_with_placeholders = {
        "workspace_id": "${AZURE_ACTIVITY_WORKSPACE_ID}",
        "tenant_id": "${AZURE_TENANT_ID}",
        "client_id": "${AZURE_CLIENT_ID}",
        "client_secret": "${AZURE_CLIENT_SECRET}",
        "default_time_range_minutes": 60,
        "max_events": 100,
    }

    with patch("corvin.evidence.azure_activity_adapter.ClientSecretCredential") as MockCred, \
         patch("corvin.evidence.azure_activity_adapter.LogsQueryClient") as MockClient:
        MockClient.return_value.query_workspace.return_value = _make_success_result()
        adapter = AzureActivityAdapter(config=config_with_placeholders)
        adapter.get_recent_changes("svc")

    MockCred.assert_called_once_with(
        tenant_id="real-tenant",
        client_id="real-client",
        client_secret="real-secret",
    )
    call_kwargs = MockClient.return_value.query_workspace.call_args.kwargs
    assert call_kwargs["workspace_id"] == "real-ws-activity"

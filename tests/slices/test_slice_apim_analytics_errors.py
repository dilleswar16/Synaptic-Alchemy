from __future__ import annotations

from unittest.mock import MagicMock, patch

from corvin.evidence.apim_analytics_adapter import APIMAnalyticsAdapter

_LA_CONFIG = {
    "workspace_id": "test-ws",
    "tenant_id": "test-tenant",
    "client_id": "test-client",
    "client_secret": "test-secret",
    "default_time_range_minutes": 30,
}


def _make_la_query_result(rows, column_names):
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


def test_apim_analytics_query_template_surfaces_path_not_found_error():
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), patch(
        "corvin.evidence.log_analytics_adapter.LogsQueryClient"
    ) as mock_client:
        mock_client.return_value.query_workspace.side_effect = Exception(
            "(PathNotFoundError) The requested path does not exist"
        )
        adapter = APIMAnalyticsAdapter(config=_LA_CONFIG)
        result = adapter.query_template("traffic_over_time", time_range_minutes=60, api_filter="all")

    assert result["row_count"] == 0
    assert result["rows"] == []
    assert "error" in result
    assert "PathNotFoundError" in str(result["error"])
    assert result.get("diagnostics", {}).get("code") == "path_not_found"


def test_apim_analytics_query_template_empty_success_has_no_error():
    mock_result = _make_la_query_result([], ["TimeGenerated", "Requests"])

    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), patch(
        "corvin.evidence.log_analytics_adapter.LogsQueryClient"
    ) as mock_client:
        mock_client.return_value.query_workspace.return_value = mock_result
        adapter = APIMAnalyticsAdapter(config=_LA_CONFIG)
        result = adapter.query_template("traffic_over_time", time_range_minutes=60, api_filter="all")

    assert result["row_count"] == 0
    assert result["rows"] == []
    assert "error" not in result


def test_apim_analytics_query_template_returns_config_missing_when_no_workspace():
    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), patch(
        "corvin.evidence.log_analytics_adapter.LogsQueryClient"
    ) as mock_client:
        adapter = APIMAnalyticsAdapter(config={})
        with patch.object(adapter, "_resolve_workspace_and_table", return_value=("", "ApiManagementGatewayLogs")):
            result = adapter.query_template("traffic_over_time", time_range_minutes=60, api_filter="all")

    assert result["row_count"] == 0
    assert result["rows"] == []
    assert result.get("diagnostics", {}).get("code") == "config_missing"
    mock_client.return_value.query_workspace.assert_not_called()


def test_apim_analytics_query_template_uses_resolved_workspace_from_service_hint():
    mock_result = _make_la_query_result([], ["TimeGenerated", "Requests"])

    with patch("corvin.evidence.log_analytics_adapter.DefaultAzureCredential"), patch(
        "corvin.evidence.log_analytics_adapter.LogsQueryClient"
    ) as mock_client, patch(
        "corvin.evidence.apim_analytics_adapter.resolve_log_source_config"
    ) as resolve_cfg:
        mock_client.return_value.query_workspace.return_value = mock_result
        resolve_cfg.return_value = {
            "workspace_id": "resolved-ws",
            "apim_table": "ApiManagementGatewayLogs",
            "connector_role": "apim_logs",
        }
        adapter = APIMAnalyticsAdapter(config={})
        adapter.query_template("traffic_over_time", time_range_minutes=60, api_filter="fundapis")

    kwargs = mock_client.return_value.query_workspace.call_args.kwargs
    assert kwargs["workspace_id"] == "resolved-ws"

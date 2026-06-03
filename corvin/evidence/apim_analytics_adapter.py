"""
APIM Analytics Adapter — Named KQL template executor.

Wraps LogAnalyticsAdapter with a library of reusable APIM-focused KQL queries.

Each template accepts `time_range_minutes` and `api_filter` parameters and
returns a unified response dict that the frontend chart renderer can consume
directly without any post-processing:

    {
        "rows":               list[dict],   # query result rows
        "columns":            list[str],    # column names in order
        "chart_type":         str,          # "area"|"bar"|"pie"|"heatmap"|"table"|"tiles"
        "title":              str,          # human-readable chart title
        "subtitle":           str,          # chart subtitle / description
        "template_name":      str,          # which template was executed
        "time_range_minutes": int,
        "api_filter":         str,
        "row_count":          int,
    }
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from corvin.connectors.config_resolver import ROLE_APIM_LOGS, infer_connector_role, resolve_log_source_config
from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter
from corvin.storage.db import get_session
from corvin.storage.models import LogSourceRow

_log = logging.getLogger(__name__)

# ── KQL Template Library ──────────────────────────────────────────────────────
# Format: template_name → (kql_str, chart_type, title, subtitle)
# Placeholders in kql_str:
#   {minutes}            → int (lookback window)
#   {api_scope_clause}   → str (optional ApiId filter clause)
#
# NOTE: KQL regex patterns use {{}} to escape the Python .format() braces.

_TEMPLATES: dict[str, tuple[str, str, str, str]] = {

    "kpi_summary": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    TotalRequests     = count(),\n'
        '    SuccessRate       = round(100.0 * countif(IsRequestSuccess == true) / count(), 1),\n'
        '    ErrorCount        = countif(ResponseCode >= 400),\n'
        '    AvgResponseTimeMs = round(avg(TotalTime), 0),\n'
        '    UniqueMembers     = dcount(extract(@"/members/([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}})", 1, Url))',
        "tiles",
        "📊 APIM Key Metrics",
        "Headline numbers for all APIs in the selected time window.",
    ),

    "traffic_over_time": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        "    ['Total Requests'] = count(),\n"
        '    Success            = countif(IsRequestSuccess == true),\n'
        '    Errors             = countif(IsRequestSuccess == false)\n'
        '    by bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "📈 Request Traffic Over Time",
        "Hourly request volume split by success and failure.",
    ),

    "success_rate": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize SuccessRate = round(100.0 * countif(IsRequestSuccess == true) / count(), 1)\n'
        '    by bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "✅ Success Rate % Over Time",
        "Percentage of requests returning 2xx per hour. Sustained drop below 99% warrants investigation.",
    ),

    "response_code_distribution": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend ResponseCategory = case(\n'
        '    ResponseCode between (200 .. 299), "2xx Success",\n'
        '    ResponseCode between (400 .. 499), "4xx Client Error",\n'
        '    ResponseCode between (500 .. 599), "5xx Server Error",\n'
        '    "Other")\n'
        '| summarize RequestCount = count() by ResponseCategory\n'
        '| order by RequestCount desc',
        "pie",
        "🔵 Response Code Distribution",
        "Breakdown of all responses by HTTP status category.",
    ),

    "api_traffic_split": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize RequestCount = count() by ApiId\n'
        '| order by RequestCount desc',
        "pie",
        "↔️ Traffic Split by API",
        "Proportion of traffic going to each API over the selected period.",
    ),

    "unique_members_by_fund": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend MemberUUID = extract(@"/members/([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}})", 1, Url)\n'
        '| extend FundCode   = toupper(extract(@"/schemes/([^/]+)/", 1, Url))\n'
        '| extend FundCode   = iff(FundCode == "CARESUPER", "CARE", FundCode)\n'
        '| where isnotempty(MemberUUID) and isnotempty(FundCode)\n'
        '| summarize UniqueMembers = dcount(MemberUUID) by FundCode, bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "👥 Unique Members by Fund Over Time",
        "Distinct member UUIDs per fund bucketed hourly — shows which fund is active and how member reach evolves.",
    ),

    "requests_by_fund": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend FundCode = toupper(extract(@"/schemes/([^/]+)/", 1, Url))\n'
        '| extend FundCode = iff(FundCode == "CARESUPER", "CARE", FundCode)\n'
        '| where isnotempty(FundCode)\n'
        '| summarize\n'
        '    RequestCount  = count(),\n'
        '    ErrorCount    = countif(ResponseCode >= 400),\n'
        '    UniqueMembers = dcount(extract(@"/members/([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}})", 1, Url))\n'
        '    by FundCode\n'
        '| order by RequestCount desc',
        "bar",
        "🏦 Requests by Fund Code",
        "Total requests, errors, and unique member reach per superannuation fund.",
    ),

    "top_members": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend FundCode   = toupper(extract(@"/schemes/([^/]+)/", 1, Url))\n'
        '| extend FundCode   = iff(FundCode == "CARESUPER", "CARE", FundCode)\n'
        '| extend MemberUUID = extract(@"/members/([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}})", 1, Url)\n'
        '| where isnotempty(MemberUUID)\n'
        '| summarize\n'
        '    RequestCount = count(),\n'
        '    ErrorCount   = countif(ResponseCode >= 400),\n'
        '    LastSeen     = max(TimeGenerated),\n'
        '    FundCode     = any(FundCode)\n'
        '    by MemberUUID\n'
        '| order by RequestCount desc\n'
        '| take 10',
        "table",
        "🏆 Top 10 Members by Request Volume",
        "Members with the highest request count — review for unusual volumes or repeated errors.",
    ),

    "fund_activity_heatmap": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend FundCode  = toupper(extract(@"/schemes/([^/]+)/", 1, Url))\n'
        '| extend FundCode  = iff(FundCode == "CARESUPER", "CARE", FundCode)\n'
        '| where isnotempty(FundCode)\n'
        '| extend HourOfDay = datetime_part("Hour", TimeGenerated)\n'
        '| summarize RequestCount = count() by FundCode, HourOfDay\n'
        '| order by FundCode asc, HourOfDay asc',
        "heatmap",
        "🕒 Fund Activity by Hour of Day",
        "Request volume per fund by hour of day — useful for understanding peak load patterns.",
    ),

    "partnerapis_operations": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    Requests = count(),\n'
        '    Success  = countif(IsRequestSuccess == true),\n'
        '    Errors   = countif(ResponseCode >= 400)\n'
        '    by OperationId\n'
        '| order by Requests desc',
        "bar",
        "🔎 API Operations Breakdown",
        "Per-operation request, success, and error counts for selected APIs.",
    ),

    "fundapis_traffic": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    TotalRequests = count(),\n'
        '    Errors        = countif(ResponseCode >= 400),\n'
        '    ErrorRate_pct = round(100.0 * countif(ResponseCode >= 400) / count(), 1)\n'
        '    by bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "💰 API Traffic & Error Rate",
        "Hourly request and error volume for selected APIs.",
    ),

    "fundapis_operations_by_fund": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend FundCode = toupper(extract(@"/schemes/([^/]+)/", 1, Url))\n'
        '| extend FundCode = iff(FundCode == "CARESUPER", "CARE", FundCode)\n'
        '| summarize\n'
        '    RequestCount  = count(),\n'
        '    ErrorCount    = countif(ResponseCode >= 400),\n'
        '    ErrorRate_pct = round(100.0 * countif(ResponseCode >= 400) / count(), 1),\n'
        '    AvgTime_ms    = round(avg(TotalTime), 0)\n'
        '    by OperationId, FundCode\n'
        '| order by FundCode asc, OperationId asc',
        "table",
        "📋 API Operations by Fund Code",
        "Per-operation and per-fund breakdown for selected APIs including error rates and latency.",
    ),

    "latency_percentiles": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    P50_ms = percentile(TotalTime, 50),\n'
        '    P95_ms = percentile(TotalTime, 95),\n'
        '    P99_ms = percentile(TotalTime, 99),\n'
        '    Avg_ms = round(avg(TotalTime), 0)\n'
        '    by bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "⏱ Latency Percentiles Over Time (ms)",
        "P50 is median response time; P99 is worst-case. A large P99/P50 gap indicates tail latency.",
    ),

    "backend_vs_overhead": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        "    BackendTime_ms  = round(avg(BackendTime), 0),\n"
        "    APIMOverhead_ms = round(avg(TotalTime - BackendTime), 0)\n"
        '    by bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "⚙️ Backend Time vs APIM Gateway Overhead",
        "Time in backend service vs APIM gateway processing. High overhead = policy or routing issues.",
    ),

    "slowest_operations": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    RequestCount = count(),\n'
        '    AvgTime_ms   = round(avg(TotalTime), 0),\n'
        '    P95_ms       = percentile(TotalTime, 95),\n'
        '    P99_ms       = percentile(TotalTime, 99)\n'
        '    by OperationId, ApiId\n'
        '| order by P95_ms desc\n'
        '| take 15',
        "table",
        "🐢 Slowest Operations (by P95 latency)",
        "Top 15 operations by P95 latency — start here when prioritising backend performance improvements.",
    ),

    "error_rate": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    TotalRequests = count(),\n'
        '    ErrorCount    = countif(ResponseCode >= 400),\n'
        '    ErrorRate_pct = round(100.0 * countif(ResponseCode >= 400) / count(), 2)\n'
        '    by bin(TimeGenerated, 1h)\n'
        '| order by TimeGenerated asc',
        "area",
        "📉 Error Rate Over Time",
        "Hourly error rate % alongside raw counts. Spikes correlate with incidents or backend degradation.",
    ),

    "errors_by_code": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| where ResponseCode >= 400\n'
        '| summarize ErrorCount = count() by ResponseCode, OperationId, ApiId\n'
        '| order by ErrorCount desc',
        "bar",
        "🚨 Errors by Response Code & Operation",
        "HTTP error codes per operation — helps triage 4xx vs 5xx issues.",
    ),

    "error_origin": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| where ResponseCode >= 400\n'
        '| extend ErrorOrigin = case(\n'
        '    BackendResponseCode >= 400,                        "Backend Error",\n'
        '    ResponseCode >= 400 and BackendResponseCode < 400, "APIM Policy Error",\n'
        '    isempty(tostring(BackendResponseCode)),            "Blocked at Gateway",\n'
        '    "Other")\n'
        '| summarize Count = count() by ErrorOrigin, ResponseCode, ApiId\n'
        '| order by Count desc',
        "bar",
        "🔍 Error Origin — Backend vs APIM vs Gateway",
        "Classifies each error as backend fault, APIM policy rejection, or gateway block.",
    ),

    "top_caller_ips": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize\n'
        '    RequestCount = count(),\n'
        '    ErrorCount   = countif(ResponseCode >= 400)\n'
        '    by CallerIpAddress\n'
        '| order by RequestCount desc\n'
        '| take 20',
        "table",
        "🌐 Top 20 Caller IP Addresses",
        "IPs making the most requests. Unexpected sources or high error rates may indicate probing.",
    ),

    "tls_versions": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| summarize RequestCount = count() by ClientTlsVersion\n'
        '| order by RequestCount desc',
        "pie",
        "🔒 TLS Version Distribution",
        "All traffic should use TLS 1.3. Any older version is a security compliance risk.",
    ),

    "traffic_source": (
        'ApiManagementGatewayLogs\n'
        '| where TimeGenerated >= ago({minutes}m)\n'
        '{api_scope_clause}'
        '| extend TrafficSource = tostring(parse_json(BackendRequestHeaders)["X-Traffic-Source"])\n'
        '| summarize RequestCount = count() by TrafficSource\n'
        '| order by RequestCount desc',
        "pie",
        "🚦 Traffic Source (X-Traffic-Source header)",
        "Which client systems or environments are calling the API.",
    ),
}

# Public list for LLM tool description
TEMPLATE_NAMES: list[str] = sorted(_TEMPLATES.keys())


class APIMAnalyticsAdapter(LogAnalyticsAdapter):
    """APIM-focused analytics adapter with named KQL templates.

    Inherits workspace_id and LogsQueryClient from LogAnalyticsAdapter.
    Adds a library of pre-validated APIM KQL templates
    and a generic raw-KQL execution path.
    """

    def query_template(
        self,
        template_name: str,
        time_range_minutes: int = 1440,
        api_filter: str = "all",
        chart_type_override: str | None = None,
    ) -> dict[str, Any]:
        """Execute a named KQL template and return structured chart data.

        Args:
            template_name:      One of the keys in TEMPLATE_NAMES.
            time_range_minutes: Lookback window (default 1440 = 24h / today).
            api_filter:         "all" or a concrete ApiId value.
            chart_type_override: If set, overrides the template's default chart type.

        Returns:
            Unified chart payload: {rows, columns, chart_type, title, subtitle, ...}
        """
        if template_name not in _TEMPLATES:
            available = ", ".join(TEMPLATE_NAMES)
            return {
                "error": f"Unknown template {template_name!r}.",
                "available_templates": available,
                "template_name": template_name,
                "rows": [],
                "columns": [],
                "chart_type": "table",
                "title": "Unknown Template",
                "subtitle": "",
                "row_count": 0,
                "time_range_minutes": time_range_minutes,
                "api_filter": api_filter,
            }

        query_tmpl, default_chart_type, title, subtitle = _TEMPLATES[template_name]
        chart_type = chart_type_override if chart_type_override else default_chart_type
        workspace_id, apim_table = self._resolve_workspace_and_table(api_filter)

        if not workspace_id:
            return {
                "rows": [],
                "columns": [],
                "chart_type": chart_type,
                "title": title,
                "subtitle": subtitle,
                "template_name": template_name,
                "time_range_minutes": time_range_minutes,
                "api_filter": api_filter,
                "row_count": 0,
                "error": "APIM analytics connector is not configured with a workspace_id.",
                "diagnostics": {
                    "code": "config_missing",
                    "hint": "Configure an active azure_monitor connector with connector_role=apim_logs and workspace_id.",
                },
            }

        # Build optional API scope clause; supports:
        # - "all" (no ApiId restriction)
        # - "api-id" (single)
        # - "api-a,api-b" (comma-separated list)
        api_scope_clause = ""
        if api_filter and api_filter.lower() not in ("all", ""):
            requested = [item.strip().replace('"', "") for item in api_filter.split(",") if item.strip()]
            if len(requested) == 1:
                api_scope_clause = f'| where ApiId == "{requested[0]}"\n'
            elif requested:
                quoted = ", ".join(f'"{item}"' for item in requested)
                api_scope_clause = f"| where ApiId in ({quoted})\\n"

        query = query_tmpl.replace("ApiManagementGatewayLogs", apim_table).format(
            minutes=time_range_minutes,
            api_scope_clause=api_scope_clause,
        )

        rows = self._run_kql(query, time_range_minutes, workspace_id=workspace_id)
        columns = list(rows[0].keys()) if rows else []

        response = {
            "rows": rows,
            "columns": columns,
            "chart_type": chart_type,
            "title": title,
            "subtitle": subtitle,
            "template_name": template_name,
            "time_range_minutes": time_range_minutes,
            "api_filter": api_filter,
            "row_count": len(rows),
        }
        if not rows and self._last_error:
            response["error"] = self._user_error_message(self._last_error)
            response["diagnostics"] = self._build_diagnostics(self._last_error)
        return response

    def run_kql_raw(
        self,
        kql: str,
        time_range_minutes: int = 1440,
        chart_type: str = "table",
        title: str = "Custom Query",
        subtitle: str = "",
    ) -> dict[str, Any]:
        """Execute an arbitrary KQL query and return structured chart data.

        Use this when the user asks a question that doesn't match any named template.
        The LLM should generate a valid KQL query targeting ApiManagementGatewayLogs.
        """
        workspace_id, _ = self._resolve_workspace_and_table("all")
        if not workspace_id:
            return {
                "rows": [],
                "columns": [],
                "chart_type": chart_type,
                "title": title,
                "subtitle": subtitle,
                "template_name": "custom",
                "time_range_minutes": time_range_minutes,
                "api_filter": "all",
                "row_count": 0,
                "error": "APIM analytics connector is not configured with a workspace_id.",
                "diagnostics": {
                    "code": "config_missing",
                    "hint": "Configure an active azure_monitor connector with connector_role=apim_logs and workspace_id.",
                },
            }

        rows = self._run_kql(kql, time_range_minutes, workspace_id=workspace_id)
        columns = list(rows[0].keys()) if rows else []
        response = {
            "rows": rows,
            "columns": columns,
            "chart_type": chart_type,
            "title": title,
            "subtitle": subtitle,
            "template_name": "custom",
            "time_range_minutes": time_range_minutes,
            "api_filter": "all",
            "row_count": len(rows),
        }
        if not rows and self._last_error:
            response["error"] = self._user_error_message(self._last_error)
            response["diagnostics"] = self._build_diagnostics(self._last_error)
        return response

    # ── Internal ──────────────────────────────────────────────────────────────

    _last_error: str | None = None

    def _resolve_workspace_and_table(self, api_filter: str) -> tuple[str, str]:
        # 1) explicit constructor config wins
        workspace_id = str(self._workspace_id or "").strip()
        apim_table = str(self._config.get("apim_table") or "ApiManagementGatewayLogs").strip() or "ApiManagementGatewayLogs"
        if workspace_id:
            return workspace_id, apim_table

        # 2) service-specific connector (derived from api_filter) when available
        api_tokens = [item.strip() for item in str(api_filter or "").split(",") if item.strip()]
        service_hint = api_tokens[0] if api_tokens and api_tokens[0].lower() != "all" else ""
        if service_hint:
            cfg = resolve_log_source_config(
                service_hint,
                source_type="azure_monitor",
                role=ROLE_APIM_LOGS,
                fallback={},
            )
            ws = str(cfg.get("workspace_id") or "").strip()
            if ws:
                table = str(cfg.get("apim_table") or "ApiManagementGatewayLogs").strip() or "ApiManagementGatewayLogs"
                return ws, table

        # 3) fallback: any active APIM logs connector in DB
        try:
            with get_session() as db:
                rows = db.query(LogSourceRow).filter_by(source_type="azure_monitor", is_active=True).all()
                for row in rows:
                    role = infer_connector_role(row.source_type, row.config_json or {}, row.display_name or "")
                    if role != ROLE_APIM_LOGS:
                        continue
                    cfg = row.config_json or {}
                    ws = str(cfg.get("workspace_id") or "").strip()
                    if ws:
                        table = str(cfg.get("apim_table") or "ApiManagementGatewayLogs").strip() or "ApiManagementGatewayLogs"
                        return ws, table
        except Exception:
            pass

        return "", apim_table

    @staticmethod
    def _build_diagnostics(error_message: str) -> dict[str, str]:
        msg = str(error_message or "").strip()
        low = msg.lower()
        if "pathnotfounderror" in low or "requested path does not exist" in low:
            return {
                "code": "path_not_found",
                "hint": "Workspace or APIM table path is unavailable. Verify workspace_id and APIM diagnostics routing to Log Analytics.",
            }
        if "defaultazurecredential failed" in low or "interactive authentication is needed" in low:
            return {
                "code": "auth_failed",
                "hint": "Azure authentication failed. Re-authenticate with az login or configure service principal credentials.",
            }
        return {
            "code": "query_failed",
            "hint": "APIM analytics query failed. Check Log Analytics workspace configuration and permissions.",
        }

    @staticmethod
    def _user_error_message(error_message: str) -> str:
        msg = str(error_message or "").strip()
        low = msg.lower()
        if "pathnotfounderror" in low or "requested path does not exist" in low:
            return "PathNotFoundError: Log Analytics workspace/table path was not found."
        if "defaultazurecredential failed" in low or "interactive authentication is needed" in low:
            return "Azure authentication failed for Log Analytics. Re-authenticate and retry."
        first_line = msg.splitlines()[0] if msg else "APIM analytics query failed"
        return first_line[:280]

    def _run_kql(self, query: str, time_range_minutes: int, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Execute a KQL query against the configured Log Analytics workspace."""
        self._last_error = None
        try:
            from azure.monitor.query import LogsQueryStatus
        except ImportError:
            self._last_error = "azure-monitor-query not installed"
            _log.warning("APIMAnalyticsAdapter: %s", self._last_error)
            return []

        if self._client is None:
            self._last_error = "LogsQueryClient not configured"
            _log.warning("APIMAnalyticsAdapter: %s — returning [].", self._last_error)
            return []

        try:
            effective_workspace = str(workspace_id or self._workspace_id or "").strip()
            if not effective_workspace:
                self._last_error = "workspace_id is empty"
                _log.warning("APIMAnalyticsAdapter._run_kql skipped: %s", self._last_error)
                return []
            result = self._client.query_workspace(
                workspace_id=effective_workspace,
                query=query,
                timespan=timedelta(minutes=time_range_minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS:
                partial_error = getattr(result, "partial_error", None) or getattr(result, "error", None)
                if partial_error:
                    self._last_error = str(partial_error)
                else:
                    self._last_error = f"Log Analytics query status: {result.status}"
                _log.warning("APIMAnalyticsAdapter._run_kql non-success status: %s", self._last_error)
                return []
            if not result.tables:
                return []
            log_table = result.tables[0]
            cols = [c.name if hasattr(c, "name") else c for c in log_table.columns]
            return [
                {
                    k: (v.isoformat() if hasattr(v, "isoformat") else v)
                    for k, v in zip(cols, row)
                }
                for row in log_table.rows
            ]
        except Exception as exc:
            self._last_error = str(exc)
            _log.warning("APIMAnalyticsAdapter._run_kql failed: %s", exc)
            return []



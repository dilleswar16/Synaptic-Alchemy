"""Read-only Azure REST client: Resource Manager, diagnostic settings, metrics, Log Analytics, activity log, alert rules.

Uses Keigan's own identity (managed / workload identity) with only Reader, Monitoring Reader and Log Analytics Reader.
Lean by design: plain REST through ``httpx`` instead of the heavy ``azure-mgmt-*`` SDKs.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from keigan.config.logging_config import current_correlation_id
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.azure_identity_provider import AzureCredentialProvider
from keigan.integrations.telemetry_gateway import ChangeEvent, ConnectionTestResult, MetricQueryResult, MetricSeries
from keigan.utils.time_utils import ensure_utc

logger = logging.getLogger(__name__)

RESOURCE_MANAGER_URL = "https://management.azure.com"
RESOURCE_MANAGER_SCOPE = "https://management.azure.com/.default"
LOG_ANALYTICS_URL = "https://api.loganalytics.io/v1"
LOG_ANALYTICS_SCOPE = "https://api.loganalytics.io/.default"
MAXIMUM_PAGES = 20


AZURE_ERROR_CODE_BY_STATUS = {403: "azure_forbidden", 404: "azure_not_found", 429: "azure_throttled", 503: "azure_throttled"}
AZURE_ADVICE_BY_STATUS = {
    401: "Azure did not accept Keigan's sign-in for {target}. Ask a Keigan admin to check the identity Keigan uses to reach Azure.",
    403: "Azure refused access to {target}. Keigan's identity needs a read role on it (the check shows which one).",
    404: "Azure could not find {target}. Check that it still exists and that the subscription and resource group names are right.",
    429: "Azure is busy and asked Keigan to slow down while reading {target}. Try again in a minute.",
    503: "Azure is busy and asked Keigan to slow down while reading {target}. Try again in a minute.",
}
AZURE_ADVICE_OTHERWISE = "Azure returned an error ({status}) for {target}. Try again; if it keeps failing, ask a Keigan admin."


@dataclass(frozen=True)
class AlertRuleReadResult:
    """Alert rules read from one resource group. ``failure_codes`` holds one error code for each rule collection Azure would not return; those rules are missing."""

    rules_by_collection: dict[str, list[dict[str, Any]]]
    failure_codes: tuple[str, ...] = ()


@dataclass
class AccessCheckResult:
    check_name: str  # list_resources | read_activity_log | read_metrics | query_workspace
    passed: bool
    message: str
    missing_role_name: str | None = None


def _isoformat_z(timestamp: datetime) -> str:
    return (ensure_utc(timestamp) or timestamp).strftime("%Y-%m-%dT%H:%M:%SZ")


class AzureClient:
    def __init__(self, credential_provider: AzureCredentialProvider):
        self.credential_provider = credential_provider

    # ── HTTP plumbing ──────────────────────────────────────────────────────────
    async def _request(
        self, method: str, url: str, *, scope: str, tenant_id: str | None, json_body: Any = None, timeout_seconds: float = 30
    ) -> httpx.Response:
        access_token = await self.credential_provider.get_access_token(scope, tenant_id)
        async with httpx.AsyncClient(timeout=timeout_seconds) as http_client:
            for attempt_index in range(4):
                response = await http_client.request(method, url, headers={"Authorization": f"Bearer {access_token}"}, json=json_body)
                if response.status_code not in (429, 503) or attempt_index == 3:
                    return response
                retry_after_seconds = float(response.headers.get("Retry-After", 2 ** (attempt_index + 1)))
                await asyncio.sleep(min(retry_after_seconds, 30))
        return response

    async def _get_all_pages(self, url: str, tenant_id: str | None) -> list[dict[str, Any]]:
        collected_items: list[dict[str, Any]] = []
        next_page_url: str | None = url
        for _ in range(MAXIMUM_PAGES):
            if not next_page_url:
                break
            response = await self._request("GET", next_page_url, scope=RESOURCE_MANAGER_SCOPE, tenant_id=tenant_id)
            self._raise_for_status(response, next_page_url)
            response_body = response.json()
            collected_items.extend(response_body.get("value", []))
            next_page_url = response_body.get("nextLink")
        return collected_items

    @staticmethod
    def _raise_for_status(response: httpx.Response, requested_url: str) -> None:
        if response.status_code < 400:
            return
        target = requested_url.split("?")[0][-160:]
        # Azure's own text names identities and role actions, so it goes to the log; the user gets what to do about it and a reference to quote.
        logger.warning("Azure returned %s for %s: %s", response.status_code, target, response.text[:500])
        advice = AZURE_ADVICE_BY_STATUS.get(response.status_code, AZURE_ADVICE_OTHERWISE).format(target=target, status=response.status_code)
        raise IntegrationException(
            f"{advice} Reference {current_correlation_id() or 'none'}.", error_code=AZURE_ERROR_CODE_BY_STATUS.get(response.status_code, "azure_request_failed")
        )

    # ── Resource Manager ───────────────────────────────────────────────────────
    async def list_resource_group_resources(self, tenant_id: str | None, subscription_id: str, resource_group_name: str) -> list[dict[str, Any]]:
        return await self._get_all_pages(
            f"{RESOURCE_MANAGER_URL}/subscriptions/{subscription_id}/resourceGroups/{quote(resource_group_name)}/resources?api-version=2021-04-01",
            tenant_id,
        )

    async def get_subscription_display_name(self, tenant_id: str | None, subscription_id: str) -> str | None:
        response = await self._request(
            "GET", f"{RESOURCE_MANAGER_URL}/subscriptions/{subscription_id}?api-version=2022-12-01", scope=RESOURCE_MANAGER_SCOPE, tenant_id=tenant_id
        )
        return response.json().get("displayName") if response.status_code == 200 else None

    async def get_resource(self, tenant_id: str | None, resource_id: str, api_version: str) -> dict[str, Any]:
        response = await self._request("GET", f"{RESOURCE_MANAGER_URL}{resource_id}?api-version={api_version}", scope=RESOURCE_MANAGER_SCOPE, tenant_id=tenant_id)
        self._raise_for_status(response, resource_id)
        return response.json()

    async def get_diagnostic_settings(self, tenant_id: str | None, resource_id: str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            f"{RESOURCE_MANAGER_URL}{resource_id}/providers/Microsoft.Insights/diagnosticSettings?api-version=2021-05-01-preview",
            scope=RESOURCE_MANAGER_SCOPE,
            tenant_id=tenant_id,
        )
        if response.status_code in (400, 404):
            return []
        self._raise_for_status(response, resource_id)
        return response.json().get("value", [])

    async def get_metric_definitions(self, tenant_id: str | None, resource_id: str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            f"{RESOURCE_MANAGER_URL}{resource_id}/providers/Microsoft.Insights/metricDefinitions?api-version=2023-10-01",
            scope=RESOURCE_MANAGER_SCOPE,
            tenant_id=tenant_id,
        )
        if response.status_code in (400, 404):
            return []
        self._raise_for_status(response, resource_id)
        return [
            {
                "name": definition["name"]["value"],
                "displayName": definition["name"].get("localizedValue", definition["name"]["value"]),
                "unit": definition.get("unit"),
                "primaryAggregationType": definition.get("primaryAggregationType"),
                "supportedAggregationTypes": definition.get("supportedAggregationTypes", []),
                "dimensions": [dimension.get("value") for dimension in definition.get("dimensions", [])],
            }
            for definition in response.json().get("value", [])
        ]

    async def query_metrics(
        self,
        tenant_id: str | None,
        resource_id: str,
        metric_names: list[str],
        time_range_start: datetime,
        time_range_end: datetime,
        interval_minutes: int = 5,
        aggregation: str = "Average",
        metric_filter: str | None = None,
    ) -> MetricQueryResult:
        interval_text = f"PT{interval_minutes}M" if interval_minutes < 60 else f"PT{interval_minutes // 60}H"
        query_url = (
            f"{RESOURCE_MANAGER_URL}{resource_id}/providers/Microsoft.Insights/metrics?api-version=2023-10-01"
            f"&metricnames={quote(','.join(metric_names))}&timespan={_isoformat_z(time_range_start)}/{_isoformat_z(time_range_end)}"
            f"&interval={interval_text}&aggregation={aggregation}"
        )
        if metric_filter:
            query_url += f"&$filter={quote(metric_filter)}"
        response = await self._request("GET", query_url, scope=RESOURCE_MANAGER_SCOPE, tenant_id=tenant_id)
        self._raise_for_status(response, resource_id)
        metric_series_list: list[MetricSeries] = []
        aggregation_key = aggregation.lower()
        for metric_entry in response.json().get("value", []):
            data_points: list[tuple[datetime, float | None]] = []
            for time_series in metric_entry.get("timeseries", []):
                for data_point in time_series.get("data", []):
                    data_points.append((datetime.fromisoformat(data_point["timeStamp"].replace("Z", "+00:00")), data_point.get(aggregation_key)))
            metric_series_list.append(
                MetricSeries(metric_entry["name"]["value"], metric_entry.get("unit", ""), aggregation, sorted(data_points, key=lambda point: point[0]))
            )
        return MetricQueryResult(series=metric_series_list)

    # ── Log Analytics ──────────────────────────────────────────────────────────
    async def get_workspace_customer_id(self, tenant_id: str | None, workspace_resource_id: str) -> str | None:
        workspace_resource = await self.get_resource(tenant_id, workspace_resource_id, "2022-10-01")
        return workspace_resource.get("properties", {}).get("customerId")

    async def query_log_analytics(
        self, tenant_id: str | None, workspace_customer_id: str, kql_text: str, time_range_start: datetime, time_range_end: datetime
    ) -> tuple[list[str], list[dict[str, Any]]]:
        response = await self._request(
            "POST",
            f"{LOG_ANALYTICS_URL}/workspaces/{workspace_customer_id}/query",
            scope=LOG_ANALYTICS_SCOPE,
            tenant_id=tenant_id,
            json_body={"query": kql_text, "timespan": f"{_isoformat_z(time_range_start)}/{_isoformat_z(time_range_end)}"},
            timeout_seconds=90,
        )
        self._raise_for_status(response, f"workspace {workspace_customer_id}")
        tables = response.json().get("tables", [])
        if not tables:
            return [], []
        column_names = [column["name"] for column in tables[0].get("columns", [])]
        return column_names, [dict(zip(column_names, row_values, strict=False)) for row_values in tables[0].get("rows", [])]

    async def test_workspace_query(self, tenant_id: str | None, workspace_customer_id: str | None) -> ConnectionTestResult:
        if not workspace_customer_id:
            return ConnectionTestResult(False, "No Log Analytics workspace is linked.")
        try:
            end_time = datetime.now().astimezone()
            _, rows = await self.query_log_analytics(
                tenant_id, workspace_customer_id, "union withsource=TableName * | summarize LatestRecord=max(TimeGenerated)", end_time.replace(hour=0, minute=0), end_time
            )
        except IntegrationException as query_error:
            return ConnectionTestResult(False, query_error.detail)
        newest_timestamp_text = rows[0].get("LatestRecord") if rows else None
        newest_timestamp = datetime.fromisoformat(newest_timestamp_text.replace("Z", "+00:00")) if newest_timestamp_text else None
        return ConnectionTestResult(True, "Workspace is queryable.", newest_log_timestamp=newest_timestamp)

    async def test_metric_read(self, tenant_id: str | None, resource_id: str | None) -> ConnectionTestResult:
        if not resource_id:
            return ConnectionTestResult(False, "No Azure resource is linked.")
        try:
            metric_definitions = await self.get_metric_definitions(tenant_id, resource_id)
        except IntegrationException as metric_error:
            return ConnectionTestResult(False, metric_error.detail)
        return ConnectionTestResult(True, f"{len(metric_definitions)} metrics available.", details={"metricCount": len(metric_definitions)})

    # ── Activity log and alert rules ───────────────────────────────────────────
    async def list_activity_changes(
        self,
        tenant_id: str | None,
        subscription_id: str,
        resource_group_name: str | None,
        time_range_start: datetime,
        time_range_end: datetime,
    ) -> list[ChangeEvent]:
        event_filter = f"eventTimestamp ge '{_isoformat_z(time_range_start)}' and eventTimestamp le '{_isoformat_z(time_range_end)}'"
        if resource_group_name:
            event_filter += f" and resourceGroupName eq '{resource_group_name}'"
        activity_events = await self._get_all_pages(
            f"{RESOURCE_MANAGER_URL}/subscriptions/{subscription_id}/providers/Microsoft.Insights/eventtypes/management/values"
            f"?api-version=2015-04-01&$filter={quote(event_filter)}"
            "&$select=eventTimestamp,operationName,resourceId,status,caller,category,properties",
            tenant_id,
        )
        change_events: list[ChangeEvent] = []
        for activity_event in activity_events:
            operation_name = (activity_event.get("operationName") or {}).get("value", "")
            status_value = (activity_event.get("status") or {}).get("value", "")
            if not operation_name.lower().endswith(("/write", "/action", "/delete")) or status_value not in ("Succeeded", "Failed"):
                continue
            lowercase_operation = operation_name.lower()
            change_kind = (
                "deployment" if "deployments" in lowercase_operation or "slots" in lowercase_operation or "/publish" in lowercase_operation
                else "restart" if "restart" in lowercase_operation
                else "scaling" if "scale" in lowercase_operation or "autoscale" in lowercase_operation
                else "configuration_change"
            )
            change_events.append(
                ChangeEvent(
                    occurred_at=datetime.fromisoformat(activity_event["eventTimestamp"].replace("Z", "+00:00")),
                    change_kind=change_kind,
                    operation_name=operation_name,
                    resource_identifier=activity_event.get("resourceId", ""),
                    description=(activity_event.get("operationName") or {}).get("localizedValue", operation_name),
                    status=status_value,
                    caller=activity_event.get("caller"),
                )
            )
        return sorted(change_events, key=lambda change_event: change_event.occurred_at)

    async def list_alert_rules(self, tenant_id: str | None, subscription_id: str, resource_group_name: str) -> AlertRuleReadResult:
        base_url = f"{RESOURCE_MANAGER_URL}/subscriptions/{subscription_id}/resourceGroups/{quote(resource_group_name)}/providers/Microsoft.Insights"
        rule_collections = {
            "metric_alerts": f"{base_url}/metricAlerts?api-version=2018-03-01",
            "scheduled_query_rules": f"{base_url}/scheduledQueryRules?api-version=2023-03-15-preview",
            "activity_log_alerts": f"{base_url}/activityLogAlerts?api-version=2020-10-01",
            "action_groups": f"{base_url}/actionGroups?api-version=2023-01-01",
        }
        discovered_rules: dict[str, list[dict[str, Any]]] = {}
        failure_codes: list[str] = []
        for collection_name, collection_url in rule_collections.items():
            try:
                discovered_rules[collection_name] = await self._get_all_pages(collection_url, tenant_id)
            except IntegrationException as listing_error:
                logger.info("Could not list %s in resource group %s: %s", collection_name, resource_group_name, listing_error.detail)
                discovered_rules[collection_name] = []
                failure_codes.append(listing_error.error_code)
        return AlertRuleReadResult(discovered_rules, tuple(failure_codes))

    # ── Access verification ────────────────────────────────────────────────────
    async def verify_read_access(
        self, tenant_id: str | None, subscription_id: str, resource_group_name: str, workspace_customer_ids: list[str] | None = None
    ) -> list[AccessCheckResult]:
        access_checks: list[AccessCheckResult] = []
        discovered_resources: list[dict[str, Any]] = []
        try:
            discovered_resources = await self.list_resource_group_resources(tenant_id, subscription_id, resource_group_name)
            access_checks.append(AccessCheckResult("list_resources", True, f"{len(discovered_resources)} resources visible."))
        except IntegrationException as listing_error:
            access_checks.append(AccessCheckResult("list_resources", False, listing_error.detail, "Reader"))

        try:
            end_time = datetime.now().astimezone()
            await self.list_activity_changes(tenant_id, subscription_id, resource_group_name, end_time.replace(hour=0, minute=0), end_time)
            access_checks.append(AccessCheckResult("read_activity_log", True, "Activity log is readable."))
        except IntegrationException as activity_error:
            access_checks.append(AccessCheckResult("read_activity_log", False, activity_error.detail, "Reader"))

        if discovered_resources:
            metric_check = await self.test_metric_read(tenant_id, discovered_resources[0]["id"])
            access_checks.append(
                AccessCheckResult("read_metrics", metric_check.succeeded, metric_check.message, None if metric_check.succeeded else "Monitoring Reader")
            )
        for workspace_customer_id in workspace_customer_ids or []:
            workspace_check = await self.test_workspace_query(tenant_id, workspace_customer_id)
            access_checks.append(
                AccessCheckResult(
                    "query_workspace", workspace_check.succeeded, workspace_check.message, None if workspace_check.succeeded else "Log Analytics Reader"
                )
            )
        return access_checks

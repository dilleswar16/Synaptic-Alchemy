"""keigan/integrations/azure_client.py: each Azure refusal has its own error code, and a refused rule collection is reported, not hidden as an empty list."""

from __future__ import annotations

import httpx
import pytest

from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.azure_client import AzureClient


@pytest.mark.parametrize(("status_code", "error_code"), [(403, "azure_forbidden"), (404, "azure_not_found"), (429, "azure_throttled"), (503, "azure_throttled"), (500, "azure_request_failed")])
def test_each_azure_status_gets_its_own_error_code(status_code: int, error_code: str) -> None:
    url = "https://management.azure.com/subscriptions/s/resourceGroups/rg"
    response = httpx.Response(status_code, json={"error": {"code": "AuthorizationFailed", "message": "no access"}}, request=httpx.Request("GET", url))
    with pytest.raises(IntegrationException) as raised:
        AzureClient._raise_for_status(response, url)
    assert raised.value.error_code == error_code


async def test_a_refused_rule_collection_is_reported_and_the_other_collections_are_still_read(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_all_pages(self: AzureClient, url: str, tenant_id: str | None) -> list[dict[str, str]]:
        if "metricAlerts" in url:
            raise IntegrationException("Azure returned 403", error_code="azure_forbidden")
        return [{"name": "rule"}]

    monkeypatch.setattr(AzureClient, "_get_all_pages", get_all_pages)
    result = await AzureClient.__new__(AzureClient).list_alert_rules("tenant", "subscription", "resource-group")
    assert result.failure_codes == ("azure_forbidden",)
    assert result.rules_by_collection["metric_alerts"] == []
    assert result.rules_by_collection["scheduled_query_rules"] == [{"name": "rule"}]

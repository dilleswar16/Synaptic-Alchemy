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


RAW_AZURE_BODY = {"error": {"code": "AuthorizationFailed", "message": "The client 'aaaa-1111' with object id 'bbbb-2222' does not have authorization to perform action 'Microsoft.Insights/metricDefinitions/read'"}}


@pytest.mark.parametrize(
    ("status_code", "expected_advice"),
    [(401, "did not accept Keigan's sign-in"), (403, "refused access"), (404, "could not find"), (429, "busy"), (500, "returned an error (500)")],
)
def test_azure_failure_text_is_plain_and_keeps_the_provider_text_out_of_the_user_message(status_code: int, expected_advice: str, caplog: pytest.LogCaptureFixture) -> None:
    from keigan.config.logging_config import set_correlation_id

    set_correlation_id("corr-azure-9")
    url = "https://management.azure.com/subscriptions/s/resourceGroups/rg-polaris/providers/Microsoft.Web/sites/app-claims?api-version=2022-03-01"
    response = httpx.Response(status_code, json=RAW_AZURE_BODY, request=httpx.Request("GET", url))
    with caplog.at_level("WARNING", logger="keigan.integrations.azure_client"), pytest.raises(IntegrationException) as raised:
        AzureClient._raise_for_status(response, url)
    detail = raised.value.detail
    assert expected_advice in detail
    assert "app-claims" in detail, "the admin needs to know which resource was refused"
    assert "AuthorizationFailed" not in detail and "bbbb-2222" not in detail and "metricDefinitions/read" not in detail
    assert "corr-azure-9" in detail
    assert any("bbbb-2222" in record.getMessage() for record in caplog.records), "the provider's own text must still reach the log"

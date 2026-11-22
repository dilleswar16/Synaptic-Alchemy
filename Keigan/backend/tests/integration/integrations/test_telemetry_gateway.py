"""keigan/integrations/telemetry_gateway.py: every read passes the access policy, in simulated mode too (V2); probes and log tools obey the outbound URL policy (V16)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.config.settings import IntegrationMode, get_settings
from keigan.entities.application_entities import LogToolConnection
from keigan.exceptions.keigan_exceptions import ForbiddenException, ReaderNotAvailableException
from keigan.integrations.telemetry_gateway import TelemetryGateway, TelemetryQuery, TelemetryTarget
from keigan.utils.outbound_url_policy import OutboundUrlPolicy
from support.telemetry_scope import (
    FOREIGN_WORKSPACE_CUSTOMER_ID,
    FOREIGN_WORKSPACE_RESOURCE_ID,
    OWN_AKS_RESOURCE_ID,
    OWN_RESOURCE_GROUP,
    OWN_SUBSCRIPTION_ID,
    OWN_WORKSPACE_CUSTOMER_ID,
    OWN_WORKSPACE_RESOURCE_ID,
    create_log_tool_connection,
    create_scoped_application,
)

pytestmark = pytest.mark.usefixtures("seed_context")

NOW = datetime.now(UTC)
QUERY = TelemetryQuery(query_language="kql", query_text="AppRequests", time_range_start=NOW - timedelta(hours=1), time_range_end=NOW)
NOT_APPROVED = "Keigan reads telemetry only for approved applications. Ask a Keigan admin to approve the onboarding request."


def simulated_gateway() -> TelemetryGateway:
    return application_context.telemetry_gateway()


def live_gateway(**policy_options: Any) -> TelemetryGateway:
    """Real policies and a live-mode gateway; the Azure and log tool clients are never reached by these tests."""
    live_settings = get_settings().model_copy(update={"telemetry_mode": IntegrationMode.LIVE})
    template = application_context.telemetry_gateway()
    return TelemetryGateway(
        live_settings, template.azure_client, template.log_tool_client_factory, template.telemetry_simulator, template.access_policy,
        OutboundUrlPolicy(denied_host_suffixes=(".svc",), **policy_options),
    )


def target(application_id: str, **overrides: Any) -> TelemetryTarget:
    values: dict[str, Any] = dict(
        application_id=application_id, service_id=None, service_name="polaris-api", service_type="aks", source_kind="log_analytics", azure_resource_id=OWN_AKS_RESOURCE_ID,
        log_analytics_workspace_resource_id=OWN_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=OWN_WORKSPACE_CUSTOMER_ID, use_simulation=True,
    )
    return TelemetryTarget(**{**values, **overrides})


async def test_simulated_logs_of_an_onboarding_request_are_refused() -> None:
    requested = await create_scoped_application(lifecycle_status="requested")
    with pytest.raises(ForbiddenException) as refusal:
        await simulated_gateway().query_logs(target(requested.application_id), QUERY)
    assert refusal.value.detail == NOT_APPROVED


async def test_simulated_metrics_and_activity_of_an_onboarding_request_are_refused() -> None:
    requested = await create_scoped_application(lifecycle_status="requested")
    gateway = simulated_gateway()
    with pytest.raises(ForbiddenException):
        await gateway.query_metrics(target(requested.application_id), ["cpu"], NOW - timedelta(hours=1), NOW)
    with pytest.raises(ForbiddenException):
        await gateway.query_activity_changes(requested.application_id, None, OWN_SUBSCRIPTION_ID, OWN_RESOURCE_GROUP, NOW - timedelta(hours=1), NOW, use_simulation=True)


async def test_simulated_probe_and_connection_test_of_an_onboarding_request_are_refused() -> None:
    requested = await create_scoped_application(lifecycle_status="requested")
    connection_id = await create_log_tool_connection(requested.application_id)
    async with open_session() as session:
        connection = await session.get(LogToolConnection, connection_id)
    gateway = simulated_gateway()
    with pytest.raises(ForbiddenException):
        await gateway.probe_endpoint("https://vendor.example/health", application_id=requested.application_id, use_simulation=True)
    with pytest.raises(ForbiddenException):
        await gateway.test_log_tool_connection(connection)


async def test_simulated_logs_from_another_teams_workspace_are_refused() -> None:
    application = await create_scoped_application()
    foreign = target(application.application_id, log_analytics_workspace_resource_id=FOREIGN_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=FOREIGN_WORKSPACE_CUSTOMER_ID)
    with pytest.raises(ForbiddenException):
        await simulated_gateway().query_logs(foreign, QUERY)


async def test_simulated_logs_of_an_approved_application_are_returned() -> None:
    application = await create_scoped_application()
    result = await simulated_gateway().query_logs(target(application.application_id), QUERY)
    assert result.is_simulated is True


@pytest.mark.parametrize("probe_url", ["https://169.254.169.254/latest/meta-data", "https://kubernetes.default.svc/healthz", "http://vendor.example/health"])
async def test_live_probe_refuses_addresses_inside_the_network_without_sending_a_request(probe_url: str) -> None:
    result = await live_gateway().probe_endpoint(probe_url)
    assert result.succeeded is False
    assert result.status_code is None
    assert result.message.startswith("This probe URL is not allowed. ")


async def test_live_log_tool_connection_test_refuses_a_stored_endpoint_inside_the_network() -> None:
    application = await create_scoped_application()
    connection_id = await create_log_tool_connection(application.application_id)
    async with open_session() as session:
        connection = await session.get(LogToolConnection, connection_id)
        connection.endpoint_url = "https://10.1.2.3:9200"  # stored before the policy existed, or edited in the database
    with pytest.raises(ForbiddenException) as refusal:
        await live_gateway().test_log_tool_connection(connection)
    assert refusal.value.detail == "Keigan will not call the elastic test endpoint. This address points at a private or internal network, which Keigan does not call. Ask an application admin to correct the connection."


# ── The Activity Log: simulated only where the telemetry mode rules say so ───────────────────────────────────────────────────────
@pytest.mark.parametrize(("mode", "marked_simulated", "expected"), [
    (IntegrationMode.SIMULATED, False, True), (IntegrationMode.SIMULATED, True, True), (IntegrationMode.LIVE, True, True), (IntegrationMode.LIVE, False, False),
])
def test_the_activity_log_is_simulated_in_simulated_mode_and_for_a_component_marked_simulated_only(mode: IntegrationMode, marked_simulated: bool, expected: bool) -> None:
    template = application_context.telemetry_gateway()
    gateway = TelemetryGateway(
        get_settings().model_copy(update={"telemetry_mode": mode}), template.azure_client, template.log_tool_client_factory, template.telemetry_simulator, template.access_policy,
        template.outbound_url_policy,
    )
    assert gateway.activity_is_simulated(use_simulation=marked_simulated) is expected


async def test_in_live_mode_an_application_with_no_azure_subscription_cannot_have_its_activity_log_read_and_is_never_answered_from_the_simulator() -> None:
    application = await create_scoped_application()
    with pytest.raises(ReaderNotAvailableException) as unreadable:
        await live_gateway().query_activity_changes(application.application_id, None, None, None, NOW - timedelta(hours=1), NOW)
    assert "no Azure subscription is connected" in unreadable.value.detail


async def test_in_live_mode_a_component_marked_simulated_is_still_answered_by_the_simulator() -> None:
    application = await create_scoped_application()
    changes = await live_gateway().query_activity_changes(application.application_id, None, OWN_SUBSCRIPTION_ID, OWN_RESOURCE_GROUP, NOW - timedelta(hours=1), NOW, use_simulation=True)
    assert isinstance(changes, list)


async def test_in_simulated_mode_an_application_with_no_subscription_is_still_answered_by_the_simulator() -> None:
    application = await create_scoped_application()
    changes = await simulated_gateway().query_activity_changes(application.application_id, None, None, None, NOW - timedelta(hours=1), NOW)
    assert isinstance(changes, list)

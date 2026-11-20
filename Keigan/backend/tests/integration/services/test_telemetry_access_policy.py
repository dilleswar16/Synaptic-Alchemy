"""keigan/services/telemetry_access_policy.py: Keigan reads telemetry only for approved applications and only from their own resources (V2)."""

from __future__ import annotations

from typing import Any

import pytest

from keigan.config.database_config import open_session
from keigan.config.settings import IntegrationMode, get_settings
from keigan.entities.application_entities import LogToolConnection
from keigan.exceptions.keigan_exceptions import ForbiddenException, IntegrationException, NotFoundException
from keigan.integrations.telemetry_gateway import TelemetryTarget
from keigan.services.telemetry_access_policy import TelemetryAccessPolicy, WorkspaceCustomerIdResolver
from support.telemetry_scope import (
    FOREIGN_WORKSPACE_CUSTOMER_ID,
    FOREIGN_WORKSPACE_RESOURCE_ID,
    OWN_AKS_RESOURCE_ID,
    OWN_APPLICATION_INSIGHTS_RESOURCE_ID,
    OWN_RESOURCE_GROUP,
    OWN_SUBSCRIPTION_ID,
    OWN_WORKSPACE_CUSTOMER_ID,
    OWN_WORKSPACE_RESOURCE_ID,
    SHARED_WORKSPACE_CUSTOMER_ID,
    SHARED_WORKSPACE_RESOURCE_ID,
    ScopedApplication,
    create_log_tool_connection,
    create_scoped_application,
)

pytestmark = pytest.mark.usefixtures("seed_context")  # creates the schema

NOT_APPROVED = "Keigan reads telemetry only for approved applications. Ask a Keigan admin to approve the onboarding request."
WORKSPACE_NOT_FOUND = (
    "Keigan will not read polaris-api logs. This workspace was not found in this application's verified Azure resource groups, so Keigan will not read it. "
    "Add the resource group that holds it as a component, verify access and run discovery, then choose it again."
)


class UnusedAzureClient:
    async def get_workspace_customer_id(self, tenant_id: str | None, workspace_resource_id: str) -> str | None:
        raise AssertionError("A simulated component must not be looked up in Azure.")


def build_policy(azure_client: Any = None, settings: Any = None) -> TelemetryAccessPolicy:
    effective_settings = settings or get_settings()
    return TelemetryAccessPolicy(open_session, effective_settings, WorkspaceCustomerIdResolver(azure_client or UnusedAzureClient(), cache_seconds=900))


def target_for(application: ScopedApplication, **overrides: Any) -> TelemetryTarget:
    values: dict[str, Any] = dict(
        application_id=application.application_id, service_id=None, service_name="polaris-api", service_type="aks", source_kind="log_analytics",
        azure_resource_id=OWN_AKS_RESOURCE_ID, log_analytics_workspace_resource_id=OWN_WORKSPACE_RESOURCE_ID,
        log_analytics_workspace_customer_id=OWN_WORKSPACE_CUSTOMER_ID, use_simulation=True,
    )
    return TelemetryTarget(**{**values, **overrides})


# ── Rule 1: approved applications only ─────────────────────────────────────────
async def test_telemetry_of_an_onboarding_request_is_refused_by_every_read_path() -> None:
    requested = await create_scoped_application(lifecycle_status="requested")
    connection_id = await create_log_tool_connection(requested.application_id)
    async with open_session() as session:
        connection = await session.get(LogToolConnection, connection_id)
    policy = build_policy()
    for refused_read in (
        policy.ensure_can_read_source(target_for(requested)),
        policy.ensure_can_read_metrics(target_for(requested)),
        policy.ensure_can_read_activity(requested.application_id, OWN_SUBSCRIPTION_ID, OWN_RESOURCE_GROUP),
        policy.ensure_can_use_connection(connection),
        policy.ensure_application_approved(requested.application_id),
    ):
        with pytest.raises(ForbiddenException) as refusal:
            await refused_read
        assert refusal.value.detail == NOT_APPROVED


@pytest.mark.parametrize("lifecycle_status", ["draft", "live", "paused"])
async def test_telemetry_of_an_approved_application_is_read(lifecycle_status: str) -> None:
    approved = await create_scoped_application(lifecycle_status=lifecycle_status)
    await build_policy().ensure_can_read_source(target_for(approved))


async def test_unknown_application_is_not_found() -> None:
    unknown = ScopedApplication("00000000-0000-0000-0000-000000000000", "none", "NONE")
    with pytest.raises(NotFoundException):
        await build_policy().ensure_can_read_source(target_for(unknown))


# ── Rule 2: only the application's own resources ───────────────────────────────
async def test_workspace_of_another_team_is_refused_even_with_its_real_workspace_id() -> None:
    application = await create_scoped_application()
    foreign_target = target_for(
        application, log_analytics_workspace_resource_id=FOREIGN_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=FOREIGN_WORKSPACE_CUSTOMER_ID
    )
    with pytest.raises(ForbiddenException) as refusal:
        await build_policy().ensure_can_read_source(foreign_target)
    assert refusal.value.detail.startswith(WORKSPACE_NOT_FOUND)


async def test_own_workspace_resource_with_another_teams_workspace_id_is_refused() -> None:
    application = await create_scoped_application()
    with pytest.raises(ForbiddenException) as refusal:
        await build_policy().ensure_can_read_source(target_for(application, log_analytics_workspace_customer_id=FOREIGN_WORKSPACE_CUSTOMER_ID))
    assert refusal.value.detail == (
        "Keigan will not read polaris-api logs. This workspace ID does not match any Log Analytics workspace of this application. "
        "Copy it from the workspace's overview page."
    )


async def test_workspace_the_applications_resources_send_their_logs_to_is_the_applications_own() -> None:
    application = await create_scoped_application()
    shared_target = target_for(
        application, log_analytics_workspace_resource_id=SHARED_WORKSPACE_RESOURCE_ID.upper(), log_analytics_workspace_customer_id=SHARED_WORKSPACE_CUSTOMER_ID
    )
    await build_policy().ensure_can_read_source(shared_target)


async def test_resources_of_a_component_whose_access_is_not_verified_are_not_trusted() -> None:
    application = await create_scoped_application(component_verification_status="missing_roles")
    with pytest.raises(ForbiddenException):
        await build_policy().ensure_can_read_source(target_for(application))


async def test_application_insights_resource_of_the_application_is_read_and_a_foreign_one_is_refused() -> None:
    application = await create_scoped_application()
    policy = build_policy()
    await policy.ensure_can_read_source(
        target_for(application, source_kind="application_insights", log_analytics_workspace_resource_id=OWN_APPLICATION_INSIGHTS_RESOURCE_ID, log_analytics_workspace_customer_id=None)
    )
    foreign_application_insights = OWN_APPLICATION_INSIGHTS_RESOURCE_ID.replace(OWN_SUBSCRIPTION_ID, "cccccccc-0000-0000-0000-000000000003")
    with pytest.raises(ForbiddenException):
        await policy.ensure_can_read_source(
            target_for(application, source_kind="application_insights", log_analytics_workspace_resource_id=foreign_application_insights, log_analytics_workspace_customer_id=None)
        )


async def test_metrics_are_read_inside_the_verified_resource_group_only() -> None:
    application = await create_scoped_application()
    policy = build_policy()
    await policy.ensure_can_read_metrics(target_for(application, azure_resource_id=OWN_AKS_RESOURCE_ID.upper()))
    foreign_resource = OWN_AKS_RESOURCE_ID.replace(OWN_RESOURCE_GROUP, "rg-other-team")
    with pytest.raises(ForbiddenException) as refusal:
        await policy.ensure_can_read_metrics(target_for(application, azure_resource_id=foreign_resource))
    assert refusal.value.detail == (
        "Keigan will not read polaris-api metrics. This Azure resource is not in a verified resource group of this application, so Keigan will not read it. "
        "Add its resource group as a component and verify access first."
    )


async def test_a_service_that_is_not_an_azure_resource_has_nothing_to_check_for_metrics() -> None:
    application = await create_scoped_application()
    await build_policy().ensure_can_read_metrics(target_for(application, azure_resource_id="syd-f5-ltm-01"))


async def test_activity_log_is_read_for_the_verified_resource_group_only() -> None:
    application = await create_scoped_application()
    policy = build_policy()
    await policy.ensure_can_read_activity(application.application_id, OWN_SUBSCRIPTION_ID, OWN_RESOURCE_GROUP.upper())
    with pytest.raises(ForbiddenException):
        await policy.ensure_can_read_activity(application.application_id, "cccccccc-0000-0000-0000-000000000003", "rg-other-team")


async def test_log_tool_connection_of_another_application_is_refused() -> None:
    application = await create_scoped_application()
    other_application = await create_scoped_application()
    own_connection_id = await create_log_tool_connection(application.application_id)
    foreign_connection_id = await create_log_tool_connection(other_application.application_id)
    policy = build_policy()
    async with open_session() as session:
        own_connection = await session.get(LogToolConnection, own_connection_id)
        foreign_connection = await session.get(LogToolConnection, foreign_connection_id)
    await policy.ensure_can_read_source(target_for(application, source_kind="log_tool", log_tool_connection=own_connection))
    with pytest.raises(ForbiddenException) as refusal:
        await policy.ensure_can_read_source(target_for(application, source_kind="log_tool", log_tool_connection=foreign_connection))
    assert refusal.value.detail == "Keigan will not read polaris-api logs. Choose a log tool connection of this application."


# ── Live mode: the workspace id is what Azure says it is ───────────────────────
class RecordingAzureClient:
    def __init__(self, customer_id_by_resource_id: dict[str, str]):
        self.customer_id_by_resource_id = customer_id_by_resource_id
        self.lookup_count = 0

    async def get_workspace_customer_id(self, tenant_id: str | None, workspace_resource_id: str) -> str | None:
        self.lookup_count += 1
        return self.customer_id_by_resource_id.get(workspace_resource_id.lower())


async def test_live_workspace_id_is_compared_with_the_one_azure_reports_and_the_lookup_is_cached() -> None:
    application = await create_scoped_application(is_simulated_component=False)
    azure_client = RecordingAzureClient({OWN_WORKSPACE_RESOURCE_ID.lower(): "12345678-aaaa-bbbb-cccc-123456789012", SHARED_WORKSPACE_RESOURCE_ID.lower(): "87654321-aaaa-bbbb-cccc-123456789012"})
    live_settings = get_settings().model_copy(update={"telemetry_mode": IntegrationMode.LIVE})
    policy = build_policy(azure_client, live_settings)
    await policy.ensure_can_read_source(target_for(application, log_analytics_workspace_customer_id="12345678-AAAA-bbbb-cccc-123456789012", use_simulation=False))
    await policy.ensure_can_read_source(target_for(application, log_analytics_workspace_customer_id="12345678-aaaa-bbbb-cccc-123456789012", use_simulation=False))
    assert azure_client.lookup_count == 2  # one lookup per workspace of the application, then the cache answers
    with pytest.raises(ForbiddenException):
        await policy.ensure_can_read_source(target_for(application, log_analytics_workspace_customer_id=OWN_WORKSPACE_CUSTOMER_ID, use_simulation=False))


async def test_live_workspace_that_azure_cannot_describe_is_not_trusted() -> None:
    application = await create_scoped_application(is_simulated_component=False)

    class FailingAzureClient:
        async def get_workspace_customer_id(self, tenant_id: str | None, workspace_resource_id: str) -> str | None:
            raise IntegrationException("Azure did not answer.")

    live_settings = get_settings().model_copy(update={"telemetry_mode": IntegrationMode.LIVE})
    with pytest.raises(ForbiddenException):
        await build_policy(FailingAzureClient(), live_settings).ensure_can_read_source(target_for(application, use_simulation=False))

"""Applications with a verified Azure component and the resources Keigan "discovered" in it, for the telemetry access rules (V2).

The workspace ids are the ones the simulator derives from a resource id (``uuid5(NAMESPACE_DNS, resource_id.lower())``); the
literals below were computed once by hand.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application, ApplicationComponent, DiscoveredResource, LogToolConnection

OWN_SUBSCRIPTION_ID = "aaaaaaaa-0000-0000-0000-000000000001"
OWN_RESOURCE_GROUP = "rg-polaris"
OWN_WORKSPACE_RESOURCE_ID = f"/subscriptions/{OWN_SUBSCRIPTION_ID}/resourceGroups/{OWN_RESOURCE_GROUP}/providers/Microsoft.OperationalInsights/workspaces/law-polaris"
OWN_WORKSPACE_CUSTOMER_ID = "ef20f8ec-2e05-5a10-adf1-3f2997d77691"
OWN_APPLICATION_INSIGHTS_RESOURCE_ID = f"/subscriptions/{OWN_SUBSCRIPTION_ID}/resourceGroups/{OWN_RESOURCE_GROUP}/providers/Microsoft.Insights/components/appi-polaris"
OWN_AKS_RESOURCE_ID = f"/subscriptions/{OWN_SUBSCRIPTION_ID}/resourceGroups/{OWN_RESOURCE_GROUP}/providers/Microsoft.ContainerService/managedClusters/polaris-aks"
# The AKS cluster sends its logs to a central workspace in another subscription: its diagnostic setting makes that workspace the application's too.
SHARED_WORKSPACE_RESOURCE_ID = "/subscriptions/bbbbbbbb-0000-0000-0000-000000000002/resourceGroups/rg-central-logging/providers/Microsoft.OperationalInsights/workspaces/law-central"
SHARED_WORKSPACE_CUSTOMER_ID = "534d6995-681e-5dbf-b747-1c8ea917b67c"
# A workspace that belongs to another team: no resource of the application sends logs to it.
FOREIGN_WORKSPACE_RESOURCE_ID = "/subscriptions/cccccccc-0000-0000-0000-000000000003/resourceGroups/rg-other-team/providers/Microsoft.OperationalInsights/workspaces/law-other-team"
FOREIGN_WORKSPACE_CUSTOMER_ID = "44b7dcc2-691d-570c-aedf-74d5f39a9ae0"

_application_counter = itertools.count(1)


@dataclass(frozen=True)
class ScopedApplication:
    application_id: str
    component_id: str
    application_code: str


async def create_scoped_application(
    *, lifecycle_status: str = "draft", component_verification_status: str = "verified", is_simulated_component: bool = True
) -> ScopedApplication:
    application_code = f"SCP{next(_application_counter):04d}"
    async with open_session() as session:
        application = Application(
            application_name=f"Scope {application_code}", application_code=application_code, lifecycle_status=lifecycle_status,
            admin_group_name=f"{application_code}_admin", reader_group_name=f"{application_code}_reader", created_by_user_principal_name="system:test",
        )
        session.add(application)
        await session.flush()
        component = ApplicationComponent(
            application_id=application.application_id, component_type="azure_resource_group", component_name=OWN_RESOURCE_GROUP, azure_tenant_id="dddddddd-0000-0000-0000-000000000004",
            azure_subscription_id=OWN_SUBSCRIPTION_ID, azure_resource_group_name=OWN_RESOURCE_GROUP, access_verification_status=component_verification_status,
            component_configuration_json={"simulated": is_simulated_component}, created_by_user_principal_name="system:test",
        )
        session.add(component)
        await session.flush()
        for azure_resource_id, resource_type, resource_name, workspace_ids in (
            (OWN_WORKSPACE_RESOURCE_ID, "Microsoft.OperationalInsights/workspaces", "law-polaris", None),
            (OWN_APPLICATION_INSIGHTS_RESOURCE_ID, "Microsoft.Insights/components", "appi-polaris", None),
            (OWN_AKS_RESOURCE_ID, "Microsoft.ContainerService/managedClusters", "polaris-aks", [SHARED_WORKSPACE_RESOURCE_ID]),
        ):
            session.add(DiscoveredResource(
                component_id=component.component_id, application_id=application.application_id, azure_resource_id=azure_resource_id, resource_name=resource_name,
                resource_type=resource_type, log_analytics_workspace_resource_ids_json=workspace_ids,
            ))
        return ScopedApplication(application.application_id, component.component_id, application_code)


async def create_log_tool_connection(application_id: str, tool_type: str = "elastic") -> str:
    async with open_session() as session:
        connection = LogToolConnection(
            application_id=application_id, tool_type=tool_type, connection_name=f"{tool_type} test", endpoint_url="https://elastic.example.com", created_by_user_principal_name="system:test"
        )
        session.add(connection)
        await session.flush()
        return connection.log_tool_connection_id

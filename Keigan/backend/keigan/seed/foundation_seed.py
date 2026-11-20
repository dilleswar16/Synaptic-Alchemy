"""Demo applications for local development: every component type, realistic services, dependencies and stakeholders.

All demo components carry ``{"simulated": true}`` so their telemetry comes from the simulator even in mixed setups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.application_entities import (
    Application,
    ApplicationComponent,
    DiscoveredResource,
    LogToolConnection,
    MonitoredService,
    ServiceDependency,
    ServiceLogSource,
)
from keigan.entities.incident_entities import ServiceNowAssignmentGroup
from keigan.entities.notification_entities import Stakeholder
from keigan.integrations.simulation.telemetry_simulator import ScenarioWindow
from keigan.services.component_discovery_service import simulated_workspace_customer_id
from keigan.services.simulation_service import SimulationService

SEED_ACTOR = "system:seed"


@dataclass
class SeedContext:
    """Shared between seed steps: application ids by code and service ids by '<CODE>/<service name>'."""

    application_ids_by_code: dict[str, str] = field(default_factory=dict)
    service_ids_by_key: dict[str, str] = field(default_factory=dict)
    historical_scenarios: list[dict[str, Any]] = field(default_factory=list)

    def service_id(self, application_code: str, service_name: str) -> str:
        return self.service_ids_by_key[f"{application_code}/{service_name}"]


def _azure_resource_id(subscription_id: str, resource_group_name: str, provider_type: str, resource_name: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/{provider_type}/{resource_name}"


DEMO_APPLICATIONS: list[dict[str, Any]] = [
    {
        "application_code": "CLMJP",
        "application_name": "Claims Processing (JP)",
        "application_description": "Customer claims intake, assessment and payment orchestration for MetLife Japan.",
        "business_unit_name": "Japan Operations",
        "region_code": "JP",
        "primary_locale": "ja",
        "time_zone_name": "Asia/Tokyo",
        "criticality_tier": "tier_1",
        "servicenow_groups": ["JP-Claims-L2-Support", "JP-Claims-DevOps"],
        "components": [
            {
                "component_type": "azure_resource_group",
                "component_name": "RG_21530_CLMJP_PRD01",
                "azure_subscription_id": "8d1c3f2a-4b6e-4c1d-9a7f-21530c1a0001",
                "azure_subscription_name": "MetLife-JP-Prod-01",
                "services": [
                    ("claims-apim", "api_management", "Microsoft.ApiManagement/service", "tier_1", None),
                    ("claims-api", "aks", "Microsoft.ContainerService/managedClusters", "tier_1", "claims"),
                    ("claims-document-renderer", "aks", "Microsoft.ContainerService/managedClusters", "tier_2", "claims-docs"),
                    ("claims-intake-func", "function_app", "Microsoft.Web/sites", "tier_2", None),
                    ("claims-workflow", "logic_app", "Microsoft.Logic/workflows", "tier_2", None),
                    ("claims-nightly-etl", "data_factory", "Microsoft.DataFactory/factories", "tier_3", None),
                    ("claims-sql", "sql_database", "Microsoft.Sql/servers/databases", "tier_1", None),
                ],
            }
        ],
        "dependencies": [
            ("claims-apim", "claims-api", "calls"),
            ("claims-api", "claims-sql", "writes_to"),
            ("claims-api", "claims-document-renderer", "calls"),
            ("claims-intake-func", "claims-api", "calls"),
            ("claims-workflow", "claims-intake-func", "calls"),
            ("claims-nightly-etl", "claims-sql", "reads_from"),
        ],
        "stakeholders": [
            ("Aiko AppAdmin", "aiko.appadmin@keigan.local", "sre", "P3", "ja", ["email", "teams_incident_chat"]),
            ("Rui Reader", "rui.reader@keigan.local", "developer", "P2", "en", ["email", "teams_incident_chat"]),
            ("Haruto Manager", "haruto.manager@keigan.local", "manager", "P2", "ja", ["email"]),
            ("Yui Executive", "yui.executive@keigan.local", "executive", "P1", "ja", ["email"]),
        ],
    },
    {
        "application_code": "CHAD",
        "application_name": "Channel APIs for Digital (AU)",
        "application_description": "Public channel APIs used by the MetLife Australia mobile app and adviser portal.",
        "business_unit_name": "Engineering Axis",
        "region_code": "AU",
        "primary_locale": "en",
        "time_zone_name": "Australia/Sydney",
        "criticality_tier": "tier_1",
        "servicenow_groups": ["AU-Digital-Channels-Support"],
        "log_tools": [("elastic", "ChAD Elastic", "https://chad-elastic.es.australiaeast.azure.elastic-cloud.com", {"index_pattern": "logs-chad-*", "service_field": "service.name"})],
        "components": [
            {
                "component_type": "azure_resource_group",
                "component_name": "RG_14470_AUCHAD_PRD01",
                "azure_subscription_id": "d5fe3f1f-7c2b-4e8a-b0d1-14470d7c0004",
                "azure_subscription_name": "MetLife-AU-Digital-Prod",
                "services": [
                    ("chad-apim", "api_management", "Microsoft.ApiManagement/service", "tier_1", None),
                    ("azaustaekub14470pr0101", "aks", "Microsoft.ContainerService/managedClusters", "tier_1", "channel-apis"),
                    ("channel-gateway-app", "app_service", "Microsoft.Web/sites", "tier_1", None),
                    ("chad-notifications-func", "function_app", "Microsoft.Web/sites", "tier_3", None),
                ],
            }
        ],
        "dependencies": [
            ("chad-apim", "channel-gateway-app", "calls"),
            ("chad-apim", "azaustaekub14470pr0101", "calls"),
            ("azaustaekub14470pr0101", "chad-notifications-func", "publishes_to"),
        ],
        "stakeholders": [
            ("Kai Admin", "keigan.admin@keigan.local", "sre", "P3", "en", ["email", "teams_incident_chat"]),
            ("Aiko AppAdmin", "aiko.appadmin@keigan.local", "developer", "P2", "ja", ["email"]),
        ],
    },
    {
        "application_code": "PAYAU",
        "application_name": "Payments Platform (AU)",
        "application_description": "Premium collection and claim payouts, including the partner bank integration and data-centre network edge.",
        "business_unit_name": "Finance Technology",
        "region_code": "AU",
        "primary_locale": "en",
        "time_zone_name": "Australia/Sydney",
        "criticality_tier": "tier_1",
        "servicenow_groups": ["AU-Payments-Support"],
        "log_tools": [("solarwinds", "SolarWinds Orion (SYD DC)", "https://orion.syd.metlife.example:17778", {"node_group": "PAY-EDGE"})],
        "components": [
            {
                "component_type": "azure_resource_group",
                "component_name": "RG_30211_PAYAU_PRD01",
                "azure_subscription_id": "4f7a2b91-3c5d-4e6f-8a9b-30211a7b0002",
                "azure_subscription_name": "MetLife-AU-Finance-Prod",
                "services": [
                    ("payment-api", "aks", "Microsoft.ContainerService/managedClusters", "tier_1", "payments"),
                    ("payment-confirmation-func", "function_app", "Microsoft.Web/sites", "tier_1", None),
                    ("payments-apim", "api_management", "Microsoft.ApiManagement/service", "tier_1", None),
                ],
            },
            {
                "component_type": "hardware",
                "component_name": "Sydney data centre network edge",
                "configuration": {"device_category": "network", "location": "SYD-DC2", "cmdb_ci": "CI0091422", "monitored_by": "solarwinds"},
                "services": [
                    ("syd-f5-ltm-01", "network_appliance", None, "tier_1", None),
                    ("syd-paloalto-fw-02", "network_appliance", None, "tier_1", None),
                ],
            },
        ],
        "dependencies": [
            ("payments-apim", "payment-api", "calls"),
            ("payment-api", "payment-confirmation-func", "publishes_to"),
            ("payment-confirmation-func", "payments-apim", "calls"),
            ("syd-f5-ltm-01", "payments-apim", "hosted_on"),
        ],
        "stakeholders": [
            ("Rui Reader", "rui.reader@keigan.local", "sre", "P2", "en", ["email", "teams_incident_chat"]),
            ("Mia Finance Owner", "mia.owner@keigan.local", "business_owner", "P1", "en", ["email"]),
        ],
    },
    {
        "application_code": "PADMF",
        "application_name": "Policy Administration Mainframe (US)",
        "application_description": "z/OS policy administration: CICS online transactions and nightly premium billing batch.",
        "business_unit_name": "US Core Systems",
        "region_code": "US",
        "primary_locale": "en",
        "time_zone_name": "America/New_York",
        "criticality_tier": "tier_1",
        "servicenow_groups": ["US-Mainframe-Batch-Ops"],
        "log_tools": [("splunk", "Splunk Mainframe", "https://splunk-mf.us.metlife.example:8089", {"indexes": ["zos_syslog", "zos_smf"], "source_types": ["syslog:zos"]})],
        "components": [
            {
                "component_type": "mainframe",
                "component_name": "SYSB sysplex — LPAR PRD1",
                "configuration": {"lpar": "PRD1", "subsystems": ["CICS", "DB2", "MQ", "batch"], "job_name_prefixes": ["PBIL", "PADM"], "batch_window": "01:00-05:00 ET"},
                "services": [
                    ("cics-policy-online", "mainframe_subsystem", None, "tier_1", None),
                    ("premium-billing-batch", "batch_job_stream", None, "tier_1", None),
                ],
            }
        ],
        "dependencies": [("premium-billing-batch", "cics-policy-online", "reads_from")],
        "stakeholders": [("Kai Admin", "keigan.admin@keigan.local", "sre", "P2", "en", ["email"])],
    },
    {
        "application_code": "BENSA",
        "application_name": "Employee Benefits Portal (SaaS)",
        "application_description": "Vendor-hosted benefits enrolment portal; vendor-hosted logging; monitored with synthetic probes and the vendor status page.",
        "business_unit_name": "Group Benefits",
        "region_code": "JP",
        "primary_locale": "ja",
        "time_zone_name": "Asia/Tokyo",
        "criticality_tier": "tier_2",
        "servicenow_groups": ["JP-Benefits-Vendor-Mgmt"],
        "log_tools": [("vendor_api", "BenefitsCloud audit API", "https://api.benefitscloud.example/v2", {"vendor": "BenefitsCloud"})],
        "components": [
            {
                "component_type": "saas_platform",
                "component_name": "BenefitsCloud tenant metlife-jp",
                "configuration": {
                    "vendor_name": "BenefitsCloud",
                    "product_name": "Enrolment Suite",
                    "instance_url": "https://metlife-jp.benefitscloud.example",
                    "status_page_url": "https://status.benefitscloud.example/api/v2/status.json",
                    "probe_url": "https://metlife-jp.benefitscloud.example/health",
                    "contractual_sla_percentage": 99.5,
                },
                "services": [("benefits-portal", "saas_service", None, "tier_2", None)],
            }
        ],
        "dependencies": [],
        "stakeholders": [("Aiko AppAdmin", "aiko.appadmin@keigan.local", "sre", "P3", "ja", ["email"])],
    },
]


async def seed_demo_applications(session: AsyncSession, seed_context: SeedContext) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    for application_definition in DEMO_APPLICATIONS:
        application_code = application_definition["application_code"]
        existing_application = await session.scalar(select(Application).where(Application.application_code == application_code))
        if existing_application is not None:
            seed_context.application_ids_by_code[application_code] = existing_application.application_id
            for existing_service in (await session.scalars(select(MonitoredService).where(MonitoredService.application_id == existing_application.application_id))).all():
                seed_context.service_ids_by_key[f"{application_code}/{existing_service.service_name}"] = existing_service.service_id
            continue

        application = Application(
            application_name=application_definition["application_name"],
            application_code=application_code,
            application_description=application_definition["application_description"],
            business_unit_name=application_definition["business_unit_name"],
            region_code=application_definition["region_code"],
            primary_locale=application_definition["primary_locale"],
            time_zone_name=application_definition["time_zone_name"],
            criticality_tier=application_definition["criticality_tier"],
            lifecycle_status="live",
            admin_group_name=settings.application_admin_group_name_for(application_code),
            reader_group_name=settings.application_reader_group_name_for(application_code),
            incident_creation_policy_json={"mode": "suggest", "minimum_score": 30, "assignment_group_name": application_definition["servicenow_groups"][0]},
            went_live_at=now - timedelta(days=45),
            went_live_by_user_principal_name="keigan.admin@keigan.local",
            created_by_user_principal_name=SEED_ACTOR,
        )
        session.add(application)
        await session.flush()
        seed_context.application_ids_by_code[application_code] = application.application_id

        log_tool_connections_by_type: dict[str, LogToolConnection] = {}
        for tool_type, connection_name, endpoint_url, connection_configuration in application_definition.get("log_tools", []):
            log_tool_connection = LogToolConnection(
                application_id=application.application_id,
                tool_type=tool_type,
                connection_name=connection_name,
                endpoint_url=endpoint_url,
                authentication_method="api_key",
                connection_configuration_json=connection_configuration,
                connection_status="connected" if tool_type in ("elastic", "splunk", "datadog") else "reader_not_available",
                last_tested_at=now - timedelta(hours=3),
                last_test_message="Simulated connection verified." if tool_type in ("elastic", "splunk", "datadog") else "Reader in development — details saved.",
                created_by_user_principal_name=SEED_ACTOR,
            )
            session.add(log_tool_connection)
            log_tool_connections_by_type[tool_type] = log_tool_connection
        await session.flush()

        for component_definition in application_definition["components"]:
            component_type = component_definition["component_type"]
            subscription_id = component_definition.get("azure_subscription_id")
            resource_group_name = component_definition["component_name"] if component_type == "azure_resource_group" else None
            component = ApplicationComponent(
                application_id=application.application_id,
                component_type=component_type,
                component_name=component_definition["component_name"],
                environment_name="prod",
                azure_tenant_id=settings.azure_tenant_id if component_type == "azure_resource_group" else None,
                azure_subscription_id=subscription_id,
                azure_subscription_name=component_definition.get("azure_subscription_name"),
                azure_resource_group_name=resource_group_name,
                component_configuration_json={"simulated": True, **component_definition.get("configuration", {})},
                access_verification_status="verified" if component_type == "azure_resource_group" else "not_applicable",
                access_verification_details_json=[
                    {"checkName": "list_resources", "passed": True, "message": "Simulated: resources visible."},
                    {"checkName": "read_activity_log", "passed": True, "message": "Simulated: activity log readable."},
                    {"checkName": "read_metrics", "passed": True, "message": "Simulated: metrics readable."},
                    {"checkName": "query_workspace", "passed": True, "message": "Simulated: workspace queryable."},
                ] if component_type == "azure_resource_group" else None,
                last_verified_at=now - timedelta(hours=2),
                last_discovered_at=now - timedelta(hours=2),
                created_by_user_principal_name=SEED_ACTOR,
            )
            session.add(component)
            await session.flush()
            workspace_resource_id = (
                _azure_resource_id(subscription_id, resource_group_name, "Microsoft.OperationalInsights/workspaces", f"law-{application_code.lower()}-prd")
                if subscription_id and resource_group_name else None
            )
            workspace_customer_id = simulated_workspace_customer_id(workspace_resource_id) if workspace_resource_id else None

            if component_type == "azure_resource_group":
                # Keigan only reads workspaces that belong to the application (V2): record what discovery would have found.
                for resource_type, resource_name in (("Microsoft.OperationalInsights/workspaces", f"law-{application_code.lower()}-prd"), ("Microsoft.Insights/components", f"appi-{application_code.lower()}-prd")):
                    session.add(DiscoveredResource(
                        component_id=component.component_id, application_id=application.application_id, resource_name=resource_name, resource_type=resource_type,
                        azure_resource_id=_azure_resource_id(subscription_id, resource_group_name, resource_type, resource_name), monitoring_classification="telemetry_source",
                    ))

            for service_name, service_type, provider_type, criticality_tier, namespace_filter in component_definition["services"]:
                external_identifier = (
                    _azure_resource_id(subscription_id, resource_group_name, provider_type, service_name) if provider_type and subscription_id and resource_group_name else service_name
                )
                service = MonitoredService(
                    application_id=application.application_id,
                    component_id=component.component_id,
                    service_name=service_name,
                    service_type=service_type,
                    external_resource_identifier=external_identifier,
                    environment_name="prod",
                    criticality_tier=criticality_tier,
                    aks_namespace_filter=namespace_filter,
                    application_insights_role_name=service_name if service_type in ("aks", "app_service", "function_app") else None,
                    application_insights_resource_id=(
                        _azure_resource_id(subscription_id, resource_group_name, "Microsoft.Insights/components", f"appi-{application_code.lower()}-prd")
                        if service_type in ("aks", "app_service", "function_app") and subscription_id else None
                    ),
                    repository_provider="azure_devops" if service_type in ("aks", "app_service", "function_app") else None,
                    repository_url=f"https://dev.azure.com/metlife/{application_code}/_git/{service_name}" if service_type in ("aks", "app_service", "function_app") else None,
                    repository_default_branch="main" if service_type in ("aks", "app_service", "function_app") else None,
                    created_by_user_principal_name=SEED_ACTOR,
                )
                session.add(service)
                await session.flush()
                seed_context.service_ids_by_key[f"{application_code}/{service_name}"] = service.service_id

                if component_type == "azure_resource_group":
                    session.add(
                        ServiceLogSource(
                            service_id=service.service_id,
                            source_kind="azure_monitor_metrics",
                            is_primary_source=False,
                            was_auto_detected=True,
                            last_read_test_status="passed",
                            last_read_test_at=now - timedelta(hours=2),
                        )
                    )
                    if service_type != "sql_database" or application_code == "CLMJP":
                        session.add(
                            ServiceLogSource(
                                service_id=service.service_id,
                                source_kind="application_insights" if service_type in ("aks", "app_service", "function_app") else "log_analytics",
                                log_analytics_workspace_resource_id=workspace_resource_id,
                                log_analytics_workspace_customer_id=workspace_customer_id,
                                is_primary_source=True,
                                was_auto_detected=True,
                                last_read_test_status="passed",
                                last_read_test_at=now - timedelta(hours=2),
                            )
                        )
                    if application_code == "CHAD" and service_type == "aks" and "elastic" in log_tool_connections_by_type:
                        session.add(
                            ServiceLogSource(
                                service_id=service.service_id,
                                source_kind="log_tool",
                                log_tool_connection_id=log_tool_connections_by_type["elastic"].log_tool_connection_id,
                                query_scope_json={"index_pattern": "logs-chad-*", "service_field_value": service_name, "namespace": namespace_filter},
                                last_read_test_status="passed",
                                last_read_test_at=now - timedelta(hours=3),
                            )
                        )
                elif component_type == "saas_platform":
                    session.add(
                        ServiceLogSource(
                            service_id=service.service_id,
                            source_kind="synthetic_probe",
                            query_scope_json={"probe_url": component_definition["configuration"]["probe_url"]},
                            is_primary_source=True,
                            last_read_test_status="passed",
                            last_read_test_at=now - timedelta(hours=1),
                        )
                    )
                else:
                    connection_type = "splunk" if component_type == "mainframe" else "solarwinds"
                    if connection_type in log_tool_connections_by_type:
                        session.add(
                            ServiceLogSource(
                                service_id=service.service_id,
                                source_kind="log_tool",
                                log_tool_connection_id=log_tool_connections_by_type[connection_type].log_tool_connection_id,
                                query_scope_json={"host": service_name, "index": "zos_syslog"} if component_type == "mainframe" else {"node_name": service_name},
                                is_primary_source=True,
                                last_read_test_status="passed" if connection_type == "splunk" else "not_tested",
                            )
                        )
        await session.flush()

        for upstream_service_name, downstream_service_name, dependency_kind in application_definition["dependencies"]:
            session.add(
                ServiceDependency(
                    application_id=application.application_id,
                    upstream_service_id=seed_context.service_id(application_code, upstream_service_name),
                    downstream_service_id=seed_context.service_id(application_code, downstream_service_name),
                    dependency_kind=dependency_kind,
                    dependency_source="user_declared",
                )
            )
        for group_name in application_definition["servicenow_groups"]:
            session.add(ServiceNowAssignmentGroup(application_id=application.application_id, group_name=group_name, verification_status="verified"))
        for display_name, email_address, stakeholder_role, minimum_priority, language_code, channels in application_definition["stakeholders"]:
            session.add(
                Stakeholder(
                    application_id=application.application_id,
                    recipient_type="person",
                    display_name=display_name,
                    email_address=email_address,
                    user_principal_name=email_address,
                    stakeholder_role=stakeholder_role,
                    notification_channels_json=channels,
                    minimum_priority=minimum_priority,
                    subscribed_notification_types_json=[
                        "incident_detected", "preliminary_report", "progress_update", "postmortem", "intelligence_report", "slo_burn_alert",
                    ],
                    preferred_language_code=language_code,
                    created_by_user_principal_name=SEED_ACTOR,
                )
            )
        await session.flush()


HISTORICAL_SCENARIOS = (
    # (application code, scenario key, primary service, dependency service, days ago, duration minutes)
    ("CLMJP", "database_connection_pool_exhaustion", "claims-api", "claims-sql", 6, 48),
    ("CLMJP", "node_memory_pressure_oom", "claims-document-renderer", "claims-apim", 17, 35),
    ("CHAD", "certificate_expiry", "channel-gateway-app", None, 13, 31),
    ("CHAD", "apim_backend_throttling", "chad-apim", None, 4, 55),
    ("PAYAU", "downstream_api_timeout", "payment-confirmation-func", "payments-apim", 3, 70),
    ("PADMF", "batch_job_abend", "premium-billing-batch", None, 2, 95),
    ("BENSA", "saas_vendor_outage", "benefits-portal", None, 9, 80),
)


async def seed_simulation_world(session: AsyncSession, seed_context: SeedContext) -> None:
    simulation_service = SimulationService(session)
    configuration = await simulation_service.read_configuration()
    if configuration.get("scenario_windows"):
        seed_context.historical_scenarios = [window for window in configuration["scenario_windows"] if window.get("historical")]
        return
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    scenario_windows: list[dict[str, Any]] = []
    for application_code, scenario_key, primary_service_name, dependency_service_name, days_ago, duration_minutes in HISTORICAL_SCENARIOS:
        started_at = (now - timedelta(days=days_ago)).replace(hour=2 + days_ago % 5, minute=10 + days_ago % 40)
        scenario_window = ScenarioWindow(
            scenario_key=scenario_key,
            application_id=seed_context.application_ids_by_code[application_code],
            primary_service_ids=[seed_context.service_id(application_code, primary_service_name)],
            dependency_service_ids=[seed_context.service_id(application_code, dependency_service_name)] if dependency_service_name else [],
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=duration_minutes),
            external_incident_number=f"INC00{4_090_000 + len(scenario_windows) * 137}",
        )
        window_dictionary = {**scenario_window.to_dictionary(), "historical": True, "application_code": application_code}
        scenario_windows.append(window_dictionary)
    conditions = [
        {"condition_kind": "memory_leak", "service_id": seed_context.service_id("CLMJP", "claims-document-renderer"), "percent_per_day": 3.2, "started_at": (now - timedelta(days=9)).isoformat()},
        {"condition_kind": "error_budget_burn", "service_id": seed_context.service_id("CHAD", "chad-apim"), "extra_error_ratio": 0.0031, "started_at": (now - timedelta(days=5)).isoformat()},
        {"condition_kind": "latency_creep", "service_id": seed_context.service_id("PAYAU", "payment-api"), "milliseconds_per_day": 11.0, "started_at": (now - timedelta(days=12)).isoformat()},
    ]
    await simulation_service.write_configuration({"scenario_windows": scenario_windows, "conditions": conditions})
    seed_context.historical_scenarios = scenario_windows

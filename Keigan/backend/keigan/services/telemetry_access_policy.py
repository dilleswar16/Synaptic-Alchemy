"""Who may be read through Keigan's own identity (finding V2, the confused deputy).

Keigan reads logs, metrics and the activity log with its own managed identity, which has Reader on many teams' Azure resources.
Two rules keep that power from being used on behalf of the wrong person:

1. **Approved applications only.** Telemetry of an application that is still an onboarding request is never read. A Keigan admin
   approves the request first (the requester keeps editing the request).
2. **Only the application's own resources.** A log source or service may only point at Azure resources that Keigan discovered in
   the application's *verified* components: the Log Analytics workspace (resource id and workspace id), the Application Insights
   resource and the subscription and resource group. A log tool connection must belong to the same application.

``TelemetryAccessRules`` holds the rules and works on a given session. The gateway calls ``TelemetryAccessPolicy`` before every read
(chat, investigations, evidence, SLI collection, probes, connection tests), so no caller can skip it. The services that save log
sources use the same rules to refuse a bad value early with a field error.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import IntegrationMode, Settings
from keigan.entities.application_entities import Application, ApplicationComponent, DiscoveredResource
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, IntegrationException, NotFoundException
from keigan.services.authorization_service import UNAPPROVED_LIFECYCLE_STATUSES
from keigan.services.component_discovery_service import classify_resource, simulated_workspace_customer_id

if TYPE_CHECKING:
    from keigan.entities.application_entities import LogToolConnection
    from keigan.integrations.azure_client import AzureClient
    from keigan.integrations.telemetry_gateway import TelemetryTarget

logger = logging.getLogger(__name__)

NOT_APPROVED_MESSAGE = "Keigan reads telemetry only for approved applications. Ask a Keigan admin to approve the onboarding request."
AZURE_RESOURCE_SCOPE_PATTERN = re.compile(r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)(?:/|$)", re.IGNORECASE)
WORKSPACE_SOURCE_KIND = "log_analytics_workspace"
APPLICATION_INSIGHTS_SOURCE_KIND = "application_insights"

SessionScope = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class FieldProblem:
    """One reason a value is refused: the camelCase field the form shows it on and an end-user message."""

    field_name: str
    message: str

    def as_field_error(self) -> dict[str, str]:
        return {"field": self.field_name, "message": self.message}


class WorkspaceCustomerIdResolver:
    """Looks up the customer id of a Log Analytics workspace in Azure and trusts the answer for a while.

    The id Keigan stores for a log source is whatever the user typed; this is the answer Azure gives for the workspace resource,
    so the two can be compared.
    """

    def __init__(self, azure_client: "AzureClient", cache_seconds: int, clock: Callable[[], float] = time.monotonic):
        self.azure_client = azure_client
        self.cache_seconds = cache_seconds
        self.clock = clock
        self._cache: dict[tuple[str | None, str], tuple[float, str]] = {}

    async def customer_id_of(self, tenant_id: str | None, workspace_resource_id: str, is_simulated: bool) -> str | None:
        if is_simulated:
            return simulated_workspace_customer_id(workspace_resource_id)
        cache_key = (tenant_id, workspace_resource_id.lower())
        cached_entry = self._cache.get(cache_key)
        if cached_entry is not None and self.clock() - cached_entry[0] < self.cache_seconds:
            return cached_entry[1]
        try:
            customer_id = await self.azure_client.get_workspace_customer_id(tenant_id, workspace_resource_id)
        except IntegrationException as lookup_error:
            logger.warning("Could not look up the Log Analytics workspace id of %s: %s", workspace_resource_id, lookup_error.detail)
            return None
        if customer_id:
            self._cache[cache_key] = (self.clock(), customer_id.lower())
            return customer_id.lower()
        return None


@dataclass
class ApplicationTelemetryScope:
    """What Keigan discovered for one application: the only Azure resources its telemetry may come from."""

    application_id: str
    lifecycle_status: str
    verified_components: dict[str, ApplicationComponent] = field(default_factory=dict)
    workspace_component_by_resource_id: dict[str, str] = field(default_factory=dict)
    application_insights_resource_ids: set[str] = field(default_factory=set)

    @property
    def is_approved(self) -> bool:
        return self.lifecycle_status not in UNAPPROVED_LIFECYCLE_STATUSES

    def contains_resource_group(self, subscription_id: str | None, resource_group_name: str | None) -> bool:
        return any(
            (component.azure_subscription_id or "").lower() == (subscription_id or "").lower()
            and (component.azure_resource_group_name or "").lower() == (resource_group_name or "").lower()
            for component in self.verified_components.values()
        )


class TelemetryAccessRules:
    """The access rules, evaluated against one database session (the caller's, so uncommitted changes are visible)."""

    def __init__(self, session: AsyncSession, settings: Settings, resolver: WorkspaceCustomerIdResolver):
        self.session = session
        self.settings = settings
        self.resolver = resolver

    # ── Rule 1: approved applications only ─────────────────────────────────────
    async def ensure_application_approved(self, application_id: str) -> None:
        lifecycle_status = await self.session.scalar(select(Application.lifecycle_status).where(Application.application_id == application_id))
        if lifecycle_status is None:
            raise NotFoundException("The application was not found.")
        if lifecycle_status in UNAPPROVED_LIFECYCLE_STATUSES:
            raise ForbiddenException(NOT_APPROVED_MESSAGE)

    # ── Rule 2: only the application's own resources ───────────────────────────
    async def load_scope(self, application_id: str) -> ApplicationTelemetryScope:
        lifecycle_status = await self.session.scalar(select(Application.lifecycle_status).where(Application.application_id == application_id))
        if lifecycle_status is None:
            raise NotFoundException("The application was not found.")
        scope = ApplicationTelemetryScope(application_id=application_id, lifecycle_status=lifecycle_status)
        verified_components = (
            await self.session.scalars(
                select(ApplicationComponent).where(
                    ApplicationComponent.application_id == application_id,
                    ApplicationComponent.component_type == "azure_resource_group",
                    ApplicationComponent.access_verification_status == "verified",
                )
            )
        ).all()
        scope.verified_components = {component.component_id: component for component in verified_components}
        if not scope.verified_components:
            return scope
        discovered_resources = (
            await self.session.scalars(
                select(DiscoveredResource).where(
                    DiscoveredResource.application_id == application_id,
                    DiscoveredResource.component_id.in_(list(scope.verified_components)),
                    DiscoveredResource.no_longer_found_at.is_(None),
                )
            )
        ).all()
        for resource in discovered_resources:
            source_kind = classify_resource(resource.resource_type, resource.resource_kind, resource.resource_name).source_kind
            if source_kind == WORKSPACE_SOURCE_KIND:
                scope.workspace_component_by_resource_id[resource.azure_resource_id.lower()] = resource.component_id
            elif source_kind == APPLICATION_INSIGHTS_SOURCE_KIND:
                scope.application_insights_resource_ids.add(resource.azure_resource_id.lower())
            # A workspace that one of the application's own resources already sends its logs to is the application's too.
            for workspace_resource_id in resource.log_analytics_workspace_resource_ids_json or []:
                scope.workspace_component_by_resource_id.setdefault(workspace_resource_id.lower(), resource.component_id)
        return scope

    async def _workspace_customer_ids(self, scope: ApplicationTelemetryScope) -> set[str]:
        customer_ids: set[str] = set()
        for workspace_resource_id, component_id in scope.workspace_component_by_resource_id.items():
            component = scope.verified_components[component_id]
            is_simulated = self.settings.telemetry_mode == IntegrationMode.SIMULATED or bool((component.component_configuration_json or {}).get("simulated"))
            customer_id = await self.resolver.customer_id_of(component.azure_tenant_id, workspace_resource_id, is_simulated)
            if customer_id:
                customer_ids.add(customer_id.lower())
        return customer_ids

    async def log_source_problems(
        self,
        application_id: str,
        source_kind: str,
        workspace_resource_id: str | None,
        workspace_customer_id: str | None,
        log_tool_connection: "LogToolConnection | None" = None,
    ) -> list[FieldProblem]:
        """Why this log source may not be read for the application (empty when it may)."""
        if source_kind == "log_tool":
            return self._log_tool_problems(application_id, log_tool_connection)
        if source_kind not in ("log_analytics", "application_insights"):
            return []
        scope = await self.load_scope(application_id)
        problems: list[FieldProblem] = []
        allowed_resource_ids = set(scope.workspace_component_by_resource_id)
        if source_kind == "application_insights":
            allowed_resource_ids |= scope.application_insights_resource_ids
        if workspace_resource_id and workspace_resource_id.lower() not in allowed_resource_ids:
            what = "workspace" if source_kind == "log_analytics" else "workspace or Application Insights resource"
            problems.append(FieldProblem(
                "logAnalyticsWorkspaceResourceId",
                f"This {what} was not found in this application's verified Azure resource groups, so Keigan will not read it. "
                "Add the resource group that holds it as a component, verify access and run discovery, then choose it again.",
            ))
        if workspace_customer_id and workspace_customer_id.lower() not in await self._workspace_customer_ids(scope):
            problems.append(FieldProblem(
                "logAnalyticsWorkspaceCustomerId",
                "This workspace ID does not match any Log Analytics workspace of this application. Copy it from the workspace's overview page.",
            ))
        return problems

    @staticmethod
    def _log_tool_problems(application_id: str, connection: "LogToolConnection | None") -> list[FieldProblem]:
        if connection is None or connection.application_id != application_id:
            return [FieldProblem("logToolConnectionId", "Choose a log tool connection of this application.")]
        return []

    async def azure_resource_problems(self, application_id: str, azure_resource_id: str | None, field_name: str) -> list[FieldProblem]:
        """Why this Azure resource id is outside the application's verified resource groups (empty when it is inside or not an Azure id)."""
        scope_match = AZURE_RESOURCE_SCOPE_PATTERN.match(azure_resource_id or "")
        if scope_match is None:
            return []
        scope = await self.load_scope(application_id)
        if scope.contains_resource_group(scope_match.group(1), scope_match.group(2)):
            return []
        return [FieldProblem(
            field_name,
            "This Azure resource is not in a verified resource group of this application, so Keigan will not read it. "
            "Add its resource group as a component and verify access first.",
        )]


class TelemetryAccessPolicy:
    """Raises :class:`ForbiddenException` before Keigan reads telemetry the application is not entitled to. Called by the gateway."""

    def __init__(self, session_scope: SessionScope, settings: Settings, resolver: WorkspaceCustomerIdResolver):
        self.session_scope = session_scope
        self.settings = settings
        self.resolver = resolver

    @asynccontextmanager
    async def _rules(self, session: AsyncSession | None) -> AsyncIterator[TelemetryAccessRules]:
        if session is not None:
            yield TelemetryAccessRules(session, self.settings, self.resolver)
            return
        async with self.session_scope() as own_session:
            yield TelemetryAccessRules(own_session, self.settings, self.resolver)

    @staticmethod
    def _refuse(problems: list[FieldProblem], subject: str) -> None:
        if problems:
            logger.warning("Telemetry read refused for %s: %s", subject, problems[0].message)
            raise ForbiddenException(f"Keigan will not read {subject}. {problems[0].message}")

    async def ensure_application_approved(self, application_id: str, session: AsyncSession | None = None) -> None:
        async with self._rules(session) as rules:
            await rules.ensure_application_approved(application_id)

    async def ensure_can_read_source(self, target: "TelemetryTarget", session: AsyncSession | None = None) -> None:
        """Logs, and the read test of a source: approved application and a source that belongs to it."""
        async with self._rules(session) as rules:
            await rules.ensure_application_approved(target.application_id)
            if target.source_kind == "azure_monitor_metrics":
                self._refuse(await rules.azure_resource_problems(target.application_id, target.azure_resource_id, "externalResourceIdentifier"), f"{target.service_name} metrics")
            elif target.source_kind != "log_tool" or target.log_tool_connection is not None:
                self._refuse(
                    await rules.log_source_problems(
                        target.application_id, target.source_kind, target.log_analytics_workspace_resource_id,
                        target.log_analytics_workspace_customer_id, target.log_tool_connection,
                    ),
                    f"{target.service_name} logs",
                )

    async def ensure_can_read_metrics(self, target: "TelemetryTarget", session: AsyncSession | None = None) -> None:
        async with self._rules(session) as rules:
            await rules.ensure_application_approved(target.application_id)
            self._refuse(await rules.azure_resource_problems(target.application_id, target.azure_resource_id, "externalResourceIdentifier"), f"{target.service_name} metrics")

    async def ensure_can_read_activity(
        self, application_id: str, azure_subscription_id: str | None, azure_resource_group_name: str | None, session: AsyncSession | None = None
    ) -> None:
        async with self._rules(session) as rules:
            await rules.ensure_application_approved(application_id)
            if azure_subscription_id:
                resource_scope = f"/subscriptions/{azure_subscription_id}/resourceGroups/{azure_resource_group_name or ''}"
                self._refuse(await rules.azure_resource_problems(application_id, resource_scope, "azureResourceGroupName"), "this application's activity log")

    async def ensure_can_use_connection(self, connection: "LogToolConnection", session: AsyncSession | None = None) -> None:
        """A log tool connection is read for its own application only, and only once that application is approved."""
        async with self._rules(session) as rules:
            await rules.ensure_application_approved(connection.application_id)


def raise_if_field_problems(detail: str, problems: list[FieldProblem]) -> None:
    """Save-time form of the rules: a 422 with one field error per problem."""
    if problems:
        raise BusinessValidationException(detail, field_errors=[problem.as_field_error() for problem in problems])

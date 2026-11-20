"""Readiness: one object that drives the stepper icons, the readiness bar and the go-live checklist."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.application_dtos import ReadinessResponse, RequirementResponse, StepStatusResponse
from keigan.entities.alert_entities import AlertSource, NoiseReductionPolicy
from keigan.entities.application_entities import (
    Application,
    ApplicationComponent,
    DiscoveredResource,
    LogToolConnection,
    MonitoredService,
    ServiceLogSource,
)
from keigan.entities.incident_entities import ServiceNowAssignmentGroup
from keigan.entities.knowledge_entities import ApplicationTopology, KnowledgeDocument, Runbook
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.slo_entities import ServiceLevelObjective
from keigan.entities.status_values import AccessVerificationStatus, ApplicationLifecycleStatus, ComponentType, DocumentDigestStatus, LogToolConnectionStatus, NoisePolicyMode, ReadTestStatus, TopologyGenerationStatus, TopologyReviewStatus

STEP_ORDER = ["components", "services", "log_tools", "knowledge", "topology", "runbooks", "incidents", "slo", "notifications", "access", "review"]
STEP_BY_REQUIREMENT = {
    "components": "components",
    "monitored_service": "services",
    "telemetry_source": "services",
    "incident_intake": "incidents",
    "stakeholder": "notifications",
    "slo": "slo",
}
NON_AZURE_COMPONENT_TYPES = {ComponentType.HARDWARE, ComponentType.MAINFRAME, ComponentType.SAAS_PLATFORM}


class ApplicationReadinessService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _count(self, counted_column: Any, *conditions: Any) -> int:
        return int((await self.session.scalar(select(func.count(counted_column)).where(*conditions))) or 0)

    async def build_readiness(self, application: Application) -> ReadinessResponse:
        application_id = application.application_id
        components = list((await self.session.scalars(select(ApplicationComponent).where(ApplicationComponent.application_id == application_id))).all())
        enabled_service_count = await self._count(
            MonitoredService.service_id, MonitoredService.application_id == application_id, MonitoredService.is_monitoring_enabled.is_(True)
        )
        service_count = await self._count(MonitoredService.service_id, MonitoredService.application_id == application_id)
        passed_source_count = await self._count(
            ServiceLogSource.service_log_source_id,
            ServiceLogSource.last_read_test_status == ReadTestStatus.PASSED,
            ServiceLogSource.service_id.in_(select(MonitoredService.service_id).where(MonitoredService.application_id == application_id)),
        )
        group_count = await self._count(ServiceNowAssignmentGroup.assignment_group_id, ServiceNowAssignmentGroup.application_id == application_id)
        alert_source_count = await self._count(AlertSource.alert_source_id, AlertSource.application_id == application_id)
        stakeholder_count = await self._count(Stakeholder.stakeholder_id, Stakeholder.application_id == application_id, Stakeholder.is_active.is_(True))
        slo_count = await self._count(ServiceLevelObjective.slo_id, ServiceLevelObjective.application_id == application_id)
        document_count = await self._count(KnowledgeDocument.knowledge_document_id, KnowledgeDocument.application_id == application_id)
        pending_document_count = await self._count(
            KnowledgeDocument.knowledge_document_id,
            KnowledgeDocument.application_id == application_id,
            KnowledgeDocument.ai_digest_status.in_([DocumentDigestStatus.PENDING, DocumentDigestStatus.RUNNING]),
        )
        runbook_count = await self._count(Runbook.runbook_id, Runbook.application_id == application_id)
        log_tool_count = await self._count(LogToolConnection.log_tool_connection_id, LogToolConnection.application_id == application_id)
        placeholder_tool_count = await self._count(
            LogToolConnection.log_tool_connection_id,
            LogToolConnection.application_id == application_id,
            LogToolConnection.connection_status == LogToolConnectionStatus.READER_NOT_AVAILABLE,
        )
        current_topology = await self.session.scalar(
            select(ApplicationTopology).where(ApplicationTopology.application_id == application_id, ApplicationTopology.is_current_version.is_(True)).limit(1)
        )
        resources_without_diagnostics = await self._count(
            DiscoveredResource.discovered_resource_id,
            DiscoveredResource.application_id == application_id,
            DiscoveredResource.monitoring_classification == "monitored_service",
            DiscoveredResource.has_diagnostic_setting.is_(False),
            DiscoveredResource.no_longer_found_at.is_(None),
        )
        noise_policy = await self.session.get(NoiseReductionPolicy, application_id)

        verified_component_count = sum(
            1
            for component in components
            if component.access_verification_status == AccessVerificationStatus.VERIFIED
            or (component.component_type in NON_AZURE_COMPONENT_TYPES and (log_tool_count > 0 or passed_source_count > 0 or component.access_verification_status == AccessVerificationStatus.NOT_APPLICABLE))
        )
        required = [
            RequirementResponse(requirement_key="components", step_key="components", is_done=verified_component_count > 0, count=verified_component_count),
            RequirementResponse(requirement_key="monitored_service", step_key="services", is_done=enabled_service_count > 0, count=enabled_service_count),
            RequirementResponse(requirement_key="telemetry_source", step_key="services", is_done=passed_source_count > 0, count=passed_source_count),
            RequirementResponse(requirement_key="incident_intake", step_key="incidents", is_done=(group_count + alert_source_count) > 0, count=group_count + alert_source_count),
            RequirementResponse(requirement_key="stakeholder", step_key="notifications", is_done=stakeholder_count > 0, count=stakeholder_count),
            RequirementResponse(requirement_key="slo", step_key="slo", is_done=slo_count > 0, count=slo_count),
        ]
        topology_reviewed = current_topology is not None and current_topology.review_status == TopologyReviewStatus.REVIEWED
        good_to_know = [
            RequirementResponse(requirement_key="diagnostic_settings", step_key="services", is_done=resources_without_diagnostics == 0, count=resources_without_diagnostics),
            RequirementResponse(requirement_key="knowledge_documents", step_key="knowledge", is_done=document_count > 0, count=document_count),
            RequirementResponse(requirement_key="topology_reviewed", step_key="topology", is_done=topology_reviewed),
            RequirementResponse(requirement_key="runbooks", step_key="runbooks", is_done=runbook_count > 0, count=runbook_count),
            RequirementResponse(requirement_key="placeholder_integrations", step_key="log_tools", is_done=placeholder_tool_count == 0, count=placeholder_tool_count),
            RequirementResponse(requirement_key="observe_mode", step_key="incidents", is_done=noise_policy is None or noise_policy.policy_mode != NoisePolicyMode.OBSERVE),
        ]

        is_live = application.lifecycle_status in (ApplicationLifecycleStatus.LIVE, ApplicationLifecycleStatus.PAUSED)
        component_statuses = {component.access_verification_status for component in components}
        if verified_component_count > 0:
            components_status = "done"
        elif not components:
            components_status = "not_started"
        elif component_statuses & {AccessVerificationStatus.CHECKING, AccessVerificationStatus.MISSING_ROLES}:
            components_status = "waiting"  # a new Azure role can take minutes to apply; the UI keeps polling
        elif AccessVerificationStatus.FAILED in component_statuses:
            components_status = "blocked"
        else:
            components_status = "in_progress"
        topology_status = "not_started"
        if current_topology is not None:
            topology_status = {TopologyGenerationStatus.BUILDING: "waiting", "failed": "blocked"}.get(current_topology.generation_status, "done" if topology_reviewed else "in_progress")
        all_required_done = all(item.is_done for item in required)
        status_by_step = {
            "components": components_status,
            "services": "done" if enabled_service_count and passed_source_count else ("in_progress" if service_count else "not_started"),
            "log_tools": "done" if log_tool_count else "not_started",
            "knowledge": "waiting" if pending_document_count else ("done" if document_count else "not_started"),
            "topology": topology_status,
            "runbooks": "done" if runbook_count else "not_started",
            "incidents": "done" if (group_count + alert_source_count) else "not_started",
            "slo": "done" if slo_count else "not_started",
            "notifications": "done" if stakeholder_count else "not_started",
            "access": "done" if (is_live or application.admin_group_object_id) else "in_progress",
            "review": "done" if is_live else ("in_progress" if all_required_done else "not_started"),
        }
        steps = [StepStatusResponse(step_key=step_key, status=status_by_step[step_key]) for step_key in STEP_ORDER]  # type: ignore[arg-type]
        next_step_key = next((STEP_BY_REQUIREMENT[item.requirement_key] for item in required if not item.is_done), None if is_live else "review")
        return ReadinessResponse(required=required, good_to_know=good_to_know, can_go_live=all_required_done, steps=steps, next_step_key=next_step_key)

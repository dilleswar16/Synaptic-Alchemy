"""One application with a row in every table that points at an application, an incident, an investigation, an SLI or a service.

Integrity tests (H11, H12) use it to prove what a delete leaves behind. Each call makes a fresh application, so tests never share rows.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import timedelta

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import Alert, AlertDecision, AlertEvent, AlertGroup, AlertMuteRule, AlertSource, MaintenanceWindow, NoiseReductionPolicy
from keigan.entities.application_entities import (
    Application,
    ApplicationComponent,
    ApplicationRecordLink,
    DiscoveredResource,
    ExternalIntegration,
    LogToolConnection,
    MonitoredService,
    ServiceDependency,
    ServiceLogSource,
)
from keigan.entities.incident_entities import (
    Conversation,
    ConversationMessage,
    Incident,
    IncidentCommunication,
    Investigation,
    InvestigationEvidence,
    InvestigationHypothesis,
    InvestigationTimelineEvent,
    PostmortemReport,
    ServiceNowAssignmentGroup,
)
from keigan.entities.knowledge_entities import ApplicationTopology, KnowledgeChunk, KnowledgeDocument, Runbook, TopologyReviewComment
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder, TeamsIncidentChat
from keigan.entities.slo_entities import IntelligenceReport, PredictiveSignal, ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement, SloBurnAlert
from keigan.utils.time_utils import utc_now

_code_counter = itertools.count(1)


@dataclass(frozen=True)
class ApplicationGraph:
    application_id: str
    first_service_id: str
    second_service_id: str
    incident_id: str
    investigation_id: str
    alert_group_id: str
    runbook_id: str
    knowledge_document_id: str
    sli_id: str


async def create_application_graph() -> ApplicationGraph:
    code = f"GRF{next(_code_counter):04d}"
    now = utc_now()
    async with open_session() as session:
        application = Application(application_name=f"Graph {code}", application_code=code, lifecycle_status="draft", admin_group_name=f"{code}_admin", reader_group_name=f"{code}_reader")
        session.add(application)
        await session.flush()
        application_id = application.application_id
        component = ApplicationComponent(application_id=application_id, component_type="azure_resource_group", component_name="rg")
        session.add(component)
        await session.flush()
        session.add(DiscoveredResource(component_id=component.component_id, application_id=application_id, azure_resource_id="/subscriptions/x/rg", resource_name="rg", resource_type="t"))
        first_service = MonitoredService(application_id=application_id, component_id=component.component_id, service_name="first", service_type="aks")
        second_service = MonitoredService(application_id=application_id, service_name="second", service_type="aks")
        session.add_all([first_service, second_service])
        await session.flush()
        session.add(ServiceDependency(application_id=application_id, upstream_service_id=first_service.service_id, downstream_service_id=second_service.service_id))
        connection = LogToolConnection(application_id=application_id, tool_type="elastic", connection_name="elastic")
        session.add(connection)
        await session.flush()
        session.add(ServiceLogSource(service_id=first_service.service_id, source_kind="elastic", log_tool_connection_id=connection.log_tool_connection_id))
        session.add_all([
            ApplicationRecordLink(application_id=application_id, record_system="servicenow", record_identifier="CI1"),
            ServiceNowAssignmentGroup(application_id=application_id, group_name="group"),
            ExternalIntegration(application_id=application_id, integration_kind="servicenow"),
            NoiseReductionPolicy(application_id=application_id),
            AlertMuteRule(application_id=application_id, rule_name="mute", mute_reason="test", expires_at=now + timedelta(days=1)),
        ])
        service_ids = [first_service.service_id, second_service.service_id]

        window = MaintenanceWindow(application_id=application_id, window_name="window", starts_at=now, ends_at=now + timedelta(hours=1))
        window.replace_linked_ids("service_links", service_ids)
        stakeholder = Stakeholder(application_id=application_id, display_name="Sam")
        stakeholder.replace_linked_ids("subscribed_service_links", service_ids)
        runbook = Runbook(application_id=application_id, runbook_title="runbook")
        runbook.replace_linked_ids("service_links", service_ids)
        document = KnowledgeDocument(
            application_id=application_id, service_id=first_service.service_id, document_title="doc", document_category="runbook", original_file_name="doc.md", content_type="text/markdown",
            storage_path="doc.md", file_sha256_hash="0" * 64,
        )
        topology = ApplicationTopology(application_id=application_id)
        session.add_all([window, stakeholder, runbook, document, topology])
        await session.flush()
        topology.replace_linked_ids("source_document_links", [document.knowledge_document_id])
        session.add_all([
            KnowledgeChunk(knowledge_document_id=document.knowledge_document_id, application_id=application_id, service_id=first_service.service_id, chunk_sequence_number=0, chunk_text="text"),
            TopologyReviewComment(topology_id=topology.topology_id, review_verdict="looks_right", reviewer_user_principal_name="r@example.com"),
        ])

        sli = ServiceLevelIndicator(application_id=application_id, service_id=first_service.service_id, sli_name="availability", sli_kind="availability", data_source_kind="azure_monitor_metrics")
        session.add(sli)
        await session.flush()
        slo = ServiceLevelObjective(sli_id=sli.sli_id, application_id=application_id, target_percentage=99.9)
        session.add(slo)
        await session.flush()
        report = IntelligenceReport(application_id=application_id, report_type="weekly_digest", report_title="report", report_period_start=now, report_period_end=now)
        session.add_all([
            SliMeasurement(sli_id=sli.sli_id, measurement_window_start=now),
            SloBurnAlert(slo_id=slo.slo_id, application_id=application_id, burn_alert_severity="page", long_window_burn_rate=1.0, short_window_burn_rate=1.0),
            PredictiveSignal(application_id=application_id, service_id=first_service.service_id, sli_id=sli.sli_id, detector_name="trend", signal_title="signal"),
            report,
        ])

        incident = Incident(application_id=application_id, incident_title="incident")
        incident.replace_linked_ids("affected_service_links", service_ids)
        session.add(incident)
        await session.flush()
        investigation = Investigation(application_id=application_id, incident_id=incident.incident_id)
        investigation.replace_linked_ids("investigated_service_links", service_ids)
        investigation.replace_linked_ids("matched_runbook_links", [runbook.runbook_id])
        session.add(investigation)
        await session.flush()
        alert_group = AlertGroup(application_id=application_id, group_title="group", primary_service_id=first_service.service_id, investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        alert_group.replace_linked_ids("affected_service_links", service_ids)
        source = AlertSource(application_id=application_id, source_tool="generic", source_name="source", webhook_secret_hash="hash")
        session.add_all([alert_group, source])
        await session.flush()
        alert = Alert(application_id=application_id, alert_source_id=source.alert_source_id, alert_fingerprint="f", rule_name="rule", service_id=first_service.service_id, alert_group_id=alert_group.alert_group_id)
        session.add_all([alert, AlertEvent(alert_source_id=source.alert_source_id, application_id=application_id)])
        await session.flush()
        session.add(AlertDecision(alert_id=alert.alert_id, alert_group_id=alert_group.alert_group_id, pipeline_stage="group", decision_outcome="new_group", decision_reason="test"))

        conversation = Conversation(conversation_scope="investigation", investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        conversation.replace_linked_ids("application_links", [application_id])
        session.add(conversation)
        await session.flush()
        session.add_all([
            ConversationMessage(conversation_id=conversation.conversation_id, author_role="user", message_text="hi"),
            InvestigationEvidence(
                investigation_id=investigation.investigation_id, evidence_code="E1", service_id=first_service.service_id, evidence_source_kind="log_analytics", evidence_category="logs", evidence_title="evidence",
            ),
            InvestigationHypothesis(investigation_id=investigation.investigation_id, analysis_perspective="application", hypothesis_title="hypothesis"),
            InvestigationTimelineEvent(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, event_type="note", event_title="timeline"),
            IncidentCommunication(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, communication_type="initial_update", subject_line="subject", body_markdown="body"),
            PostmortemReport(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, report_title="postmortem"),
            NotificationDelivery(
                application_id=application_id, incident_id=incident.incident_id, investigation_id=investigation.investigation_id, notification_type="incident_detected", delivery_channel="email", recipient_address="a@example.com",
            ),
            TeamsIncidentChat(incident_id=incident.incident_id, application_id=application_id, teams_chat_identifier="19:x", chat_topic="topic", conversation_id=conversation.conversation_id),
        ])
        return ApplicationGraph(
            application_id=application_id, first_service_id=first_service.service_id, second_service_id=second_service.service_id, incident_id=incident.incident_id,
            investigation_id=investigation.investigation_id, alert_group_id=alert_group.alert_group_id, runbook_id=runbook.runbook_id, knowledge_document_id=document.knowledge_document_id, sli_id=sli.sli_id,
        )

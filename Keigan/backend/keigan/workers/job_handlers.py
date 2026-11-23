"""Job type → service method table. This is the contract between the queue and the vertical slices.

Each job runs ``ServiceClass(session).method_name(**job_payload)`` in its own transaction. Slices implement the
listed methods with exactly these keyword arguments. Payload values must be JSON-serialisable.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from keigan.config.database_config import open_session


@dataclass(frozen=True)
class JobHandlerReference:
    module_path: str
    service_class_name: str
    method_name: str


JOB_HANDLER_REFERENCES: dict[str, JobHandlerReference] = {
    "evaluate_error_budget_policy": JobHandlerReference("keigan.services.error_budget_policy_service", "ErrorBudgetPolicyService", "evaluate_application"),  # application_id
    "send_action_item_reminders": JobHandlerReference("keigan.services.action_item_reminders", "ActionItemReminderService", "send_due_reminders"),  # application_id
    # ── S1 applications, onboarding, knowledge ────────────────────────────────
    "verify_component_access": JobHandlerReference("keigan.services.onboarding_service", "OnboardingService", "verify_component_access"),  # component_id
    "discover_component": JobHandlerReference("keigan.services.onboarding_service", "OnboardingService", "discover_component"),  # component_id
    "digest_knowledge_document": JobHandlerReference("keigan.services.knowledge_service", "KnowledgeService", "digest_document"),  # knowledge_document_id
    "build_topology": JobHandlerReference("keigan.services.knowledge_service", "KnowledgeService", "build_topology"),  # application_id, requested_by_user_principal_name
    # ── S2 incidents, investigations, communications ──────────────────────────
    "poll_servicenow": JobHandlerReference("keigan.services.incident_service", "IncidentService", "poll_servicenow_for_application"),  # application_id
    "run_investigation": JobHandlerReference("keigan.services.investigation_service", "InvestigationService", "run_investigation"),  # investigation_id
    "generate_communications": JobHandlerReference("keigan.services.communication_service", "CommunicationService", "generate_communications"),  # investigation_id, communication_types, language_codes
    "generate_postmortem": JobHandlerReference("keigan.services.communication_service", "CommunicationService", "generate_postmortem"),  # incident_id, generation_trigger, requested_by_user_principal_name
    # ── S3 alerts and SLOs ─────────────────────────────────────────────────────
    "process_alert_event": JobHandlerReference("keigan.services.alert_service", "AlertService", "process_alert_event"),  # alert_event_id
    "settle_alert": JobHandlerReference("keigan.services.alert_service", "AlertService", "complete_settle_stage"),  # alert_id
    "simulate_alerts_for_scenario": JobHandlerReference("keigan.services.alert_service", "AlertService", "simulate_alerts_for_scenario"),  # application_id, scenario_window
    "weekly_noise_report": JobHandlerReference("keigan.services.alert_service", "AlertService", "build_noise_report"),  # application_id
    "measure_sli_proposals": JobHandlerReference("keigan.services.slo_service", "SloService", "measure_proposals"),  # application_id
    "backfill_sli": JobHandlerReference("keigan.services.slo_service", "SloService", "backfill_sli"),  # sli_id
    "collect_sli_measurements": JobHandlerReference("keigan.services.slo_service", "SloService", "collect_due_measurements"),  # application_id
    "evaluate_burn_rates": JobHandlerReference("keigan.services.slo_service", "SloService", "evaluate_burn_rates"),  # application_id
    # ── S4 notifications, Teams, intelligence ──────────────────────────────────
    "notify_incident_detected": JobHandlerReference("keigan.services.notification_service", "NotificationService", "on_incident_detected"),  # incident_id
    "notify_investigation_completed": JobHandlerReference("keigan.services.notification_service", "NotificationService", "on_investigation_completed"),  # investigation_id
    "deliver_notification": JobHandlerReference("keigan.services.notification_service", "NotificationService", "deliver"),  # notification_delivery_id
    "create_incident_chat": JobHandlerReference("keigan.services.notification_service", "NotificationService", "create_incident_chat"),  # incident_id
    "poll_incident_chat": JobHandlerReference("keigan.services.notification_service", "NotificationService", "poll_incident_chat"),  # teams_incident_chat_id
    "run_predictive_analysis": JobHandlerReference("keigan.services.intelligence_service", "IntelligenceService", "run_detectors_for_application"),  # application_id
    "send_intelligence_report": JobHandlerReference("keigan.services.intelligence_service", "IntelligenceService", "generate_and_send_report"),  # application_id, report_type
    # ── Lead / platform ────────────────────────────────────────────────────────
    "retention_cleanup": JobHandlerReference("keigan.services.administration_service", "AdministrationService", "run_retention_cleanup"),  # (no arguments)
}


async def execute_job_handler(job_type: str, job_payload: dict[str, Any]) -> Any:
    handler_reference = JOB_HANDLER_REFERENCES.get(job_type)
    if handler_reference is None:
        raise NotImplementedError(f"No handler is registered for job type {job_type}.")
    service_module = importlib.import_module(handler_reference.module_path)
    service_class = getattr(service_module, handler_reference.service_class_name)
    async with open_session() as session:
        service_instance = service_class(session)
        handler_method = getattr(service_instance, handler_reference.method_name, None)
        if handler_method is None:
            raise NotImplementedError(f"{handler_reference.service_class_name}.{handler_reference.method_name} is not implemented yet.")
        return await handler_method(**job_payload)

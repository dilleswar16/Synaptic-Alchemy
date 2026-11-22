"""Incident and investigation entities, communications, postmortems and conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now
from keigan.entities.linked_ids import LinkedIdsMixin, OrderedLinkColumns, linked_ids_property, ordered_links_relationship
from keigan.entities.status_values import AnalysisPerspective, AssignmentGroupVerificationStatus, BaselineComparison, ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepKind, ChatRunStepStatus, CommunicationStatus, ConversationScope, CoverageGapKind, CoverageGapReason, EvidenceCheckOutcome, HypothesisState, HypothesisStateGuard, IncidentSource, IncidentStatus, InvestigationAiCallFailure, InvestigationDecisionKind, InvestigationFeedbackVerdict, InvestigationOutcome, InvestigationOutcomeGuard, InvestigationStage, InvestigationStatus, InvestigationTraceStepKind, InvestigationTraceStepStatus, InvestigationTrigger, MessageAuthorRole, PostmortemStatus, Priority, RiskLevel, ToolCallingMode, values_check


class ServiceNowAssignmentGroup(EntityBase):
    __tablename__ = "servicenow_assignment_group"
    __table_args__ = (
        UniqueConstraint("application_id", "group_name", name="uq_servicenow_group_per_application"),
        values_check("verification_status", AssignmentGroupVerificationStatus),
    )

    assignment_group_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    group_name: Mapped[str] = mapped_column(String(200))
    servicenow_sys_id: Mapped[str | None] = mapped_column(String(64))
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Incident(LinkedIdsMixin, AuditColumnsMixin, EntityBase):
    link_relationship_names = ("affected_service_links",)

    __tablename__ = "incident"
    __table_args__ = (
        # Filtered: manual and alert-born incidents may have no ticket number (SQL Server unique constraints allow only one NULL).
        Index(
            "uq_incident_external_number", "application_id", "external_incident_number", unique=True,
            mssql_where=text("external_incident_number IS NOT NULL"),
            postgresql_where=text("external_incident_number IS NOT NULL"),
            sqlite_where=text("external_incident_number IS NOT NULL"),
        ),
        Index("ix_incident_application_status_opened", "application_id", "incident_status", "opened_at"),
        values_check("incident_source", IncidentSource),
        values_check("incident_status", IncidentStatus),
        values_check("keigan_priority", Priority),
    )

    incident_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    incident_source: Mapped[str] = mapped_column(String(20), default="servicenow")
    external_incident_number: Mapped[str | None] = mapped_column(String(40), index=True)
    external_system_identifier: Mapped[str | None] = mapped_column(String(64))
    incident_title: Mapped[str] = mapped_column(String(500))
    incident_description: Mapped[str | None] = mapped_column(Text)
    servicenow_priority: Mapped[str | None] = mapped_column(String(10))
    servicenow_impact: Mapped[str | None] = mapped_column(String(10))
    servicenow_urgency: Mapped[str | None] = mapped_column(String(10))
    keigan_priority: Mapped[str | None] = mapped_column(String(4))
    priority_rationale: Mapped[str | None] = mapped_column(Text)
    incident_category: Mapped[str | None] = mapped_column(String(40))
    incident_status: Mapped[str] = mapped_column(String(20), default="new")
    affected_service_links: Mapped[list[IncidentAffectedService]] = ordered_links_relationship("IncidentAffectedService")
    affected_service_ids = linked_ids_property("affected_service_links")
    assignment_group_name: Mapped[str | None] = mapped_column(String(200))
    external_state: Mapped[str | None] = mapped_column(String(40))
    opened_at: Mapped[datetime] = mapped_column(default=utc_now)
    detected_by_keigan_at: Mapped[datetime] = mapped_column(default=utc_now)
    first_update_sent_at: Mapped[datetime | None] = mapped_column()
    resolved_at: Mapped[datetime | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column()
    external_last_updated_at: Mapped[datetime | None] = mapped_column()


class IncidentAffectedService(OrderedLinkColumns, EntityBase):
    """A service an incident affects. The first one is the incident's primary service."""

    __tablename__ = "incident_affected_service"
    linked_id_attribute = "service_id"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incident.incident_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the incident already cascades from its application, and SQL Server allows one cascade path; deleting a service releases its rows.
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"), primary_key=True, index=True)


class Investigation(LinkedIdsMixin, AuditColumnsMixin, EntityBase):
    link_relationship_names = ("investigated_service_links", "matched_runbook_links")

    __tablename__ = "investigation"
    __table_args__ = (
        Index("ix_investigation_application_created", "application_id", "created_at"),
        values_check("investigation_trigger", InvestigationTrigger),
        values_check("investigation_status", InvestigationStatus),
        values_check("current_stage_name", InvestigationStage),
        values_check("user_feedback_verdict", InvestigationFeedbackVerdict),
        values_check("investigation_outcome", InvestigationOutcome),
        values_check("proposed_investigation_outcome", InvestigationOutcome),
        values_check("outcome_guard_code", InvestigationOutcomeGuard),
    )

    investigation_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    # NO ACTION: investigations already cascade from application; SQL Server allows one path (application deletion removes them first).
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    investigation_trigger: Mapped[str] = mapped_column(String(20), default="incident")
    investigation_status: Mapped[str] = mapped_column(String(30), default="queued")
    current_stage_name: Mapped[str] = mapped_column(String(30), default="triage")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    stage_messages_json: Mapped[list[Any] | None] = mapped_column()
    investigation_window_start: Mapped[datetime | None] = mapped_column()
    investigation_window_end: Mapped[datetime | None] = mapped_column()
    baseline_window_start: Mapped[datetime | None] = mapped_column()
    baseline_window_end: Mapped[datetime | None] = mapped_column()
    investigated_service_links: Mapped[list[InvestigationInvestigatedService]] = ordered_links_relationship("InvestigationInvestigatedService")
    investigated_service_ids = linked_ids_property("investigated_service_links")
    triage_result_json: Mapped[dict[str, Any] | None] = mapped_column()
    executive_summary: Mapped[str | None] = mapped_column(Text)
    what_went_wrong_markdown: Mapped[str | None] = mapped_column(Text)
    why_it_happened_markdown: Mapped[str | None] = mapped_column(Text)
    how_to_fix_markdown: Mapped[str | None] = mapped_column(Text)
    open_questions_json: Mapped[list[str] | None] = mapped_column()
    overall_confidence_score: Mapped[float | None] = mapped_column(Float)
    leading_hypothesis_id: Mapped[str | None] = mapped_column(String(36))
    blast_radius_json: Mapped[dict[str, Any] | None] = mapped_column()
    matched_runbook_links: Mapped[list[InvestigationMatchedRunbook]] = ordered_links_relationship("InvestigationMatchedRunbook")
    matched_runbook_ids = linked_ids_property("matched_runbook_links")
    knowledge_references_json: Mapped[list[Any] | None] = mapped_column()
    user_feedback_verdict: Mapped[str | None] = mapped_column(String(20))
    user_feedback_comment: Mapped[str | None] = mapped_column(Text)
    user_feedback_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    # How far the investigation got (spec 27). Null for rows stored before it, for evidence-only runs and for runs that failed or are still running.
    investigation_outcome: Mapped[str | None] = mapped_column(String(30))
    proposed_investigation_outcome: Mapped[str | None] = mapped_column(String(30))  # what the model said before Keigan's rules
    outcome_guard_code: Mapped[str | None] = mapped_column(String(40))  # the rule that lowered the proposal, if one did
    outcome_reason_markdown: Mapped[str | None] = mapped_column(Text)
    leading_perspective_reason_markdown: Mapped[str | None] = mapped_column(Text)
    total_input_token_count: Mapped[int] = mapped_column(Integer, default=0)
    total_output_token_count: Mapped[int] = mapped_column(Integer, default=0)
    model_names_json: Mapped[list[str] | None] = mapped_column()
    requested_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()


class InvestigationInvestigatedService(OrderedLinkColumns, EntityBase):
    """A service an investigation examined, in the order triage found them."""

    __tablename__ = "investigation_investigated_service"
    linked_id_attribute = "service_id"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the investigation already cascades from its application, and SQL Server allows one cascade path; deleting a service releases its rows.
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"), primary_key=True, index=True)


class InvestigationMatchedRunbook(OrderedLinkColumns, EntityBase):
    """A runbook the investigation matched, best match first."""

    __tablename__ = "investigation_matched_runbook"
    linked_id_attribute = "runbook_id"

    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the investigation already cascades from its application, and SQL Server allows one cascade path; deleting a runbook releases its rows.
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbook.runbook_id"), primary_key=True, index=True)


class InvestigationHypothesis(EntityBase):
    __tablename__ = "investigation_hypothesis"
    __table_args__ = (
        values_check("analysis_perspective", AnalysisPerspective),
        values_check("fix_risk_level", RiskLevel),
        values_check("hypothesis_state", HypothesisState),
        values_check("proposed_hypothesis_state", HypothesisState),
        values_check("state_guard_code", HypothesisStateGuard),
    )

    hypothesis_id: Mapped[str] = identifier_column()
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"), index=True)
    analysis_perspective: Mapped[str] = mapped_column(String(20))
    hypothesis_title: Mapped[str] = mapped_column(String(300))
    hypothesis_statement_markdown: Mapped[str | None] = mapped_column(Text)
    reasoning_markdown: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_evidence_codes_json: Mapped[list[str] | None] = mapped_column()
    contradicting_evidence_codes_json: Mapped[list[str] | None] = mapped_column()
    proposed_fix_json: Mapped[dict[str, Any] | None] = mapped_column()
    fix_risk_level: Mapped[str] = mapped_column(String(10), default="medium")
    matched_runbook_id: Mapped[str | None] = mapped_column(String(36))
    is_leading_hypothesis: Mapped[bool] = mapped_column(Boolean, default=False)
    # The end state after Keigan's rules (spec 27); null for rows stored before it.
    hypothesis_state: Mapped[str | None] = mapped_column(String(20))
    proposed_hypothesis_state: Mapped[str | None] = mapped_column(String(20))  # what the model said before the rules
    state_guard_code: Mapped[str | None] = mapped_column(String(40))  # the rule that lowered the proposal, if one did
    state_reason_markdown: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class InvestigationEvidence(EntityBase):
    __tablename__ = "investigation_evidence"
    __table_args__ = (
        UniqueConstraint("investigation_id", "evidence_code", name="uq_evidence_code_per_investigation"),
        values_check("signal_strength", RiskLevel),
        values_check("check_outcome", EvidenceCheckOutcome),
        values_check("baseline_comparison", BaselineComparison),
    )

    evidence_id: Mapped[str] = identifier_column()
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"), index=True)
    evidence_code: Mapped[str] = mapped_column(String(10))
    service_id: Mapped[str | None] = mapped_column(ForeignKey("monitored_service.service_id"))
    evidence_source_kind: Mapped[str] = mapped_column(String(40))
    evidence_category: Mapped[str] = mapped_column(String(40))
    evidence_title: Mapped[str] = mapped_column(String(300))
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    query_language: Mapped[str] = mapped_column(String(20), default="none")
    query_text: Mapped[str | None] = mapped_column(Text)
    query_time_range_start: Mapped[datetime | None] = mapped_column()
    query_time_range_end: Mapped[datetime | None] = mapped_column()
    matched_record_count: Mapped[int] = mapped_column(Integer, default=0)
    baseline_record_count: Mapped[int | None] = mapped_column(Integer)
    condensed_patterns_json: Mapped[list[Any] | None] = mapped_column()
    metric_series_json: Mapped[list[Any] | None] = mapped_column()
    signal_strength: Mapped[str] = mapped_column(String(10), default="low")
    check_outcome: Mapped[str | None] = mapped_column(String(20))  # spec 27; null for rows stored before it
    baseline_comparison: Mapped[str | None] = mapped_column(String(30))
    masked_value_count: Mapped[int] = mapped_column(Integer, default=0)
    possible_prompt_injection: Mapped[bool] = mapped_column(Boolean, default=False)
    deep_link_url: Mapped[str | None] = mapped_column(String(1000))
    collected_at: Mapped[datetime] = mapped_column(default=utc_now)


class InvestigationCoverageGap(EntityBase):
    """One thing an investigation meant to check and could not, or did not because of a limit (spec 27). Written by code from catalogue names and fixed codes, never from integration text."""

    __tablename__ = "investigation_coverage_gap"
    __table_args__ = (
        values_check("gap_kind", CoverageGapKind),
        values_check("gap_reason_code", CoverageGapReason),
    )

    coverage_gap_id: Mapped[str] = identifier_column()
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"), index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    gap_kind: Mapped[str] = mapped_column(String(40))
    gap_reason_code: Mapped[str | None] = mapped_column(String(40))
    # Recorded facts, not links: the gap outlives a service that is deleted later.
    service_id: Mapped[str | None] = mapped_column(String(36))
    service_name: Mapped[str | None] = mapped_column(String(200))
    source_kind: Mapped[str | None] = mapped_column(String(40))
    parameters_json: Mapped[dict[str, Any] | None] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(default=utc_now)


class InvestigationTraceStep(EntityBase):
    """One ordered step of an investigation's decision trace (spec 28): its inputs, an AI call, the evidence summary, a deterministic decision or the outcome.

    Written by code from ids, codes, numbers and catalogue names; the raw output of an AI call is masked and cut. The investigation row is the run, so a step needs nothing else.
    """

    __tablename__ = "investigation_trace_step"
    __table_args__ = (
        UniqueConstraint("investigation_id", "sequence_number", name="uq_investigation_trace_step_investigation_id_sequence_number"),
        values_check("stage_name", InvestigationStage),
        values_check("step_kind", InvestigationTraceStepKind),
        values_check("step_status", InvestigationTraceStepStatus),
        values_check("decision_kind", InvestigationDecisionKind),
        values_check("failure_code", InvestigationAiCallFailure),
    )

    trace_step_id: Mapped[str] = identifier_column()
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"))
    sequence_number: Mapped[int] = mapped_column(Integer)
    stage_name: Mapped[str] = mapped_column(String(30))
    step_kind: Mapped[str] = mapped_column(String(20))
    step_status: Mapped[str] = mapped_column(String(20))
    decision_kind: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column()
    duration_milliseconds: Mapped[int | None] = mapped_column(Integer)
    feature_name: Mapped[str | None] = mapped_column(String(80))
    prompt_key: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    prompt_template_sha256: Mapped[str | None] = mapped_column(String(64))  # the prompt file plus the fragments it includes
    system_prompt_sha256: Mapped[str | None] = mapped_column(String(64))  # of the rendered system prompt text
    provider_name: Mapped[str | None] = mapped_column(String(40))
    model_name: Mapped[str | None] = mapped_column(String(120))
    model_tier: Mapped[str | None] = mapped_column(String(20))
    input_manifest_json: Mapped[list[Any] | None] = mapped_column()  # per prompt section: size, cut flag, SHA-256, citation codes (never the text)
    estimated_input_token_count: Mapped[int | None] = mapped_column(Integer)  # only when the call wrote no usage rows (mock, offline)
    estimated_output_token_count: Mapped[int | None] = mapped_column(Integer)
    raw_output_json: Mapped[dict[str, Any] | None] = mapped_column()  # the validated answer before Keigan's checks, masked and cut
    raw_output_character_count: Mapped[int | None] = mapped_column(Integer)
    raw_output_is_truncated: Mapped[bool | None] = mapped_column(Boolean)
    raw_output_sha256: Mapped[str | None] = mapped_column(String(64))
    adjustments_json: Mapped[list[Any] | None] = mapped_column()  # what Keigan's code changed in the raw output: [{"code": ..., "parameters": {...}}]
    failure_code: Mapped[str | None] = mapped_column(String(40))
    hypothesis_id: Mapped[str | None] = mapped_column(String(36))  # the hypothesis a hypothesis call produced: a recorded fact, not a link
    details_json: Mapped[dict[str, Any] | None] = mapped_column()


class InvestigationTimelineEvent(EntityBase):
    __tablename__ = "investigation_timeline_event"

    timeline_event_id: Mapped[str] = identifier_column()
    # The incident owns its timeline (CASCADE); NO ACTION on the investigation: SQL Server allows one cascade path and an investigation cascades from the application too.
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"), index=True)
    event_occurred_at: Mapped[datetime] = mapped_column(default=utc_now)
    event_type: Mapped[str] = mapped_column(String(40))
    event_title: Mapped[str] = mapped_column(String(400))
    event_details_markdown: Mapped[str | None] = mapped_column(Text)
    event_source: Mapped[str] = mapped_column(String(40), default="keigan")
    source_reference: Mapped[str | None] = mapped_column(String(400))
    actor_display_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class IncidentCommunication(AuditColumnsMixin, EntityBase):
    __tablename__ = "incident_communication"
    __table_args__ = (
        values_check("communication_status", CommunicationStatus),
    )

    communication_id: Mapped[str] = identifier_column()
    # Same rule as the timeline: the incident cascades, the investigation is NO ACTION.
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"), index=True)
    communication_type: Mapped[str] = mapped_column(String(30))
    audience_type: Mapped[str] = mapped_column(String(20), default="stakeholders")
    language_code: Mapped[str] = mapped_column(String(10), default="en")
    subject_line: Mapped[str] = mapped_column(String(400))
    body_markdown: Mapped[str] = mapped_column(Text)
    communication_status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    approved_at: Mapped[datetime | None] = mapped_column()
    sent_at: Mapped[datetime | None] = mapped_column()


class PostmortemReport(AuditColumnsMixin, EntityBase):
    __tablename__ = "postmortem_report"
    __table_args__ = (
        values_check("report_status", PostmortemStatus),
    )

    postmortem_id: Mapped[str] = identifier_column()
    # Same rule as the timeline: the incident cascades, the investigation is NO ACTION.
    incident_id: Mapped[str] = mapped_column(ForeignKey("incident.incident_id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"))
    report_title: Mapped[str] = mapped_column(String(400))
    report_markdown: Mapped[str | None] = mapped_column(Text)
    report_sections_json: Mapped[dict[str, Any] | None] = mapped_column()
    language_code: Mapped[str] = mapped_column(String(10), default="en")
    report_status: Mapped[str] = mapped_column(String(20), default="generating")
    generation_trigger: Mapped[str] = mapped_column(String(30), default="user_button")
    finalized_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    finalized_at: Mapped[datetime | None] = mapped_column()
    sent_at: Mapped[datetime | None] = mapped_column()


class Conversation(LinkedIdsMixin, AuditColumnsMixin, EntityBase):
    link_relationship_names = ("application_links",)

    __tablename__ = "conversation"
    __table_args__ = (
        values_check("conversation_scope", ConversationScope),
    )

    conversation_id: Mapped[str] = identifier_column()
    conversation_scope: Mapped[str] = mapped_column(String(30))
    application_links: Mapped[list[ConversationApplication]] = ordered_links_relationship("ConversationApplication")
    application_ids = linked_ids_property("application_links")
    # NO ACTION on both: a conversation is scoped to applications through conversation_application (cascade), so it must not also cascade from an incident.
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"), index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    owner_user_principal_name: Mapped[str | None] = mapped_column(String(320), index=True)
    conversation_title: Mapped[str] = mapped_column(String(300), default="New conversation")


class ConversationApplication(OrderedLinkColumns, EntityBase):
    """An application a conversation is scoped to (an empty list means every application the user can read)."""

    __tablename__ = "conversation_application"
    linked_id_attribute = "application_id"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.conversation_id", ondelete="CASCADE"), primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), primary_key=True, index=True)


class ConversationMessage(EntityBase):
    __tablename__ = "conversation_message"
    __table_args__ = (
        values_check("author_role", MessageAuthorRole),
    )

    message_id: Mapped[str] = identifier_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.conversation_id", ondelete="CASCADE"), index=True)
    author_role: Mapped[str] = mapped_column(String(20))
    author_display_name: Mapped[str | None] = mapped_column(String(200))
    author_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    message_text: Mapped[str] = mapped_column(Text, default="")
    message_payload_json: Mapped[dict[str, Any] | None] = mapped_column()
    external_message_identifier: Mapped[str | None] = mapped_column(String(200))
    input_token_count: Mapped[int] = mapped_column(Integer, default=0)
    output_token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


# A run in this state owns its conversation: the database allows only one such run per conversation, however many processes answer questions.
_RUNNING_RUN_FILTER = text(f"run_status = '{ChatAnswerRunStatus.RUNNING.value}'")


class ChatAnswerRun(EntityBase):
    """Everything Keigan did to answer one question in Ask Keigan: the scope it ran with, the model and tools it used, the totals and the cited sources."""

    __tablename__ = "chat_answer_run"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_request_id", name="uq_chat_answer_run_conversation_id_client_request_id"),
        # Filtered unique index (portable like uq_background_job_active_deduplication_key): finished runs stay for history, one running run per conversation.
        Index(
            "uq_chat_answer_run_one_running_per_conversation", "conversation_id", unique=True,
            mssql_where=_RUNNING_RUN_FILTER, postgresql_where=_RUNNING_RUN_FILTER, sqlite_where=_RUNNING_RUN_FILTER,
        ),
        Index("ix_chat_answer_run_requested_by_user_principal_name_started_at", "requested_by_user_principal_name", "started_at"),
        values_check("conversation_scope", ConversationScope),
        values_check("run_status", ChatAnswerRunStatus),
        values_check("stop_reason", ChatAnswerStopReason),
        values_check("tool_calling_mode", ToolCallingMode),
    )

    answer_run_id: Mapped[str] = identifier_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.conversation_id", ondelete="CASCADE"), index=True)
    # NO ACTION on the two message keys and the investigation: SQL Server allows one cascade path per table, so the code deletes runs before messages.
    user_message_id: Mapped[str] = mapped_column(ForeignKey("conversation_message.message_id"))
    assistant_message_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_message.message_id"))
    client_request_id: Mapped[str] = mapped_column(String(64))
    conversation_scope: Mapped[str] = mapped_column(String(30))
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"), index=True)
    requested_by_user_principal_name: Mapped[str] = mapped_column(String(320))
    # A point-in-time audit snapshot of the applications, bound arguments and withheld tools: not a relationship, so not an association table.
    scope_snapshot_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # The applications whose data reached the model through this run's tool calls, kept up to date as the calls finish. Who may still see the answer follows from it: a person who can no
    # longer read any one of them sees none of the run. Null for a run stored before this column existed (an investigation chat, whose access is the investigation's application).
    used_application_ids_json: Mapped[list[str] | None] = mapped_column()
    run_status: Mapped[str] = mapped_column(String(20))
    stop_reason: Mapped[str | None] = mapped_column(String(30))
    engine_version: Mapped[str] = mapped_column(String(20))
    prompt_key: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(20))
    system_prompt_sha256: Mapped[str] = mapped_column(String(64))
    tool_catalog_sha256: Mapped[str] = mapped_column(String(64))
    offered_tools_json: Mapped[list[Any]] = mapped_column(default=list)
    provider_name: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(120))
    model_tier: Mapped[str] = mapped_column(String(20))
    tool_calling_mode: Mapped[str] = mapped_column(String(20))
    limits_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    total_input_token_count: Mapped[int] = mapped_column(Integer, default=0)
    total_output_token_count: Mapped[int] = mapped_column(Integer, default=0)
    token_counts_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    model_turn_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    citations_json: Mapped[list[Any]] = mapped_column(default=list)
    follow_up_questions_json: Mapped[list[Any]] = mapped_column(default=list)
    is_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(60))
    # The low-sensitivity values the error message was written from (the failed step, a limit, a retry delay): a reload words the same message as the live stream did.
    error_parameters_json: Mapped[dict[str, Any] | None] = mapped_column()
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column()
    duration_milliseconds: Mapped[int | None] = mapped_column(Integer)
    last_progress_at: Mapped[datetime] = mapped_column(default=utc_now)


class ChatRunStep(EntityBase):
    """One ordered item of an answer run: a model turn (the model was asked once) or a tool call (one tool ran once)."""

    __tablename__ = "chat_run_step"
    __table_args__ = (
        UniqueConstraint("answer_run_id", "sequence_number", name="uq_chat_run_step_answer_run_id_sequence_number"),
        values_check("step_kind", ChatRunStepKind),
        values_check("step_status", ChatRunStepStatus),
    )

    run_step_id: Mapped[str] = identifier_column()
    answer_run_id: Mapped[str] = mapped_column(ForeignKey("chat_answer_run.answer_run_id", ondelete="CASCADE"))
    sequence_number: Mapped[int] = mapped_column(Integer)
    step_kind: Mapped[str] = mapped_column(String(20))
    # NO ACTION: a tool call names the model turn that requested it; both belong to one run, which cascades.
    parent_run_step_id: Mapped[str | None] = mapped_column(ForeignKey("chat_run_step.run_step_id"))
    step_status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column()
    duration_milliseconds: Mapped[int | None] = mapped_column(Integer)
    # Model turns. turn_finish is left open on purpose: tool_requests, answer, length, protocol_error.
    turn_number: Mapped[int | None] = mapped_column(Integer)
    turn_finish: Mapped[str | None] = mapped_column(String(30))
    model_text: Mapped[str | None] = mapped_column(Text)
    input_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    # Tool calls. The tool name and source come from the tool registry, so adding a tool needs no migration.
    tool_name: Mapped[str | None] = mapped_column(String(64), index=True)
    tool_version: Mapped[int | None] = mapped_column(Integer)
    tool_source: Mapped[str | None] = mapped_column(String(80))
    citation_code: Mapped[str | None] = mapped_column(String(8))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    requested_arguments_json: Mapped[dict[str, Any] | None] = mapped_column()
    effective_arguments_json: Mapped[dict[str, Any] | None] = mapped_column()
    # A recorded fact kept without a foreign key, like audit_event.application_id: the trace outlives the application it was about.
    application_id: Mapped[str | None] = mapped_column(String(36), index=True)
    records_json: Mapped[list[Any] | None] = mapped_column()
    output_json: Mapped[dict[str, Any] | None] = mapped_column()
    output_character_count: Mapped[int | None] = mapped_column(Integer)
    output_is_truncated: Mapped[bool | None] = mapped_column(Boolean)
    output_item_count: Mapped[int | None] = mapped_column(Integer)
    model_view_text: Mapped[str | None] = mapped_column(Text)
    model_view_sha256: Mapped[str | None] = mapped_column(String(64))
    masked_value_count: Mapped[int | None] = mapped_column(Integer)
    injection_flagged: Mapped[bool | None] = mapped_column(Boolean)
    outcome_code: Mapped[str | None] = mapped_column(String(60))
    outcome_message: Mapped[str | None] = mapped_column(String(400))


__all__ = [
    "ChatAnswerRun",
    "ChatRunStep",
    "Conversation",
    "ConversationApplication",
    "ConversationMessage",
    "Incident",
    "IncidentAffectedService",
    "IncidentCommunication",
    "Investigation",
    "InvestigationEvidence",
    "InvestigationHypothesis",
    "InvestigationInvestigatedService",
    "InvestigationMatchedRunbook",
    "InvestigationTimelineEvent",
    "PostmortemReport",
    "ServiceNowAssignmentGroup",
]

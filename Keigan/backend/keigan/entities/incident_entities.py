"""Incident and investigation entities, communications, postmortems and conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now


class ServiceNowAssignmentGroup(EntityBase):
    __tablename__ = "servicenow_assignment_group"
    __table_args__ = (UniqueConstraint("application_id", "group_name", name="uq_servicenow_group_per_application"),)

    assignment_group_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    group_name: Mapped[str] = mapped_column(String(200))
    servicenow_sys_id: Mapped[str | None] = mapped_column(String(64))
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Incident(AuditColumnsMixin, EntityBase):
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
    affected_service_ids_json: Mapped[list[str] | None] = mapped_column()
    assignment_group_name: Mapped[str | None] = mapped_column(String(200))
    external_state: Mapped[str | None] = mapped_column(String(40))
    opened_at: Mapped[datetime] = mapped_column(default=utc_now)
    detected_by_keigan_at: Mapped[datetime] = mapped_column(default=utc_now)
    first_update_sent_at: Mapped[datetime | None] = mapped_column()
    resolved_at: Mapped[datetime | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column()
    external_last_updated_at: Mapped[datetime | None] = mapped_column()


class Investigation(AuditColumnsMixin, EntityBase):
    __tablename__ = "investigation"
    __table_args__ = (Index("ix_investigation_application_created", "application_id", "created_at"),)

    investigation_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    # NO ACTION: investigations already cascade from application; SQL Server allows one path (application deletion removes them first).
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    alert_group_id: Mapped[str | None] = mapped_column(String(36), index=True)
    investigation_trigger: Mapped[str] = mapped_column(String(20), default="incident")
    investigation_status: Mapped[str] = mapped_column(String(30), default="queued")
    current_stage_name: Mapped[str] = mapped_column(String(30), default="triage")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    stage_messages_json: Mapped[list[Any] | None] = mapped_column()
    investigation_window_start: Mapped[datetime | None] = mapped_column()
    investigation_window_end: Mapped[datetime | None] = mapped_column()
    baseline_window_start: Mapped[datetime | None] = mapped_column()
    baseline_window_end: Mapped[datetime | None] = mapped_column()
    investigated_service_ids_json: Mapped[list[str] | None] = mapped_column()
    triage_result_json: Mapped[dict[str, Any] | None] = mapped_column()
    executive_summary: Mapped[str | None] = mapped_column(Text)
    what_went_wrong_markdown: Mapped[str | None] = mapped_column(Text)
    why_it_happened_markdown: Mapped[str | None] = mapped_column(Text)
    how_to_fix_markdown: Mapped[str | None] = mapped_column(Text)
    open_questions_json: Mapped[list[str] | None] = mapped_column()
    overall_confidence_score: Mapped[float | None] = mapped_column(Float)
    leading_hypothesis_id: Mapped[str | None] = mapped_column(String(36))
    blast_radius_json: Mapped[dict[str, Any] | None] = mapped_column()
    matched_runbook_ids_json: Mapped[list[str] | None] = mapped_column()
    knowledge_references_json: Mapped[list[Any] | None] = mapped_column()
    user_feedback_verdict: Mapped[str | None] = mapped_column(String(20))
    user_feedback_comment: Mapped[str | None] = mapped_column(Text)
    user_feedback_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    total_input_token_count: Mapped[int] = mapped_column(Integer, default=0)
    total_output_token_count: Mapped[int] = mapped_column(Integer, default=0)
    model_names_json: Mapped[list[str] | None] = mapped_column()
    requested_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()


class InvestigationHypothesis(EntityBase):
    __tablename__ = "investigation_hypothesis"

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
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class InvestigationEvidence(EntityBase):
    __tablename__ = "investigation_evidence"
    __table_args__ = (UniqueConstraint("investigation_id", "evidence_code", name="uq_evidence_code_per_investigation"),)

    evidence_id: Mapped[str] = identifier_column()
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id", ondelete="CASCADE"), index=True)
    evidence_code: Mapped[str] = mapped_column(String(10))
    service_id: Mapped[str | None] = mapped_column(String(36))
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
    masked_value_count: Mapped[int] = mapped_column(Integer, default=0)
    possible_prompt_injection: Mapped[bool] = mapped_column(Boolean, default=False)
    deep_link_url: Mapped[str | None] = mapped_column(String(1000))
    collected_at: Mapped[datetime] = mapped_column(default=utc_now)


class InvestigationTimelineEvent(EntityBase):
    __tablename__ = "investigation_timeline_event"

    timeline_event_id: Mapped[str] = identifier_column()
    incident_id: Mapped[str | None] = mapped_column(String(36), index=True)
    investigation_id: Mapped[str | None] = mapped_column(String(36), index=True)
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

    communication_id: Mapped[str] = identifier_column()
    incident_id: Mapped[str | None] = mapped_column(String(36), index=True)
    investigation_id: Mapped[str | None] = mapped_column(String(36), index=True)
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

    postmortem_id: Mapped[str] = identifier_column()
    incident_id: Mapped[str] = mapped_column(String(36), index=True)
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    report_title: Mapped[str] = mapped_column(String(400))
    report_markdown: Mapped[str | None] = mapped_column(Text)
    report_sections_json: Mapped[dict[str, Any] | None] = mapped_column()
    language_code: Mapped[str] = mapped_column(String(10), default="en")
    report_status: Mapped[str] = mapped_column(String(20), default="generating")
    generation_trigger: Mapped[str] = mapped_column(String(30), default="user_button")
    finalized_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    finalized_at: Mapped[datetime | None] = mapped_column()
    sent_at: Mapped[datetime | None] = mapped_column()


class Conversation(AuditColumnsMixin, EntityBase):
    __tablename__ = "conversation"

    conversation_id: Mapped[str] = identifier_column()
    conversation_scope: Mapped[str] = mapped_column(String(30))
    application_ids_json: Mapped[list[str] | None] = mapped_column()
    investigation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), index=True)
    owner_user_principal_name: Mapped[str | None] = mapped_column(String(320), index=True)
    conversation_title: Mapped[str] = mapped_column(String(300), default="New conversation")


class ConversationMessage(EntityBase):
    __tablename__ = "conversation_message"

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


__all__ = [
    "Conversation",
    "ConversationMessage",
    "Incident",
    "IncidentCommunication",
    "Investigation",
    "InvestigationEvidence",
    "InvestigationHypothesis",
    "InvestigationTimelineEvent",
    "PostmortemReport",
    "ServiceNowAssignmentGroup",
]

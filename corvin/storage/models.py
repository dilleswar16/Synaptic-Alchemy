"""
SQLAlchemy ORM models for Corvin V1.

Tables:
  investigation_requests  — one row per InvestigationRequest
  rca_outputs             — one row per RCAOutput, FK to investigation_requests
  fix_strategy_outputs    — one row per FixStrategyOutput, FK to investigation_requests

JSON columns are used for list/dict fields so that the domain contract types
(which are defined in corvin.core.contracts) remain the single source of
truth and the ORM layer stays thin.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Use JSONB on Postgres, fall back to JSON on other dialects (e.g. SQLite in tests).
# This has no effect on production behaviour: Postgres always sees JSONB.
JSONB_COMPAT = JSONB().with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class InvestigationRequestRow(Base):
    __tablename__ = "investigation_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    lookback_minutes: Mapped[int] = mapped_column(nullable=False, default=60)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    rca: Mapped[RCAOutputRow | None] = relationship(
        "RCAOutputRow", back_populates="request", uselist=False
    )
    fix_strategy: Mapped[FixStrategyOutputRow | None] = relationship(
        "FixStrategyOutputRow", back_populates="request", uselist=False
    )
    evidence: Mapped[EvidenceBundleRow | None] = relationship(
        "EvidenceBundleRow", back_populates="request", uselist=False
    )
    post_mortem: Mapped[PostMortemRow | None] = relationship(
        "PostMortemRow", back_populates="request", uselist=False
    )
    chat_messages: Mapped[list[ChatMessageRow]] = relationship(
        "ChatMessageRow", back_populates="request", order_by="ChatMessageRow.created_at"
    )


class RCAOutputRow(Base):
    __tablename__ = "rca_outputs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigation_requests.id"), nullable=False, unique=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_factors: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    confidence_reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_references: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped[InvestigationRequestRow] = relationship(
        "InvestigationRequestRow", back_populates="rca"
    )


class FixStrategyOutputRow(Base):
    __tablename__ = "fix_strategy_outputs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigation_requests.id"), nullable=False, unique=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    actions: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped[InvestigationRequestRow] = relationship(
        "InvestigationRequestRow", back_populates="fix_strategy"
    )


class EvidenceBundleRow(Base):
    __tablename__ = "evidence_bundles"

    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigation_requests.id"), primary_key=True
    )
    elastic_logs: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    elastic_metrics: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    log_analytics_apim: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    aks_context: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    azure_activity_changes: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped[InvestigationRequestRow] = relationship(
        "InvestigationRequestRow", back_populates="evidence"
    )


class PostMortemRow(Base):
    __tablename__ = "post_mortems"

    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigation_requests.id"), primary_key=True
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    incident_summary: Mapped[str] = mapped_column(Text, nullable=False)
    detection_timeline: Mapped[str] = mapped_column(Text, nullable=False)
    investigation_findings: Mapped[str] = mapped_column(Text, nullable=False)
    actions_taken: Mapped[str] = mapped_column(Text, nullable=False)
    prevention_recommendations: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped[InvestigationRequestRow] = relationship(
        "InvestigationRequestRow", back_populates="post_mortem"
    )


class PredictiveAlertRow(Base):
    __tablename__ = "predictive_alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_value: Mapped[float] = mapped_column(nullable=False, default=0.0)
    threshold_value: Mapped[float] = mapped_column(nullable=False, default=0.0)
    estimated_breach_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    investigation_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ChatMessageRow(Base):
    """One chat turn (user or assistant) for an investigation's Copilot session."""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigation_requests.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)   # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped[InvestigationRequestRow] = relationship(
        "InvestigationRequestRow", back_populates="chat_messages"
    )


class CorvinSessionRow(Base):
    """A top-level Corvin Command Center conversation (ChatGPT-style session)."""
    __tablename__ = "corvin_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    messages: Mapped[list[CorvinMessageRow]] = relationship(
        "CorvinMessageRow", back_populates="session", order_by="CorvinMessageRow.created_at"
    )


class CorvinMessageRow(Base):
    """One chat turn in a Corvin Command Center session."""
    __tablename__ = "corvin_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("corvin_sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)   # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # The agent's internal reasoning/thought process (monospaced in UI)
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # Serialised list of tool calls made during this turn (JSON), null for user turns
    tool_calls: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    session: Mapped[CorvinSessionRow] = relationship(
        "CorvinSessionRow", back_populates="messages"
    )

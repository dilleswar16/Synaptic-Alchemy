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

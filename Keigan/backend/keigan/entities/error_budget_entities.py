"""Error budget policy: the team's agreement, what each incident cost, and the breaches of the agreement (spec 30)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column
from keigan.entities.status_values import ErrorBudgetBreachKind, ErrorBudgetRequirementStatus, IncidentBudgetImpactState, values_check

_SINGLE_INCIDENT_FILTER = text(f"breach_kind = '{ErrorBudgetBreachKind.SINGLE_INCIDENT.value}'")
_OPEN_OUTAGE_CLASS_FILTER = text(f"breach_kind = '{ErrorBudgetBreachKind.OUTAGE_CLASS.value}' AND requirement_status = '{ErrorBudgetRequirementStatus.OPEN.value}'")
_OPEN_EXHAUSTED_FILTER = text(f"breach_kind = '{ErrorBudgetBreachKind.BUDGET_EXHAUSTED.value}' AND requirement_status = '{ErrorBudgetRequirementStatus.OPEN.value}'")


class ErrorBudgetPolicy(AuditColumnsMixin, EntityBase):
    """One row per application, created on the first save only (a missing row means: off, with the default thresholds). A null threshold means the setting's default."""

    __tablename__ = "error_budget_policy"

    error_budget_policy_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), unique=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    single_incident_threshold_percent: Mapped[float | None] = mapped_column(Float)
    outage_class_threshold_percent: Mapped[float | None] = mapped_column(Float)
    outage_class_window_days: Mapped[int | None] = mapped_column(Integer)
    exhausted_budget_guidance_text: Mapped[str | None] = mapped_column(Text)  # the team's own words; never sent to a model


class IncidentBudgetImpact(EntityBase):
    """What one incident cost one SLO's error budget, with the inputs. Stored because the raw measurements expire."""

    __tablename__ = "incident_budget_impact"
    __table_args__ = (
        UniqueConstraint("incident_id", "slo_id", name="uq_incident_budget_impact_incident_id_slo_id"),
        Index("ix_incident_budget_impact_application_id_evaluated_at", "application_id", "evaluated_at"),
        values_check("impact_state", IncidentBudgetImpactState),
    )

    incident_budget_impact_id: Mapped[str] = identifier_column()
    incident_id: Mapped[str] = mapped_column(ForeignKey("incident.incident_id", ondelete="CASCADE"))
    application_id: Mapped[str] = mapped_column(String(36))  # a recorded fact, not a link: the incident row is the one cascade path
    slo_id: Mapped[str | None] = mapped_column(ForeignKey("service_level_objective.slo_id"))  # released to null when the SLO is deleted; the snapshot columns keep the meaning
    sli_name_text: Mapped[str] = mapped_column(String(200))
    target_percentage: Mapped[float] = mapped_column(Float)
    budget_window_days: Mapped[int] = mapped_column(Integer)
    impact_window_start: Mapped[datetime] = mapped_column()
    impact_window_end: Mapped[datetime] = mapped_column()
    budget_window_start: Mapped[datetime] = mapped_column()
    budget_window_end: Mapped[datetime] = mapped_column()
    bad_event_count: Mapped[int] = mapped_column(BigInteger)
    impact_total_event_count: Mapped[int] = mapped_column(BigInteger)
    window_total_event_count: Mapped[int] = mapped_column(BigInteger)
    data_coverage_percent: Mapped[float] = mapped_column(Float)
    budget_event_count: Mapped[float | None] = mapped_column(Float)
    budget_share_percent: Mapped[float | None] = mapped_column(Float)
    is_service_matched: Mapped[bool] = mapped_column(Boolean)  # false: matched as an application-wide SLI, or because the incident names no service
    impact_state: Mapped[str] = mapped_column(String(20))
    evaluated_at: Mapped[datetime] = mapped_column()


class ErrorBudgetPolicyBreach(AuditColumnsMixin, EntityBase):
    """A recorded fact that a policy threshold was crossed, and whether the requirement that follows has been met, waived or has ended."""

    __tablename__ = "error_budget_policy_breach"
    __table_args__ = (
        Index("uq_error_budget_policy_breach_single_incident", "incident_id", unique=True, mssql_where=_SINGLE_INCIDENT_FILTER, postgresql_where=_SINGLE_INCIDENT_FILTER, sqlite_where=_SINGLE_INCIDENT_FILTER),
        Index(
            "uq_error_budget_policy_breach_open_outage_class", "application_id", "recurrence_category", "recurrence_service_id", unique=True,
            mssql_where=_OPEN_OUTAGE_CLASS_FILTER, postgresql_where=_OPEN_OUTAGE_CLASS_FILTER, sqlite_where=_OPEN_OUTAGE_CLASS_FILTER,
        ),
        Index("uq_error_budget_policy_breach_open_exhausted", "slo_id", unique=True, mssql_where=_OPEN_EXHAUSTED_FILTER, postgresql_where=_OPEN_EXHAUSTED_FILTER, sqlite_where=_OPEN_EXHAUSTED_FILTER),
        values_check("breach_kind", ErrorBudgetBreachKind),
        values_check("requirement_status", ErrorBudgetRequirementStatus),
    )

    error_budget_policy_breach_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    breach_kind: Mapped[str] = mapped_column(String(30))
    # NO ACTION on the next four: the application is the one cascade path; incident expiry, SLO deletion and action item deletion release them first.
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    incident_reference_text: Mapped[str | None] = mapped_column(String(60))
    slo_id: Mapped[str | None] = mapped_column(ForeignKey("service_level_objective.slo_id"))
    sli_name_text: Mapped[str | None] = mapped_column(String(200))
    recurrence_category: Mapped[str | None] = mapped_column(String(40))
    recurrence_service_id: Mapped[str | None] = mapped_column(String(36))  # a recorded fact, not a link
    recurrence_service_name_text: Mapped[str | None] = mapped_column(String(200))
    measured_share_percent: Mapped[float | None] = mapped_column(Float)
    threshold_percent: Mapped[float | None] = mapped_column(Float)
    window_days: Mapped[int] = mapped_column(Integer)
    detected_at: Mapped[datetime] = mapped_column()
    requirement_status: Mapped[str] = mapped_column(String(20), default=ErrorBudgetRequirementStatus.OPEN)
    requirement_changed_at: Mapped[datetime] = mapped_column()
    qualifying_action_item_id: Mapped[str | None] = mapped_column(ForeignKey("action_item.action_item_id"))
    waived_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    waiver_reason_text: Mapped[str | None] = mapped_column(String(1000))
    notified_at: Mapped[datetime | None] = mapped_column()
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=False)

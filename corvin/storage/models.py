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
    incident_priority: Mapped[str] = mapped_column(String(10), nullable=False, default="P3")
    lookback_minutes: Mapped[int] = mapped_column(nullable=False, default=60)
    ado_work_item_id: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    wiki_url: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)
    sharepoint_url: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)
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
    container_resource_metrics: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    container_inventory: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    node_inventory: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    network_metrics: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    pod_restarts: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    oom_kill_events: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    autoscaler_events: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
    health_probe_failures: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list, server_default="[]")
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
    confidence_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    related_count: Mapped[int] = mapped_column(nullable=False, default=1)
    blast_radius_users: Mapped[int] = mapped_column(nullable=False, default=0)
    blast_radius_requests: Mapped[int] = mapped_column(nullable=False, default=0)
    change_correlation: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    suppression_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)  # suppressed | None
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
    # Serialised tool results keyed by tool_name — allows UI to re-render charts after reload
    tool_results: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    session: Mapped[CorvinSessionRow] = relationship(
        "CorvinSessionRow", back_populates="messages"
    )


# ── Application Panel models ──────────────────────────────────────────────────


class ApplicationRow(Base):
    """A registered application — top-level container for services, connectors, and SLO configs."""
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    environment_default: Mapped[str] = mapped_column(String(50), nullable=False, default="dev")
    topology_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    # ── Git repository config (for code-aware investigation) ──────────────────
    git_provider: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)   # azure_devops | github
    git_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)  # e.g. https://dev.azure.com/org/project/_git/repo
    git_branch: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)    # default branch to read from
    git_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)  # AES-256-GCM encrypted PAT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    services: Mapped[list["ApplicationServiceRow"]] = relationship(
        "ApplicationServiceRow", back_populates="application", cascade="all, delete-orphan"
    )
    log_sources: Mapped[list["LogSourceRow"]] = relationship(
        "LogSourceRow", back_populates="application", cascade="all, delete-orphan"
    )
    slo_configs: Mapped[list["SloConfigRow"]] = relationship(
        "SloConfigRow", back_populates="application", cascade="all, delete-orphan"
    )
    notification_contacts: Mapped[list["NotificationContactRow"]] = relationship(
        "NotificationContactRow", back_populates="application", cascade="all, delete-orphan"
    )
    outbound_connectors: Mapped[list["OutboundConnectorRow"]] = relationship(
        "OutboundConnectorRow", back_populates="application", cascade="all, delete-orphan"
    )
    validations: Mapped[list["ValidationDefinitionRow"]] = relationship(
        "ValidationDefinitionRow", back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationServiceRow(Base):
    """A named service/component within an application."""
    __tablename__ = "application_services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False, index=True
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    tier: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)  # frontend|api|db|queue|worker
    dependencies: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    # Kubernetes deployment label (e.g. "chad-fundapis") — may differ from service_name.
    # Used by the topology/live endpoint to map AKS pod labels to logical service names.
    k8s_app_label: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    # ── Git repository config (per-service, for code-aware investigation) ─────
    git_provider: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)   # azure_devops | github
    git_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    git_branch: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    git_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    application: Mapped["ApplicationRow"] = relationship("ApplicationRow", back_populates="services")


class LogSourceRow(Base):
    """A configured log/metrics data source (connector) for an application."""
    __tablename__ = "log_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # azure_monitor|elastic|byoa
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    credential_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="env_var"
    )  # db_encrypted|kv_reference|env_var
    credential_ref: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # encrypted blob | KV vault_url|secret_name | env var name
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    test_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)  # ok|error|unknown
    test_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    application: Mapped["ApplicationRow"] = relationship("ApplicationRow", back_populates="log_sources")


class SloConfigRow(Base):
    """SLO / SLI configuration for a specific service within an application."""
    __tablename__ = "slo_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False, index=True
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sli_type: Mapped[str] = mapped_column(String(30), nullable=False, default="availability")  # availability|latency
    target_pct: Mapped[float] = mapped_column(nullable=False, default=99.9)
    time_window_days: Mapped[int] = mapped_column(nullable=False, default=30)
    latency_threshold_ms: Mapped[int | None] = mapped_column(nullable=True, default=None)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    application: Mapped["ApplicationRow"] = relationship("ApplicationRow", back_populates="slo_configs")
    snapshots: Mapped[list["SloSnapshotRow"]] = relationship(
        "SloSnapshotRow", back_populates="slo_config", cascade="all, delete-orphan",
        order_by="SloSnapshotRow.sampled_at",
    )


# ── Notification Contacts ─────────────────────────────────────────────────────


class NotificationContactRow(Base):
    """A person/channel to alert when incidents occur for an application."""
    __tablename__ = "notification_contacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False, index=True
    )
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)  # email|phone|teams
    value: Mapped[str] = mapped_column(String(500), nullable=False)  # email addr, phone #, channel webhook
    priority_filter: Mapped[str] = mapped_column(String(20), nullable=False, default="all")  # all|p1_only|p1_p2
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    application: Mapped["ApplicationRow"] = relationship("ApplicationRow", back_populates="notification_contacts")


# ── Outbound Connectors ───────────────────────────────────────────────────────


class OutboundConnectorRow(Base):
    """An outbound notification/integration destination for an application."""
    __tablename__ = "outbound_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)  # teams_webhook|servicenow|email|pagerduty
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    test_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    test_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    application: Mapped["ApplicationRow"] = relationship("ApplicationRow", back_populates="outbound_connectors")


# ── SLO Monitoring models ─────────────────────────────────────────────────────


class SloSnapshotRow(Base):
    """One health measurement for an SLO config at a point in time."""
    __tablename__ = "slo_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slo_config_id: Mapped[int] = mapped_column(
        ForeignKey("slo_configs.id"), nullable=False, index=True
    )
    application_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sli_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_pct: Mapped[float] = mapped_column(nullable=False)
    measured_pct: Mapped[float | None] = mapped_column(nullable=True)
    error_budget_pct: Mapped[float | None] = mapped_column(nullable=True)
    burn_rate: Mapped[float | None] = mapped_column(nullable=True)
    is_compliant: Mapped[bool | None] = mapped_column(nullable=True)
    data_source: Mapped[str] = mapped_column(String(30), nullable=False, default="simulated")
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    raw_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)

    slo_config: Mapped["SloConfigRow"] = relationship("SloConfigRow", back_populates="snapshots")


# ── Predictive Penalty / Learning models ──────────────────────────────────────


class PredictivePenaltyRow(Base):
    """Records a miss or insufficient prediction — drives the learning feedback loop."""
    __tablename__ = "predictive_penalties"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False, default="production")
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    penalty_type: Mapped[str] = mapped_column(String(30), nullable=False)  # missed|insufficient
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    predictive_alert_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pattern_description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_threshold_adjustment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


# ── Validations models ────────────────────────────────────────────────────────


class ValidationDefinitionRow(Base):
    """A named, runnable validation check."""
    __tablename__ = "validation_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    validation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="health_check"
    )  # health_check|endpoint|synthetic|slo_gate|chaos
    config_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    last_run_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    application: Mapped["ApplicationRow | None"] = relationship(
        "ApplicationRow", back_populates="validations"
    )
    runs: Mapped[list["ValidationRunRow"]] = relationship(
        "ValidationRunRow", back_populates="definition", cascade="all, delete-orphan",
        order_by="ValidationRunRow.started_at",
    )


class ValidationRunRow(Base):
    """One execution of a ValidationDefinitionRow."""
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("validation_definitions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True, default=None)
    result_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    triggered_by: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    definition: Mapped["ValidationDefinitionRow"] = relationship(
        "ValidationDefinitionRow", back_populates="runs"
    )


# ── Validation Automation Policies ────────────────────────────────────────────


class ApprovalDecisionRow(Base):
    """Persists operator approval/rejection decisions (correlation suppression, scaling, etc.)."""
    __tablename__ = "approval_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)  # correlation_suppression | scaling_action
    reference_id: Mapped[str] = mapped_column(String(255), nullable=False)  # group_id or service_name
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approve | reject
    action_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RunbookSessionRow(Base):
    """Persists conversational runbook builder sessions across restarts."""
    __tablename__ = "runbook_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="drafting")
    messages_json: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False, default=list)
    current_draft_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_draft_version: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ValidationAutomationPolicyRow(Base):
    """Links a predictive alert pattern to a validation definition for auto-trigger."""
    __tablename__ = "validation_automation_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    min_confidence_pct: Mapped[float] = mapped_column(nullable=False, default=70.0)
    validation_definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("validation_definitions.id"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    validation_definition: Mapped["ValidationDefinitionRow"] = relationship(
        "ValidationDefinitionRow"
    )

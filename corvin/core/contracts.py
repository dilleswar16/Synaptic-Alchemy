"""
Shared investigation contracts for Corvin V1.

These Pydantic models are the single source of truth for data shapes
passed between trigger adapters, enrichment, investigation engine,
RCA/fix strategy generators, persistence, and all delivery surfaces.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Trigger sources ──────────────────────────────────────────────────────────


class TriggerSource(str, Enum):
    """All supported investigation trigger origins."""

    AZURE_ALERT = "azure_alert"
    MANUAL_API = "manual_api"
    MANUAL_CLI = "manual_cli"
    TEAMS = "teams"
    MANUAL_WEB = "manual_web"


class ApprovalStatus(str, Enum):
    """Lifecycle states for human-in-the-loop investigation approval."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


# ── Inbound request ──────────────────────────────────────────────────────────


class InvestigationRequest(BaseModel):
    """Normalized inbound investigation request produced by any trigger adapter."""

    id: str = Field(default_factory=_new_id)
    trigger_source: TriggerSource
    service_name: str
    environment: str
    description: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    lookback_minutes: int = Field(default=60)
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _set_dynamic_lookback(self) -> InvestigationRequest:
        if self.trigger_source == TriggerSource.AZURE_ALERT:
            self.lookback_minutes = 15
        elif self.trigger_source in (
            TriggerSource.MANUAL_CLI,
            TriggerSource.MANUAL_API,
            TriggerSource.TEAMS,
            TriggerSource.MANUAL_WEB,
        ):
            self.lookback_minutes = 60
        return self


# ── Evidence bundle ──────────────────────────────────────────────────────────


class EvidenceBundle(BaseModel):
    """Collected evidence from all configured adapters for one investigation."""

    request_id: str
    elastic_logs: list[dict[str, Any]] = Field(default_factory=list)
    elastic_metrics: list[dict[str, Any]] = Field(default_factory=list)
    log_analytics_apim: list[dict[str, Any]] = Field(default_factory=list)
    aks_context: dict[str, Any] = Field(default_factory=dict)
    azure_activity_changes: list[dict[str, Any]] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=_utcnow)


# ── RCA ──────────────────────────────────────────────────────────────────────


class RCAConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RCAOutput(BaseModel):
    """Structured root-cause analysis produced by the investigation engine."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    summary: str
    root_cause: str
    contributing_factors: list[str] = Field(default_factory=list)
    confidence: RCAConfidence = RCAConfidence.MEDIUM
    confidence_reasoning: str = Field(default="", description="Why this confidence level was assigned.")
    evidence_references: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)


# ── Fix strategy ─────────────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionType(str, Enum):
    """The concrete execution type for a FixAction.

    Used by ExecutionService to dispatch to the correct AKS / Azure call.
    """

    RESTART_POD = "restart_pod"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    SCALE_DEPLOYMENT = "scale_deployment"
    MANUAL = "manual"  # Human-only action — ExecutionService skips it


class FixAction(BaseModel):
    """A single recommended remediation action."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    action_type: ActionType = ActionType.MANUAL
    risk_level: RiskLevel
    estimated_impact: str
    requires_approval: bool = True


class FixStrategyOutput(BaseModel):
    """Structured fix strategy associated with a completed RCA."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    summary: str
    actions: list[FixAction] = Field(default_factory=list)
    justification: str
    generated_at: datetime = Field(default_factory=_utcnow)


# ── Combined result ──────────────────────────────────────────────────────────


class InvestigationResult(BaseModel):
    """Complete investigation result: request + evidence + RCA + fix strategy.

    confidence_warning is set to True by FixStrategyGenerator when the RCA
    confidence is below the configured ``min_confidence_to_suggest_action``
    threshold.  The API surfaces this flag so the UI can display a warning
    banner like: 'Low confidence RCA — manual review strongly recommended.'
    """

    request_id: str
    request: InvestigationRequest
    evidence: EvidenceBundle
    rca: RCAOutput
    fix_strategy: FixStrategyOutput
    completed_at: datetime = Field(default_factory=_utcnow)
    confidence_warning: bool = False


# ── Post-Mortem ───────────────────────────────────────────────────────────────


class PostMortemOutput(BaseModel):
    """Blameless post-mortem auto-generated from a completed investigation.

    ``markdown`` is the full formatted document ready for download/render.
    The structured fields are provided so the UI can render sections
    individually without re-parsing Markdown.
    """

    request_id: str
    service_name: str
    environment: str
    generated_at: datetime = Field(default_factory=_utcnow)

    # Structured sections (mirrors the Markdown document structure)
    incident_summary: str
    detection_timeline: str          # ISO timestamps + narrative
    investigation_findings: str      # RCA root cause + contributing factors
    actions_taken: str               # Fix actions that were executed
    prevention_recommendations: str  # LLM-generated future prevention steps
    approved_by: str | None = None

    # Full Markdown document — generated by PostMortemService
    markdown: str

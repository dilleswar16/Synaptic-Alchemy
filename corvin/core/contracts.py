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
    PREDICTIVE = "predictive"
    MANUAL_API = "manual_api"
    MANUAL_CLI = "manual_cli"
    TEAMS = "teams"
    MANUAL_WEB = "manual_web"


class ApprovalStatus(str, Enum):
    """Lifecycle states for human-in-the-loop investigation approval."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACKNOWLEDGED = "acknowledged"
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
    incident_priority: str = Field(default="P3")
    lookback_minutes: int = Field(default=60)
    created_at: datetime = Field(default_factory=_utcnow)

    @staticmethod
    def _priority_from_payload(payload: dict[str, Any]) -> str | None:
        """Extract optional priority hints from heterogeneous trigger payloads."""
        direct = str(payload.get("incident_priority") or payload.get("priority") or "").upper().strip()
        if direct in {"P1", "P2", "P3"}:
            return direct

        severity_raw = payload.get("severity")
        if severity_raw is None and isinstance(payload.get("essentials"), dict):
            severity_raw = payload["essentials"].get("severity")
        severity = str(severity_raw or "").lower().strip()
        if severity in {"sev0", "sev1", "critical", "high"}:
            return "P1"
        if severity in {"sev2", "medium", "warning"}:
            return "P2"
        if severity in {"sev3", "sev4", "low", "info", "informational"}:
            return "P3"
        return None

    @model_validator(mode="after")
    def _apply_payload_priority(self) -> InvestigationRequest:
        """Apply only payload-derived priority at construction time.

        Full priority classification (DB + config lookup) is performed by
        corvin.core.priority.classify_priority() after the request is created.
        Trigger adapters and API routes call classify_priority() and write the
        result back to incident_priority and lookback_minutes.
        """
        payload_priority = self._priority_from_payload(self.raw_payload)
        if payload_priority is not None:
            self.incident_priority = payload_priority
        return self


# ── Evidence bundle ──────────────────────────────────────────────────────────


class EvidenceBundle(BaseModel):
    """Collected evidence from all configured adapters for one investigation."""

    request_id: str
    elastic_logs: list[dict[str, Any]] = Field(default_factory=list)
    elastic_metrics: list[dict[str, Any]] = Field(default_factory=list)
    log_analytics_apim: list[dict[str, Any]] = Field(default_factory=list)
    aks_context: dict[str, Any] = Field(default_factory=dict)
    azure_activity_changes: list[dict[str, Any]] = Field(default_factory=list)  # deprecated, kept for DB compat
    container_resource_metrics: list[dict[str, Any]] = Field(default_factory=list)
    container_inventory: list[dict[str, Any]] = Field(default_factory=list)
    node_inventory: list[dict[str, Any]] = Field(default_factory=list)
    network_metrics: list[dict[str, Any]] = Field(default_factory=list)
    pod_restarts: list[dict[str, Any]] = Field(default_factory=list)
    oom_kill_events: list[dict[str, Any]] = Field(default_factory=list)
    autoscaler_events: list[dict[str, Any]] = Field(default_factory=list)
    health_probe_failures: list[dict[str, Any]] = Field(default_factory=list)
    code_context: list[dict[str, Any]] = Field(default_factory=list)
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


# ── Feature 8 — Debate Mode Hypothesis ────────────────────────────────────────


class RCAHypothesis(BaseModel):
    """One competing root-cause hypothesis generated during Debate Mode.

    The LLM produces exactly N of these (default 3) from the evidence bundle.
    The SRE selects the winner via POST /investigations/{id}/select-hypothesis.
    Winner’s root_cause is then used to re-run fix strategy generation.
    """

    id: str = Field(..., description="\"h1\" | \"h2\" | \"h3\" (positional index)")
    title: str = Field(..., description="Short label, e.g. \"Memory Leak in Worker Pool\"")
    root_cause: str = Field(..., description="Full explanation of this hypothesis.")
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence keys that support this hypothesis.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="LLM-assigned confidence score 0.0–1.0.",
    )
    evidence_strength_pct: int = Field(
        ...,
        ge=0,
        le=100,
        description="Evidence strength 0–100 for UI progress bar.",
    )
    supporting_signals: list[str] = Field(
        default_factory=list,
        description="Bullet list of key signals that support this hypothesis.",
    )
    refuting_signals: list[str] = Field(
        default_factory=list,
        description="Signals that argue against this hypothesis.",
    )
    supporting_evidence: list[dict[str, str]] = Field(
        default_factory=list,
        description="Traceable evidence refs for supporting signals. Each item: source_id + summary.",
    )
    refuting_evidence: list[dict[str, str]] = Field(
        default_factory=list,
        description="Traceable evidence refs for refuting signals. Each item: source_id + summary.",
    )


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
    target_service: str | None = None
    target_namespace: str | None = None
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
    github_issue_url: str | None = None
    github_issue_number: int | None = None


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
    ado_work_item_id: str | None = None
    ado_url: str | None = None
    wiki_url: str | None = None
    sharepoint_url: str | None = None
    # Feature 8 — Debate Mode
    # None when investigation was completed before Feature 8, or when debate_mode.enabled=false.
    hypotheses: list[RCAHypothesis] | None = None
    selected_hypothesis_id: str | None = None


# ── Post-Mortem ──────────────────────────────────────────────────────────────


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

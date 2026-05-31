"""
Advanced AI features API routes — V6

Covers:
  - Alert Correlation & Deduplication (/alerts/correlated)
  - AI Capacity Forecaster (/capacity-forecast)
  - Conversational Runbook Builder (/runbooks)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from corvin.core.config_loader import get_env, load_config
from corvin.core.knowledge_loader import KnowledgeLoader
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.alert_correlation import AlertCorrelationEngine, CorrelationGroup
from corvin.strategy.capacity_forecaster import CapacityForecaster, CapacityForecastReport
from corvin.strategy.runbook_builder import RunbookBuilder

router = APIRouter()
_log = logging.getLogger(__name__)

# ── Shared instances (stateful for sessions) ──────────────────────────────────
_runbook_builder = RunbookBuilder()


def get_repository() -> InvestigationRepository:
    return InvestigationRepository()


# ══════════════════════════════════════════════════════════════════════════════
# Alert Correlation & Deduplication
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/alerts/correlated")
def get_correlated_alerts(
    environment: Optional[str] = Query(None),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """
    Fetch all open predictive alerts, run correlation engine,
    and return grouped alerts with suppression recommendations.
    """
    from corvin.storage.models import PredictiveAlertRow
    from corvin.storage.database import get_session

    with get_session() as session:
        query = session.query(PredictiveAlertRow).filter(
            PredictiveAlertRow.status == "open"
        )
        if environment:
            query = query.filter(PredictiveAlertRow.environment == environment)

        rows = query.order_by(PredictiveAlertRow.created_at.desc()).limit(200).all()

    alerts = [
        {
            "id": r.id,
            "service_name": r.service_name,
            "environment": r.environment,
            "title": r.title,
            "severity": r.severity,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "alert_type": r.alert_type,
            "confidence_pct": r.confidence_pct,
        }
        for r in rows
    ]

    engine = AlertCorrelationEngine()
    groups = engine.correlate(alerts)

    return {
        "total_alerts": len(alerts),
        "correlation_groups": [g.to_dict() for g in groups],
        "ungrouped_count": len(alerts) - sum(len(g.alerts) for g in groups),
        "suppression_candidates": sum(1 for g in groups if g.suppression_recommended),
    }


class CorrelationApprovalRequest(BaseModel):
    group_id: str
    action: str = Field(..., pattern="^(approve|reject)$")
    approved_by: str = "operator"


@router.post("/alerts/correlated/approve")
def approve_correlation_action(body: CorrelationApprovalRequest = Body(...)) -> dict:
    """Approve or reject a correlation group's suppression recommendation."""
    from corvin.storage.database import get_session
    from corvin.storage.models import ApprovalDecisionRow, PredictiveAlertRow

    with get_session() as session:
        # Persist the decision
        decision = ApprovalDecisionRow(
            decision_type="correlation_suppression",
            reference_id=body.group_id,
            action=body.action,
            approved_by=body.approved_by,
            metadata_json={"group_id": body.group_id},
        )
        session.add(decision)

        # If approved, suppress correlated alerts matching this group
        if body.action == "approve":
            # Find alerts that belong to this correlation group (stored in metadata)
            alerts = session.query(PredictiveAlertRow).filter(
                PredictiveAlertRow.status == "open"
            ).all()
            suppressed_count = 0
            for alert in alerts:
                # Group ID is typically service+type hash — suppress matching open alerts
                if alert.id.startswith(body.group_id[:8]):
                    alert.suppression_status = "suppressed"
                    alert.status = "suppressed"
                    suppressed_count += 1

        session.commit()

    return {
        "group_id": body.group_id,
        "action": body.action,
        "status": "approved" if body.action == "approve" else "rejected",
        "approved_by": body.approved_by,
        "persisted": True,
        "message": f"Correlation group {body.group_id} {body.action}d by {body.approved_by}.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# AI Capacity Forecaster
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/capacity-forecast/{service_name}")
async def get_capacity_forecast(
    service_name: str,
    environment: str = Query("prod"),
    namespace: str = Query("default"),
) -> dict:
    """
    Generate a capacity forecast for a given service based on stored metrics.
    Analyzes container_resource_metrics from the most recent evidence bundle.
    """
    from corvin.storage.models import EvidenceBundleRow, InvestigationRequestRow
    from corvin.storage.database import get_session
    import json

    # Pull recent evidence metrics for this service
    metrics: list[dict] = []
    current_replicas = 1

    with get_session() as session:
        bundles = (
            session.query(EvidenceBundleRow)
            .join(InvestigationRequestRow)
            .filter(InvestigationRequestRow.service_name == service_name)
            .filter(InvestigationRequestRow.environment == environment)
            .order_by(InvestigationRequestRow.created_at.desc())
            .limit(5)
            .all()
        )

        for bundle in bundles:
            if bundle.container_resource_metrics:
                raw = bundle.container_resource_metrics
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if isinstance(raw, list):
                    metrics.extend(raw)
                elif isinstance(raw, dict):
                    metrics.append(raw)

    forecaster = CapacityForecaster()
    report = forecaster.forecast(
        service_name=service_name,
        environment=environment,
        namespace=namespace,
        metrics=metrics,
        current_replicas=current_replicas,
    )

    # Generate AI narrative if we have forecasts
    if report.forecasts:
        report.ai_narrative = await forecaster.generate_narrative(report)

    return report.to_dict()


class ScalingApprovalRequest(BaseModel):
    service_name: str
    action_type: str
    approved_by: str = "operator"


@router.post("/capacity-forecast/approve-scaling")
def approve_scaling_action(body: ScalingApprovalRequest = Body(...)) -> dict:
    """Approve a scaling recommendation. Persists decision for audit trail. Does NOT auto-execute."""
    from corvin.storage.database import get_session
    from corvin.storage.models import ApprovalDecisionRow

    with get_session() as session:
        decision = ApprovalDecisionRow(
            decision_type="scaling_action",
            reference_id=body.service_name,
            action="approve",
            action_detail=body.action_type,
            approved_by=body.approved_by,
            metadata_json={"service_name": body.service_name, "action_type": body.action_type},
        )
        session.add(decision)
        session.commit()

    return {
        "service_name": body.service_name,
        "action_type": body.action_type,
        "status": "approved",
        "approved_by": body.approved_by,
        "persisted": True,
        "message": f"Scaling action '{body.action_type}' for {body.service_name} approved by {body.approved_by}. Execute via kubectl/HPA.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Conversational Runbook Builder
# ══════════════════════════════════════════════════════════════════════════════


class RunbookSessionStartRequest(BaseModel):
    request_id: str
    service_name: str
    environment: str = "prod"


@router.post("/runbooks/start-session")
async def start_runbook_session(body: RunbookSessionStartRequest = Body(...)) -> dict:
    """Start a new conversational runbook building session."""
    # Gather investigation context
    repo = get_repository()
    result = repo.get_investigation_result(body.request_id)

    context_parts = []
    if result:
        if result.rca:
            context_parts.append(f"Root Cause: {result.rca.root_cause}")
            context_parts.append(f"Contributing Factors: {', '.join(result.rca.contributing_factors or [])}")
        if result.fix_strategy:
            context_parts.append(f"Fix Summary: {result.fix_strategy.summary}")
            for action in (result.fix_strategy.actions or []):
                context_parts.append(f"  - Action: {action.title}")
    else:
        context_parts.append("No investigation result available. Building runbook from scratch.")

    investigation_context = "\n".join(context_parts)

    session = _runbook_builder.start_session(
        request_id=body.request_id,
        service_name=body.service_name,
        environment=body.environment,
        investigation_context=investigation_context,
    )

    # Generate initial draft
    initial = await _runbook_builder.generate_initial_draft(session.session_id)

    return {
        "session_id": session.session_id,
        "status": "drafting",
        "initial_response": initial.get("response", ""),
        "draft": initial.get("draft"),
    }


class RunbookChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("/runbooks/chat")
async def runbook_chat(body: RunbookChatRequest = Body(...)) -> dict:
    """Send a message in an active runbook building session."""
    session = _runbook_builder.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Runbook session '{body.session_id}' not found.")

    result = await _runbook_builder.chat(body.session_id, body.message)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


class RunbookApproveRequest(BaseModel):
    session_id: str
    approved_by: str = "operator"


@router.post("/runbooks/approve")
def approve_runbook_draft(body: RunbookApproveRequest = Body(...)) -> dict:
    """Approve the current runbook draft for saving."""
    session = _runbook_builder.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Runbook session '{body.session_id}' not found.")

    result = _runbook_builder.approve_draft(body.session_id, body.approved_by)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


class RunbookSaveRequest(BaseModel):
    session_id: str


@router.post("/runbooks/save")
def save_runbook(body: RunbookSaveRequest = Body(...)) -> dict:
    """Save the approved runbook to the knowledge base. Requires prior approval."""
    session = _runbook_builder.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Runbook session '{body.session_id}' not found.")

    if session.status != "approved":
        raise HTTPException(status_code=400, detail="Draft must be approved before saving. Call /runbooks/approve first.")

    content = _runbook_builder.get_final_content(body.session_id)
    if not content:
        raise HTTPException(status_code=400, detail="No approved content to save.")

    # Persist to knowledge base
    loader = KnowledgeLoader()
    runbook_path = loader.append_runbook_step(session.service_name, content)

    return {
        "session_id": body.session_id,
        "service_name": session.service_name,
        "status": "saved",
        "path": str(runbook_path),
        "content": content,
        "message": f"Runbook saved for {session.service_name}.",
    }

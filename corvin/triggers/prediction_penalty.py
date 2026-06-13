"""Predictive Analysis penalty/learning system.

When an incident occurs:
  - If a predictive alert existed for the same service → "insufficient" penalty
    (prediction fired but the issue still occurred)
  - If no predictive alert existed → "missed" penalty
    (the system failed to predict the failure)

The penalty generates a structured learning record that is injected into
future prediction checks and investigation prompts so the same miss is
not repeated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult
from corvin.core.knowledge_loader import KnowledgeLoader
from corvin.storage.db import get_session
from corvin.storage.models import PredictiveAlertRow, PredictivePenaltyRow

_log = logging.getLogger(__name__)

# Window to look back for matching predictive alerts (hours before incident)
_ALERT_LOOKBACK_HOURS = 24


def _find_related_alert(
    service_name: str,
    environment: str,
    incident_time: datetime,
) -> dict[str, Any] | None:
    """Find the most recent predictive alert for this service within the lookback window."""
    cutoff = incident_time - timedelta(hours=_ALERT_LOOKBACK_HOURS)

    with get_session() as session:
        row = session.execute(
            select(PredictiveAlertRow)
            .where(
                PredictiveAlertRow.service_name == service_name,
                PredictiveAlertRow.environment == environment,
                PredictiveAlertRow.created_at >= cutoff,
            )
            .order_by(PredictiveAlertRow.created_at.desc())
            .limit(1)
        ).scalars().first()

        if row is None:
            return None

        return {
            "id": row.id,
            "alert_type": row.alert_type,
            "severity": row.severity,
            "confidence_pct": row.confidence_pct,
            "signal_value": row.signal_value,
            "threshold_value": row.threshold_value,
            "title": row.title,
            "summary": row.summary,
        }


def _generate_pattern_fingerprint(result: InvestigationResult, penalty_type: str, related_alert: dict | None) -> str:
    """Generate a structured pattern description from the incident for future reference.

    This is a deterministic prompt-engineering approach — no LLM call needed here.
    The output is injected into future LLM investigation prompts.
    """
    root_cause = result.rca.root_cause or "Unknown"
    contributing = ", ".join(result.rca.contributing_factors[:3]) if result.rca.contributing_factors else "None identified"
    service = result.request.service_name

    if penalty_type == "missed":
        fingerprint = (
            f"MISSED PATTERN for {service}: The predictive engine failed to detect this failure mode.\n"
            f"Root Cause: {root_cause}\n"
            f"Contributing Factors: {contributing}\n"
            f"What to watch for: Monitor for the combination of these signals before similar incidents. "
            f"Consider adding a heuristic check for this pattern."
        )
    else:
        # insufficient — prediction fired but didn't prevent the incident
        alert_info = related_alert or {}
        fingerprint = (
            f"INSUFFICIENT PREDICTION for {service}: Alert '{alert_info.get('title', 'unknown')}' fired "
            f"(confidence {alert_info.get('confidence_pct', 0):.0f}%, type={alert_info.get('alert_type', 'unknown')}) "
            f"but the incident still occurred.\n"
            f"Root Cause: {root_cause}\n"
            f"Contributing Factors: {contributing}\n"
            f"Gap: The prediction identified the right area but the threshold/timing was not aggressive enough. "
            f"Lower the threshold or increase alert severity for this pattern."
        )

    return fingerprint


def _suggest_threshold_adjustment(penalty_type: str, related_alert: dict | None) -> str | None:
    """Suggest concrete threshold adjustment based on the miss."""
    if penalty_type == "missed":
        return "Add new heuristic rule for this failure mode or lower existing thresholds by 15-20%."

    if related_alert:
        signal = related_alert.get("signal_value", 0)
        threshold = related_alert.get("threshold_value", 100)
        if threshold > 0:
            # Suggest lowering threshold to 80% of current value
            suggested = round(threshold * 0.8, 1)
            return (
                f"Lower {related_alert.get('alert_type', 'unknown')} threshold from "
                f"{threshold} to {suggested} (signal was {signal} when alert fired but incident still occurred)."
            )

    return None


def is_penalty_feature_enabled() -> bool:
    """Read the prediction_penalty_enabled policy flag (default: disabled)."""
    try:
        from corvin.core.config_loader import get_env, load_config
        policy = load_config("policies/investigation", get_env())
        return bool(policy.get("prediction_penalty_enabled", False))
    except Exception:  # noqa: BLE001
        return False


def penalize_prediction(result: InvestigationResult) -> PredictivePenaltyRow | None:
    """Evaluate an investigation result and create a penalty record if warranted.

    Called after every investigation completes. Returns the penalty row if
    created, or None when the feature is disabled via the
    ``prediction_penalty_enabled`` policy flag.
    """
    if not is_penalty_feature_enabled():
        return None

    service_name = result.request.service_name
    environment = result.request.environment
    incident_time = result.completed_at or datetime.now(timezone.utc)

    # Find related predictive alert
    related_alert = _find_related_alert(service_name, environment, incident_time)

    if related_alert:
        penalty_type = "insufficient"
        alert_type = related_alert["alert_type"]
        predictive_alert_id = related_alert["id"]
    else:
        penalty_type = "missed"
        # Infer alert_type from the incident characteristics
        root_cause_lower = (result.rca.root_cause or "").lower()
        if any(w in root_cause_lower for w in ("memory", "oom", "heap")):
            alert_type = "memory_pressure"
        elif any(w in root_cause_lower for w in ("error", "5xx", "exception", "timeout")):
            alert_type = "error_rate"
        elif any(w in root_cause_lower for w in ("restart", "crash", "pod")):
            alert_type = "restart_acceleration"
        else:
            alert_type = "unknown"
        predictive_alert_id = None

    pattern_description = _generate_pattern_fingerprint(result, penalty_type, related_alert)
    root_cause_fingerprint = f"{service_name}|{alert_type}|{result.rca.root_cause or 'unknown'}"
    threshold_adjustment = _suggest_threshold_adjustment(penalty_type, related_alert)

    # Persist the penalty
    with get_session() as session:
        row = PredictivePenaltyRow(
            service_name=service_name,
            environment=environment,
            alert_type=alert_type,
            penalty_type=penalty_type,
            investigation_id=result.request_id,
            predictive_alert_id=predictive_alert_id,
            pattern_description=pattern_description,
            root_cause_fingerprint=root_cause_fingerprint,
            suggested_threshold_adjustment=threshold_adjustment,
        )
        session.add(row)
        session.commit()
        session.refresh(row)

    _log.info(
        "Predictive penalty recorded: type=%s service=%s alert_type=%s investigation=%s",
        penalty_type, service_name, alert_type, result.request_id,
    )

    # Also write to the knowledge/learnings folder for prompt injection
    try:
        loader = KnowledgeLoader()
        learning_content = (
            f"# Predictive Penalty: {penalty_type.upper()}\n\n"
            f"**Service:** {service_name}  \n"
            f"**Date:** {datetime.now(timezone.utc).isoformat()[:19]}Z  \n"
            f"**Investigation:** {result.request_id}  \n\n"
            f"{pattern_description}\n\n"
            f"**Threshold Suggestion:** {threshold_adjustment or 'N/A'}\n"
        )
        loader.append_learning(f"penalty-{result.request_id}", learning_content)
    except Exception as exc:
        _log.warning("Failed to persist penalty learning to knowledge folder: %s", exc)

    return row


def load_penalties_for_service(service_name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Load recent penalty records for a service (used for prompt injection)."""
    with get_session() as session:
        rows = session.execute(
            select(PredictivePenaltyRow)
            .where(PredictivePenaltyRow.service_name == service_name)
            .order_by(PredictivePenaltyRow.created_at.desc())
            .limit(limit)
        ).scalars().all()

    return [
        {
            "id": r.id,
            "service_name": r.service_name,
            "environment": r.environment,
            "alert_type": r.alert_type,
            "penalty_type": r.penalty_type,
            "investigation_id": r.investigation_id,
            "predictive_alert_id": r.predictive_alert_id,
            "pattern_description": r.pattern_description,
            "root_cause_fingerprint": r.root_cause_fingerprint,
            "suggested_threshold_adjustment": r.suggested_threshold_adjustment,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

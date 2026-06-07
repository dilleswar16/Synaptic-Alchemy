"""Validation automation — triggers user journey runs when predictive alerts match policies."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from corvin.storage.db import get_session
from corvin.storage.models import ValidationAutomationPolicyRow, ValidationDefinitionRow

if TYPE_CHECKING:
    from corvin.triggers.predictive import PredictiveAlert

_log = logging.getLogger(__name__)


async def evaluate_policies(alerts: list["PredictiveAlert"]) -> list[dict]:
    """Match new alerts against automation policies and trigger validation runs.

    Returns a list of dicts describing actions taken (for logging / API response).
    """
    if not alerts:
        return []

    actions: list[dict] = []

    with get_session() as db:
        policies: list[ValidationAutomationPolicyRow] = (
            db.query(ValidationAutomationPolicyRow)
            .filter(ValidationAutomationPolicyRow.enabled.is_(True))
            .all()
        )

        if not policies:
            return []

        for alert in alerts:
            for policy in policies:
                if not _matches(alert, policy):
                    continue

                defn = db.get(ValidationDefinitionRow, policy.validation_definition_id)
                if defn is None or not defn.enabled:
                    _log.warning(
                        "Policy %d references missing/disabled validation %s — skipping.",
                        policy.id,
                        policy.validation_definition_id,
                    )
                    continue

                _log.info(
                    "Auto-triggering validation '%s' for alert [%s:%s] (confidence %.1f%%).",
                    defn.name,
                    alert.service_name,
                    alert.alert_type,
                    alert.confidence_pct,
                )

                from corvin.validations.runner import run_validation

                try:
                    run = await run_validation(defn, db)
                    actions.append({
                        "policy_id": policy.id,
                        "alert_id": alert.id,
                        "service_name": alert.service_name,
                        "alert_type": alert.alert_type,
                        "confidence_pct": alert.confidence_pct,
                        "validation_name": defn.name,
                        "run_id": run.id,
                        "run_status": run.status,
                    })
                except Exception as exc:
                    _log.error(
                        "Failed to run validation '%s' triggered by alert %s: %s",
                        defn.name,
                        alert.id,
                        exc,
                    )
                    actions.append({
                        "policy_id": policy.id,
                        "alert_id": alert.id,
                        "error": str(exc),
                    })

    return actions


def _matches(alert: "PredictiveAlert", policy: ValidationAutomationPolicyRow) -> bool:
    """Return True if the alert satisfies the policy's filter criteria."""
    if alert.service_name.lower() != policy.service_name.lower():
        return False
    if alert.alert_type.lower() != policy.alert_type.lower():
        return False
    if alert.confidence_pct < policy.min_confidence_pct:
        return False
    return True

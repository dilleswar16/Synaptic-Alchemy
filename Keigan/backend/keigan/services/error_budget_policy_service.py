"""The error budget policy of an application and its evaluation (spec 30, 4.4).

The policy is **off** until an application admin turns it on: impacts are always computed and shown as information, but nothing is required of anyone until the team agreed to it.
Everything Keigan does here stays inside Keigan: a draft, a requirement, a message. Nothing writes to a customer system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.error_budget_entities import ErrorBudgetPolicy
from keigan.entities.incident_entities import Incident
from keigan.entities.status_values import IncidentStatus
from keigan.services.incident_budget_impact_service import IncidentBudgetImpactService
from keigan.utils.time_utils import utc_now
from keigan.workers.job_queue import JobQueue

EVALUATION_JOB_TYPE = "evaluate_error_budget_policy"


@dataclass(frozen=True)
class EffectivePolicy:
    """The policy in force: the team's values, or the setting defaults for what they left empty. A missing row means off."""

    is_enabled: bool
    single_incident_threshold_percent: float
    outage_class_threshold_percent: float
    outage_class_window_days: int
    exhausted_budget_guidance_text: str | None


async def effective_policy(session: AsyncSession, application_id: str) -> EffectivePolicy:
    settings = get_settings()
    row = await session.scalar(select(ErrorBudgetPolicy).where(ErrorBudgetPolicy.application_id == application_id))
    return EffectivePolicy(
        is_enabled=bool(row and row.is_enabled),
        single_incident_threshold_percent=(row.single_incident_threshold_percent if row and row.single_incident_threshold_percent is not None else settings.error_budget_policy_single_incident_threshold_percent),
        outage_class_threshold_percent=(row.outage_class_threshold_percent if row and row.outage_class_threshold_percent is not None else settings.error_budget_policy_outage_class_threshold_percent),
        outage_class_window_days=(row.outage_class_window_days if row and row.outage_class_window_days is not None else settings.error_budget_policy_outage_class_window_days),
        exhausted_budget_guidance_text=row.exhausted_budget_guidance_text if row else None,
    )


async def enqueue_error_budget_evaluation(session: AsyncSession, application_id: str) -> None:
    """One queued evaluation per application at a time (a second request merges with the queued one)."""
    await JobQueue(session).enqueue(EVALUATION_JOB_TYPE, {"application_id": application_id}, deduplication_key=f"error_budget_policy:{application_id}", priority_number=70)


class ErrorBudgetPolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def evaluate_application(self, application_id: str) -> dict[str, int]:
        """Job handler: re-evaluates the impacts of the open incidents and of those resolved recently enough that their figure is not final yet."""
        counts = {"incidents": 0, "impacts": 0}
        now = utc_now()
        # Resolved incidents stay in until one evaluation after the figure became final (the margin is two evaluation intervals), which freezes it.
        still_changing = now - timedelta(hours=self.settings.error_budget_policy_final_after_hours, minutes=2 * self.settings.error_budget_policy_evaluation_interval_minutes)
        incidents = (await self.session.scalars(select(Incident).where(
            Incident.application_id == application_id,
            or_(Incident.incident_status.not_in((IncidentStatus.RESOLVED, IncidentStatus.CLOSED)), Incident.resolved_at.is_(None), Incident.resolved_at >= still_changing),
        ))).all()
        impact_service = IncidentBudgetImpactService(self.session)
        for incident in incidents:
            rows = await impact_service.evaluate(incident, now)
            counts["incidents"] += 1
            counts["impacts"] += len(rows)
        return counts

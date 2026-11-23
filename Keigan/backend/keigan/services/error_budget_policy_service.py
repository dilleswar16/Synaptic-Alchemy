"""The error budget policy of an application and its evaluation (spec 30, 4.4).

The policy is **off** until an application admin turns it on: impacts are always computed and shown as information, but nothing is required of anyone until the team agreed to it.
Everything Keigan does here stays inside Keigan: a draft, a requirement, a message. Nothing writes to a customer system.

Three rules: one incident using more than the threshold of an SLO's budget (a postmortem with an accepted top-priority 'prevent' action item is required), one outage class (same category
and service) using more than the threshold over the class window (a top-priority item is required), and a budget that is used up (the team's own agreed response is shown).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicy, ErrorBudgetPolicyBreach, IncidentBudgetImpact
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective
from keigan.entities.status_values import (
    ActionItemPriority, ActionItemSource, ActionItemStatus, ActionItemType, ErrorBudgetBreachKind, ErrorBudgetRequirementStatus, IncidentBudgetImpactState, IncidentStatus, PostmortemStatus, SloHealthStatus,
)
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.services.audit_service import AuditService
from keigan.services.error_budget_math import MeasurementTotals, budget_share, union_of_windows
from keigan.services.incident_budget_impact_service import SUPPORTING_SIGNAL_KIND, IncidentBudgetImpactService
from keigan.services.incident_recurrence import recurrence_key
from keigan.services.postmortem_action_items import incident_reference_of
from keigan.utils.time_utils import ensure_utc, utc_now
from keigan.workers.job_queue import JobQueue

logger = logging.getLogger(__name__)
EVALUATION_JOB_TYPE = "evaluate_error_budget_policy"
SYSTEM_ACTOR = "system:keigan"
QUALIFYING_ITEM_STATUSES = (ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS, ActionItemStatus.BLOCKED, ActionItemStatus.DONE)
CLASS_ITEM_EXCLUDED_STATUSES = (ActionItemStatus.PROPOSED, ActionItemStatus.WONT_DO)


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


async def on_action_items_changed(session: AsyncSession, incident_id: str | None) -> None:
    """Called by the action item service after a change: turning the qualifying item to won't do reopens the requirement at once, accepting one meets it."""
    if incident_id:
        await ErrorBudgetPolicyService(session).refresh_requirement(incident_id)


class ErrorBudgetPolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    # ── The evaluation job ─────────────────────────────────────────────────────
    async def evaluate_application(self, application_id: str, *, now: datetime | None = None) -> dict[str, int]:
        """Job handler: re-evaluates the impacts of the open incidents and of those resolved recently enough that their figure is not final yet, then (when the team turned the policy
        on) the three rules."""
        counts = {"incidents": 0, "impacts": 0, "breaches": 0}
        now = now or utc_now()  # the job passes no time; tests move the clock to see a figure become final
        # Resolved incidents stay in until one evaluation after the figure became final (the margin is two evaluation intervals), which freezes it.
        still_changing = now - timedelta(hours=self.settings.error_budget_policy_final_after_hours, minutes=2 * self.settings.error_budget_policy_evaluation_interval_minutes)
        incidents = list((await self.session.scalars(select(Incident).where(
            Incident.application_id == application_id,
            or_(Incident.incident_status.not_in((IncidentStatus.RESOLVED, IncidentStatus.CLOSED)), Incident.resolved_at.is_(None), Incident.resolved_at >= still_changing),
        ))).all())
        impact_service = IncidentBudgetImpactService(self.session)
        for incident in incidents:
            rows = await impact_service.evaluate(incident, now)
            counts["incidents"] += 1
            counts["impacts"] += len(rows)
        policy = await effective_policy(self.session, application_id)
        application = await self.session.get(Application, application_id)
        if not policy.is_enabled or application is None:
            return counts
        for incident in incidents:
            counts["breaches"] += await self._single_incident(incident, policy, application, now)
        counts["breaches"] += await self._outage_classes(application, policy, now)
        counts["breaches"] += await self._budget_exhausted(application, now)
        return counts

    # ── Rule 1: one incident ───────────────────────────────────────────────────
    async def _single_incident(self, incident: Incident, policy: EffectivePolicy, application: Application, now: datetime) -> int:
        rows = [row for row in await IncidentBudgetImpactService(self.session).impacts_of(incident.incident_id) if row.budget_share_percent is not None]
        worst = max(rows, key=lambda row: row.budget_share_percent or 0.0, default=None)
        breach = await self._single_breach(incident.incident_id)
        if worst is None or (worst.budget_share_percent or 0.0) <= policy.single_incident_threshold_percent:
            if breach is not None and breach.is_provisional:  # the figure fell back under the threshold before it was final: withdraw. A final breach is never withdrawn.
                await AuditService(self.session).record(SYSTEM_ACTOR, "error_budget_breach.withdrawn", target_entity_type="error_budget_policy_breach", target_entity_id=breach.error_budget_policy_breach_id, application_id=application.application_id)
                await self.session.delete(breach)
            return 0
        is_provisional = any(row.impact_state == IncidentBudgetImpactState.PROVISIONAL for row in rows if row.slo_id == worst.slo_id)
        created = breach is None
        if breach is None:
            breach = ErrorBudgetPolicyBreach(
                application_id=application.application_id, breach_kind=ErrorBudgetBreachKind.SINGLE_INCIDENT, incident_id=incident.incident_id, incident_reference_text=incident_reference_of(incident),
                window_days=worst.budget_window_days, detected_at=now, requirement_status=ErrorBudgetRequirementStatus.OPEN, requirement_changed_at=now, created_by_user_principal_name=SYSTEM_ACTOR,
            )
            self.session.add(breach)
        if breach.is_provisional or created:
            breach.is_provisional = is_provisional
        breach.measured_share_percent, breach.threshold_percent, breach.slo_id, breach.sli_name_text, breach.window_days = (
            worst.budget_share_percent, policy.single_incident_threshold_percent, worst.slo_id, worst.sli_name_text, worst.budget_window_days,
        )
        await self.session.flush()
        if incident.resolved_at is not None and breach.notified_at is None:
            await self._draft_postmortem_and_notify(breach, incident, application, now)
        await self._refresh_single(breach)
        return 1 if created else 0

    async def _draft_postmortem_and_notify(self, breach: ErrorBudgetPolicyBreach, incident: Incident, application: Application, now: datetime) -> None:
        from keigan.services.error_budget_policy_notifier import ErrorBudgetPolicyNotifier

        if self.settings.error_budget_policy_auto_draft_postmortem and await self._postmortem_of(incident.incident_id) is None:
            await JobQueue(self.session).enqueue(
                "generate_postmortem", {"incident_id": incident.incident_id, "generation_trigger": "error_budget_policy", "requested_by_user_principal_name": SYSTEM_ACTOR},
                deduplication_key=f"postmortem:{incident.incident_id}",
            )
        await ErrorBudgetPolicyNotifier(self.session).notify(breach, application)
        breach.notified_at = now

    async def _single_breach(self, incident_id: str) -> ErrorBudgetPolicyBreach | None:
        return await self.session.scalar(select(ErrorBudgetPolicyBreach).where(ErrorBudgetPolicyBreach.incident_id == incident_id, ErrorBudgetPolicyBreach.breach_kind == ErrorBudgetBreachKind.SINGLE_INCIDENT))

    async def _postmortem_of(self, incident_id: str) -> PostmortemReport | None:
        return await self.session.scalar(select(PostmortemReport).where(PostmortemReport.incident_id == incident_id))

    async def qualifying_item(self, incident_id: str) -> ActionItem | None:
        """An accepted, top-priority 'prevent' item of the incident that was not closed as won't do: a proposed or dropped item does not count."""
        return await self.session.scalar(select(ActionItem).where(
            ActionItem.incident_id == incident_id, ActionItem.action_priority == ActionItemPriority.TOP, ActionItem.action_type == ActionItemType.PREVENT, ActionItem.item_status.in_(QUALIFYING_ITEM_STATUSES),
        ).order_by(ActionItem.created_at))

    async def _refresh_single(self, breach: ErrorBudgetPolicyBreach) -> None:
        if breach.requirement_status in (ErrorBudgetRequirementStatus.WAIVED, ErrorBudgetRequirementStatus.ENDED) or breach.incident_id is None:
            return
        item = await self.qualifying_item(breach.incident_id)
        postmortem = await self._postmortem_of(breach.incident_id)
        is_met = item is not None and postmortem is not None and postmortem.report_status == PostmortemStatus.FINAL
        if is_met and breach.requirement_status != ErrorBudgetRequirementStatus.MET and item is not None:
            breach.requirement_status, breach.qualifying_action_item_id, breach.requirement_changed_at = ErrorBudgetRequirementStatus.MET, item.action_item_id, utc_now()
        elif not is_met and breach.requirement_status == ErrorBudgetRequirementStatus.MET:
            breach.requirement_status, breach.qualifying_action_item_id, breach.requirement_changed_at = ErrorBudgetRequirementStatus.OPEN, None, utc_now()

    async def refresh_requirement(self, incident_id: str) -> None:
        breach = await self._single_breach(incident_id)
        if breach is not None:
            await self._refresh_single(breach)
            await self.session.flush()

    async def ensure_finalising_is_allowed(self, incident_id: str) -> None:
        """The finalise gate: a final, open breach needs an accepted top-priority 'prevent' item (or a waiver) before the postmortem can be finalised. A provisional breach does not block."""
        breach = await self._single_breach(incident_id)
        if breach is None or breach.is_provisional or breach.requirement_status != ErrorBudgetRequirementStatus.OPEN:
            return
        if await self.qualifying_item(incident_id) is not None:
            return
        share = f"{breach.measured_share_percent:g}" if breach.measured_share_percent is not None else "?"
        raise BusinessValidationException(
            f"The error budget policy needs at least one accepted top-priority 'prevent' action item (this incident used {share} % of the {breach.sli_name_text or 'SLO'} budget). Add one, or waive the requirement with a reason.",
            field_errors=[{"field": "actionItems", "message": "A top-priority 'prevent' action item is required by the error budget policy."}],
        )

    async def error_budget_prompt_facts(self, incident_id: str) -> tuple[list[str], bool]:
        """What the postmortem writer is told (spec 30, 4.4): one line per SLO with a stated share, and whether the team's policy requires a top-priority prevent item. Computed by Keigan."""
        rows = [row for row in await IncidentBudgetImpactService(self.session).impacts_of(incident_id) if row.budget_share_percent is not None]
        lines = [f"{row.sli_name_text}: {row.budget_share_percent:g} % of the {row.budget_window_days}-day budget ({row.impact_state})" for row in rows]
        breach = await self._single_breach(incident_id)
        return lines, breach is not None

    # ── Rule 2: one class of outage over a quarter ─────────────────────────────
    async def _outage_classes(self, application: Application, policy: EffectivePolicy, now: datetime) -> int:
        window_days = policy.outage_class_window_days
        since = now - timedelta(days=window_days)
        incidents = list((await self.session.scalars(select(Incident).where(Incident.application_id == application.application_id, Incident.opened_at >= since))).all())
        groups: dict[tuple[str, str], list[Incident]] = {}
        for incident in incidents:
            groups.setdefault(recurrence_key(incident), []).append(incident)
        created = 0
        impact_service = IncidentBudgetImpactService(self.session)
        for (category, service_id), members in groups.items():
            if len(members) < 2 or not service_id:
                continue
            already = await self.session.scalar(select(ErrorBudgetPolicyBreach).where(
                ErrorBudgetPolicyBreach.application_id == application.application_id, ErrorBudgetPolicyBreach.breach_kind == ErrorBudgetBreachKind.OUTAGE_CLASS,
                ErrorBudgetPolicyBreach.recurrence_category == category, ErrorBudgetPolicyBreach.recurrence_service_id == service_id, ErrorBudgetPolicyBreach.detected_at >= since,
            ))
            if already is not None:
                continue
            worst = await self._worst_class_share(members, impact_service, window_days, now)
            if worst is None or worst[0] <= policy.outage_class_threshold_percent:
                continue
            share, slo_id, sli_name = worst
            from keigan.entities.application_entities import MonitoredService

            service = await self.session.get(MonitoredService, service_id)
            breach = ErrorBudgetPolicyBreach(
                application_id=application.application_id, breach_kind=ErrorBudgetBreachKind.OUTAGE_CLASS, slo_id=slo_id, sli_name_text=sli_name, recurrence_category=category, recurrence_service_id=service_id,
                recurrence_service_name_text=service.service_name if service else None, measured_share_percent=share, threshold_percent=policy.outage_class_threshold_percent, window_days=window_days,
                detected_at=now, requirement_status=ErrorBudgetRequirementStatus.OPEN, requirement_changed_at=now, created_by_user_principal_name=SYSTEM_ACTOR,
            )
            self.session.add(breach)
            await self.session.flush()
            from keigan.services.error_budget_policy_notifier import ErrorBudgetPolicyNotifier

            await ErrorBudgetPolicyNotifier(self.session).notify(breach, application)
            breach.notified_at = now
            created += 1
        for breach in (await self.session.scalars(select(ErrorBudgetPolicyBreach).where(
            ErrorBudgetPolicyBreach.application_id == application.application_id, ErrorBudgetPolicyBreach.breach_kind == ErrorBudgetBreachKind.OUTAGE_CLASS,
            ErrorBudgetPolicyBreach.requirement_status.in_((ErrorBudgetRequirementStatus.OPEN, ErrorBudgetRequirementStatus.MET))))).all():
            await self.refresh_class_requirement(breach, now)
        return created

    async def _worst_class_share(self, members: list[Incident], impact_service: IncidentBudgetImpactService, window_days: int, now: datetime) -> tuple[float, str | None, str] | None:
        """The largest share over the class window across the SLOs the class's incidents touched. Bad events are counted over the union of the incidents' impact windows, so overlap counts once."""
        rows = list((await self.session.scalars(select(IncidentBudgetImpact).where(IncidentBudgetImpact.incident_id.in_([member.incident_id for member in members]), IncidentBudgetImpact.slo_id.is_not(None)))).all())
        windows_by_slo: dict[str, list[tuple[datetime, datetime]]] = {}
        for row in rows:
            if row.slo_id:
                windows_by_slo.setdefault(row.slo_id, []).append((ensure_utc(row.impact_window_start) or now, ensure_utc(row.impact_window_end) or now))
        worst: tuple[float, str | None, str] | None = None
        for slo_id, windows in windows_by_slo.items():
            slo = await self.session.get(ServiceLevelObjective, slo_id)
            sli = await self.session.get(ServiceLevelIndicator, slo.sli_id) if slo else None
            if slo is None or sli is None:
                continue
            bad = 0
            for start, end in union_of_windows(windows):
                bad += (await impact_service.totals(sli.sli_id, start, end)).bad
            window = await impact_service.totals(sli.sli_id, now - timedelta(days=window_days), now)
            share = budget_share(
                MeasurementTotals(good=0, total=bad, measured_window_count=0), window, slo.target_percentage, window_days,
                minimum_coverage_percent=self.settings.error_budget_policy_minimum_data_coverage_percent, minimum_window_events=self.settings.error_budget_policy_minimum_window_events,
            )
            if share.share_percent is not None and (worst is None or share.share_percent > worst[0]):
                worst = (share.share_percent, slo_id, sli.sli_name[:200])
        return worst

    async def refresh_class_requirement(self, breach: ErrorBudgetPolicyBreach, now: datetime | None = None) -> None:
        """An outage-class breach is met by a top-priority item that came from it, or one on an incident of the class created in the class window, that is accepted and not dropped."""
        now = now or utc_now()
        since = now - timedelta(days=breach.window_days)
        class_incident_ids = [
            incident.incident_id for incident in (await self.session.scalars(select(Incident).where(Incident.application_id == breach.application_id, Incident.opened_at >= since))).all()
            if recurrence_key(incident) == (breach.recurrence_category, breach.recurrence_service_id)
        ]
        conditions = [(ActionItem.item_source_kind == ActionItemSource.ERROR_BUDGET_POLICY) & (ActionItem.source_record_id == breach.error_budget_policy_breach_id)]
        if class_incident_ids:
            conditions.append(ActionItem.incident_id.in_(class_incident_ids) & (ActionItem.created_at >= since))
        item = await self.session.scalar(select(ActionItem).where(or_(*conditions), ActionItem.action_priority == ActionItemPriority.TOP, ActionItem.item_status.not_in(CLASS_ITEM_EXCLUDED_STATUSES)).order_by(ActionItem.created_at))
        if item is not None and breach.requirement_status == ErrorBudgetRequirementStatus.OPEN:
            breach.requirement_status, breach.qualifying_action_item_id, breach.requirement_changed_at = ErrorBudgetRequirementStatus.MET, item.action_item_id, now
        elif item is None and breach.requirement_status == ErrorBudgetRequirementStatus.MET:
            breach.requirement_status, breach.qualifying_action_item_id, breach.requirement_changed_at = ErrorBudgetRequirementStatus.OPEN, None, now

    # ── Rule 3: a budget used up ───────────────────────────────────────────────
    async def _budget_exhausted(self, application: Application, now: datetime) -> int:
        from keigan.services.error_budget_policy_notifier import ErrorBudgetPolicyNotifier
        from keigan.services.slo_service import SloService

        summaries = await SloService(self.session).summarize_slos([application.application_id])
        breached = {summary["sloId"]: summary for summary in summaries if summary["status"] == SloHealthStatus.BREACHED and summary.get("sliKind") != SUPPORTING_SIGNAL_KIND}
        open_breaches = {
            breach.slo_id: breach for breach in (await self.session.scalars(select(ErrorBudgetPolicyBreach).where(
                ErrorBudgetPolicyBreach.application_id == application.application_id, ErrorBudgetPolicyBreach.breach_kind == ErrorBudgetBreachKind.BUDGET_EXHAUSTED,
                ErrorBudgetPolicyBreach.requirement_status == ErrorBudgetRequirementStatus.OPEN))).all()
        }
        created = 0
        for slo_id, summary in breached.items():
            if slo_id in open_breaches:
                continue
            breach = ErrorBudgetPolicyBreach(
                application_id=application.application_id, breach_kind=ErrorBudgetBreachKind.BUDGET_EXHAUSTED, slo_id=slo_id, sli_name_text=str(summary["sliName"])[:200], window_days=int(summary["rollingWindowDays"]),
                detected_at=now, requirement_status=ErrorBudgetRequirementStatus.OPEN, requirement_changed_at=now, created_by_user_principal_name=SYSTEM_ACTOR,
            )
            self.session.add(breach)
            await self.session.flush()
            await ErrorBudgetPolicyNotifier(self.session).notify(breach, application)
            breach.notified_at = now
            created += 1
        for slo_id, breach in open_breaches.items():
            if slo_id not in breached:
                breach.requirement_status, breach.requirement_changed_at = ErrorBudgetRequirementStatus.ENDED, now
        return created

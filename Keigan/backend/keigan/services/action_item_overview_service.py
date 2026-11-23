"""The action items overview (spec 29, 4.4): are follow-ups getting done, what needs attention now, and which incidents came back and what had happened to their follow-ups.

Counts per application, never a ranking of people. Only applications the caller may read are included.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import Settings, get_settings
from keigan.dtos.action_item_dtos import (
    ActionItemOverviewResponse, ApplicationCompletionDto, AttentionEntryDto, CompletionFiguresDto, EarlierPreventItemDto, RepeatGroupDto, RepeatIncidentDto,
)
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.error_budget_entities import ErrorBudgetPolicyBreach
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.entities.status_values import ActionItemPriority, ActionItemStatus, ActionItemType, ErrorBudgetBreachKind, ErrorBudgetRequirementStatus, PostmortemStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_overview_rules import (
    AttentionEntry, AttentionKind, CompletionFigures, IncidentFacts, ItemFacts, PreventItemFacts, attention_order, completion_figures, prevent_item_state_at, repeat_groups,
    repeat_outcome,
)
from keigan.services.action_item_rules import TRACKED_STATUSES, days_overdue, local_today
from keigan.services.authorization_service import AuthorizationService
from keigan.services.incident_recurrence import recurrence_key
from keigan.utils.time_utils import ensure_utc, utc_now


def _figures_dto(figures: CompletionFigures) -> CompletionFiguresDto:
    return CompletionFiguresDto(**{name: getattr(figures, name) for name in CompletionFiguresDto.model_fields})


def _incident_label(incident: Incident) -> str:
    return incident.external_incident_number or incident.incident_id[:8]


class ActionItemOverviewService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings: Settings = get_settings()
        self.authorization = AuthorizationService(session)

    async def overview(self, current_user: CurrentUser, application_ids: list[str] | None, days: int | None, *, now: datetime | None = None) -> ActionItemOverviewResponse:
        period_days = days if days is not None else self.settings.action_items_overview_default_days
        maximum = self.settings.action_items_overview_maximum_days
        if not 1 <= period_days <= maximum:
            raise BusinessValidationException(f"Choose a period between 1 and {maximum} days.")
        now = now or utc_now()
        period_start = now - timedelta(days=period_days)
        scope = await self.authorization.scoped_application_ids(current_user, application_ids)
        if not scope:
            return ActionItemOverviewResponse(
                period_start=period_start, period_end=now, period_days=period_days, completion=_figures_dto(completion_figures([], [], now)), by_application=[], needs_attention=[], repeats=[],
            )
        applications = {row.application_id: row for row in (await self.session.scalars(select(Application).where(Application.application_id.in_(scope)))).all()}
        items = list((await self.session.scalars(select(ActionItem).where(ActionItem.application_id.in_(scope)))).all())
        completion, by_application = self._completion(items, applications, period_start, now)
        attention = await self._needs_attention(items, applications, scope, period_start, now)
        return ActionItemOverviewResponse(
            period_start=period_start, period_end=now, period_days=period_days, completion=completion, by_application=by_application,
            needs_attention=[AttentionEntryDto(
                kind=entry.kind, application_id=entry.application_id, application_name=applications[entry.application_id].application_name, record_kind=entry.record_kind,
                record_id=entry.record_id, title=entry.title, parameters=entry.parameters,
            ) for entry in attention_order(attention)],
            repeats=await self._repeats(applications, scope, now),
        )

    # ── Completion ─────────────────────────────────────────────────────────────
    @staticmethod
    def _facts(item: ActionItem, application: Application) -> ItemFacts:
        return ItemFacts(
            status=item.item_status, due_on=item.due_on, original_due_on=item.original_due_on, accepted_at=ensure_utc(item.accepted_at), completed_at=ensure_utc(item.completed_at),
            time_zone_name=application.time_zone_name,
        )

    def _completion(
        self, items: list[ActionItem], applications: dict[str, Application], period_start: datetime, now: datetime,
    ) -> tuple[CompletionFiguresDto, list[ApplicationCompletionDto]]:
        def figures_for(subset: list[ActionItem]) -> CompletionFigures:
            accepted = [self._facts(item, applications[item.application_id]) for item in subset if item.accepted_at is not None and ensure_utc(item.accepted_at) >= period_start]
            tracked = [self._facts(item, applications[item.application_id]) for item in subset if item.item_status in TRACKED_STATUSES]
            return completion_figures(accepted, tracked, now)

        per_application: dict[str, list[ActionItem]] = defaultdict(list)
        for item in items:
            per_application[item.application_id].append(item)
        rows = [
            ApplicationCompletionDto(application_id=application_id, application_name=application.application_name, **_figures_dto(figures_for(per_application.get(application_id, []))).model_dump())
            for application_id, application in sorted(applications.items(), key=lambda pair: pair[1].application_name.lower())
        ]
        return _figures_dto(figures_for(items)), rows

    # ── Needs attention ────────────────────────────────────────────────────────
    async def _needs_attention(
        self, items: list[ActionItem], applications: dict[str, Application], scope: list[str], period_start: datetime, now: datetime,
    ) -> list[AttentionEntry]:
        entries: list[AttentionEntry] = []
        for item in items:
            if item.item_status not in TRACKED_STATUSES:
                continue
            today = local_today(applications[item.application_id].time_zone_name, now)
            overdue_days = days_overdue(item.item_status, item.due_on, today)
            link = {"incidentId": item.incident_id, "incidentReference": item.incident_reference_text}
            if overdue_days > 0:
                entries.append(AttentionEntry(AttentionKind.OVERDUE_ITEM, item.application_id, "action_item", item.action_item_id, item.item_title, {"daysOverdue": overdue_days, "priority": item.action_priority, **link}))
            if item.action_priority == ActionItemPriority.TOP and item.owner_stakeholder_id is None:
                entries.append(AttentionEntry(AttentionKind.TOP_PRIORITY_UNOWNED, item.application_id, "action_item", item.action_item_id, item.item_title, link))
        entries += await self._open_policy_breaches(scope)
        entries += await self._missing_postmortems(scope, period_start, now)
        entries += await self._waiting_suggestions(items, now)
        return entries

    async def _open_policy_breaches(self, scope: list[str]) -> list[AttentionEntry]:
        breaches = (await self.session.scalars(select(ErrorBudgetPolicyBreach).where(
            ErrorBudgetPolicyBreach.application_id.in_(scope), ErrorBudgetPolicyBreach.requirement_status == ErrorBudgetRequirementStatus.OPEN,
        ))).all()
        def title(breach: ErrorBudgetPolicyBreach) -> str:
            if breach.breach_kind == ErrorBudgetBreachKind.SINGLE_INCIDENT:
                return breach.incident_reference_text or "Incident"
            if breach.breach_kind == ErrorBudgetBreachKind.OUTAGE_CLASS:
                return f"{breach.recurrence_service_name_text or 'Service'}: {(breach.recurrence_category or '').replace('_', ' ')}"
            return breach.sli_name_text or "Service level objective"
        return [AttentionEntry(
            AttentionKind.POLICY_BREACH_OPEN, breach.application_id, "error_budget_policy_breach", breach.error_budget_policy_breach_id, title(breach),
            {"breachKind": breach.breach_kind, "sharePercent": breach.measured_share_percent, "incidentId": breach.incident_id},
        ) for breach in breaches]

    async def _missing_postmortems(self, scope: list[str], period_start: datetime, now: datetime) -> list[AttentionEntry]:
        required = self.settings.action_items_postmortem_required_priority_list
        grace_limit = now - timedelta(days=self.settings.action_items_postmortem_grace_days)
        incidents = (await self.session.scalars(select(Incident).where(
            Incident.application_id.in_(scope), Incident.keigan_priority.in_(required), Incident.resolved_at.is_not(None), Incident.resolved_at >= period_start, Incident.resolved_at <= grace_limit,
        ))).all()
        if not incidents:
            return []
        with_final = set((await self.session.scalars(select(PostmortemReport.incident_id).where(
            PostmortemReport.incident_id.in_([incident.incident_id for incident in incidents]), PostmortemReport.report_status == PostmortemStatus.FINAL,
        ))).all())
        return [
            AttentionEntry(
                AttentionKind.POSTMORTEM_MISSING, incident.application_id, "incident", incident.incident_id, f"{_incident_label(incident)} {incident.incident_title}",
                {"incidentPriority": incident.keigan_priority, "daysWaiting": (now - ensure_utc(incident.resolved_at)).days, "incidentId": incident.incident_id},
            )
            for incident in incidents if incident.incident_id not in with_final
        ]

    async def _waiting_suggestions(self, items: list[ActionItem], now: datetime) -> list[AttentionEntry]:
        grace_limit = now - timedelta(days=self.settings.action_items_postmortem_grace_days)
        waiting: dict[str, list[ActionItem]] = defaultdict(list)
        for item in items:
            if item.item_status == ActionItemStatus.PROPOSED and item.postmortem_id and ensure_utc(item.created_at) <= grace_limit:
                waiting[item.postmortem_id].append(item)
        if not waiting:
            return []
        postmortems = {row.postmortem_id: row for row in (await self.session.scalars(select(PostmortemReport).where(PostmortemReport.postmortem_id.in_(list(waiting))))).all()}
        return [
            AttentionEntry(
                AttentionKind.PROPOSED_WAITING, group[0].application_id, "postmortem", postmortem_id, postmortems[postmortem_id].report_title if postmortem_id in postmortems else group[0].incident_reference_text or "Postmortem",
                {"proposedCount": len(group), "daysWaiting": (now - ensure_utc(min(item.created_at for item in group))).days, "incidentId": group[0].incident_id},
            )
            for postmortem_id, group in waiting.items()
        ]

    # ── Repeats ────────────────────────────────────────────────────────────────
    async def _repeats(self, applications: dict[str, Application], scope: list[str], now: datetime) -> list[RepeatGroupDto]:
        window_start = now - timedelta(days=self.settings.action_items_repeat_window_days)
        incidents = list((await self.session.scalars(select(Incident).where(Incident.application_id.in_(scope), Incident.opened_at >= window_start).order_by(Incident.opened_at))).all())
        by_id = {incident.incident_id: incident for incident in incidents}
        groups = repeat_groups(IncidentFacts(incident.incident_id, recurrence_key(incident), ensure_utc(incident.opened_at)) for incident in incidents)
        if not groups:
            return []
        incident_ids = list(by_id)
        final_postmortems: dict[str, list[datetime | None]] = defaultdict(list)
        for postmortem in (await self.session.scalars(select(PostmortemReport).where(PostmortemReport.incident_id.in_(incident_ids), PostmortemReport.report_status == PostmortemStatus.FINAL))).all():
            final_postmortems[postmortem.incident_id].append(ensure_utc(postmortem.finalized_at))
        prevent_items: dict[str, list[ActionItem]] = defaultdict(list)
        for item in (await self.session.scalars(select(ActionItem).where(ActionItem.incident_id.in_(incident_ids), ActionItem.action_type == ActionItemType.PREVENT, ActionItem.accepted_at.is_not(None)))).all():
            prevent_items[item.incident_id or ""].append(item)
        service_names = {row.service_id: row.service_name for row in (await self.session.scalars(select(MonitoredService).where(MonitoredService.service_id.in_({group[0].recurrence_key[1] for group in groups})))).all()}

        result: list[RepeatGroupDto] = []
        for group in groups:
            repeat_incidents: list[RepeatIncidentDto] = []
            for position, member in enumerate(group):
                incident = by_id[member.incident_id]
                if position == 0:
                    repeat_incidents.append(RepeatIncidentDto(incident_id=incident.incident_id, incident_reference=_incident_label(incident), opened_at=member.opened_at))
                    continue
                earlier = group[:position]
                has_final = any(finalized_at is None or finalized_at <= member.opened_at for earlier_member in earlier for finalized_at in final_postmortems.get(earlier_member.incident_id, []))
                facts = [
                    PreventItemFacts(item.action_item_id, item.item_title, item.item_status, ensure_utc(item.accepted_at), ensure_utc(item.completed_at))
                    for earlier_member in earlier for item in prevent_items.get(earlier_member.incident_id, [])
                ]
                states = [(fact, prevent_item_state_at(fact, member.opened_at)) for fact in facts]
                repeat_incidents.append(RepeatIncidentDto(
                    incident_id=incident.incident_id, incident_reference=_incident_label(incident), opened_at=member.opened_at, outcome=repeat_outcome(has_final, facts, member.opened_at),
                    earlier_prevent_items=[EarlierPreventItemDto(action_item_id=fact.action_item_id, item_title=fact.title, status_at_repeat=state) for fact, state in states if state is not None],
                ))
            first = by_id[group[0].incident_id]
            category, service_id = group[0].recurrence_key
            result.append(RepeatGroupDto(
                application_id=first.application_id, application_name=applications[first.application_id].application_name, recurrence_category=category, service_id=service_id,
                service_name=service_names.get(service_id, ""), incidents=repeat_incidents,
            ))
        return result

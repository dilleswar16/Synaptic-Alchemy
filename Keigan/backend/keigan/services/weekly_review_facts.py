"""The two review sections of the weekly digest (spec 31, 4.3): what the week cost the error budgets, and where the follow-ups stand. Built by code from stored rows; the model is only
given the figures to phrase, it never computes them."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicyBreach, IncidentBudgetImpact
from keigan.entities.incident_entities import Incident
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ActionItemPriority, ActionItemStatus, ErrorBudgetRequirementStatus
from keigan.services.action_item_rules import TRACKED_STATUSES, days_overdue, local_today
from keigan.services.error_budget_policy_service import effective_policy
from keigan.utils.time_utils import ensure_utc


def _within(moment: datetime | None, start: datetime, end: datetime) -> bool:
    moment = ensure_utc(moment)
    return moment is not None and start <= moment <= end


async def weekly_review_sections(
    session: AsyncSession, application: Application, period_start: datetime, period_end: datetime, now: datetime, maximum_listed_items: int,
) -> dict[str, Any]:
    return {
        "budget": await _budget_section(session, application, period_start, period_end),
        "actionItems": await _action_item_section(session, application, period_start, period_end, now, maximum_listed_items),
    }


async def _budget_section(session: AsyncSession, application: Application, period_start: datetime, period_end: datetime) -> dict[str, Any]:
    incidents = list((await session.scalars(select(Incident).where(Incident.application_id == application.application_id, Incident.opened_at >= period_start, Incident.opened_at <= period_end).order_by(Incident.opened_at))).all())
    impacts = list((await session.scalars(select(IncidentBudgetImpact).where(IncidentBudgetImpact.incident_id.in_([incident.incident_id for incident in incidents])))).all()) if incidents else []
    worst_by_incident: dict[str, IncidentBudgetImpact] = {}
    for impact in impacts:
        if impact.budget_share_percent is not None and (impact.incident_id not in worst_by_incident or impact.budget_share_percent > (worst_by_incident[impact.incident_id].budget_share_percent or 0.0)):
            worst_by_incident[impact.incident_id] = impact
    rows = [
        {
            "incidentNumber": incident.external_incident_number or incident.incident_id[:8], "incidentTitle": incident.incident_title, "sliName": worst_by_incident[incident.incident_id].sli_name_text,
            "sharePercent": worst_by_incident[incident.incident_id].budget_share_percent, "impactState": worst_by_incident[incident.incident_id].impact_state,
        }
        for incident in incidents if incident.incident_id in worst_by_incident
    ]
    breaches = list((await session.scalars(select(ErrorBudgetPolicyBreach).where(ErrorBudgetPolicyBreach.application_id == application.application_id))).all())
    return {
        "policyIsEnabled": (await effective_policy(session, application.application_id)).is_enabled,
        "incidents": sorted(rows, key=lambda row: -(row["sharePercent"] or 0.0)),
        "incidentsWithoutFigureCount": len(incidents) - len(rows),
        "breachesOpenedCount": sum(1 for breach in breaches if _within(breach.detected_at, period_start, period_end)),
        "openBreaches": [
            {"kind": breach.breach_kind, "sharePercent": breach.measured_share_percent, "incidentNumber": breach.incident_reference_text, "sliName": breach.sli_name_text}
            for breach in breaches if breach.requirement_status == ErrorBudgetRequirementStatus.OPEN
        ],
    }


async def _action_item_section(session: AsyncSession, application: Application, period_start: datetime, period_end: datetime, now: datetime, maximum_listed_items: int) -> dict[str, Any]:
    items = list((await session.scalars(select(ActionItem).where(ActionItem.application_id == application.application_id))).all())
    owners = {person.stakeholder_id: person.display_name for person in (await session.scalars(select(Stakeholder).where(Stakeholder.application_id == application.application_id))).all()}
    today = local_today(application.time_zone_name, now)
    tracked = [item for item in items if item.item_status in TRACKED_STATUSES]
    overdue = sorted((item for item in tracked if days_overdue(item.item_status, item.due_on, today) > 0), key=lambda item: -days_overdue(item.item_status, item.due_on, today))
    return {
        "openCount": len(tracked),
        "overdueCount": len(overdue),
        "overdue": [
            {"title": item.item_title, "owner": owners.get(item.owner_stakeholder_id or ""), "priority": item.action_priority, "daysOverdue": days_overdue(item.item_status, item.due_on, today), "incidentNumber": item.incident_reference_text}
            for item in overdue[:maximum_listed_items]
        ],
        "doneThisWeekCount": sum(1 for item in items if item.item_status == ActionItemStatus.DONE and _within(item.completed_at, period_start, period_end)),
        "acceptedThisWeekCount": sum(1 for item in items if _within(item.accepted_at, period_start, period_end)),
        "topPriorityWithoutOwner": [item.item_title for item in tracked if item.action_priority == ActionItemPriority.TOP and item.owner_stakeholder_id is None][:maximum_listed_items],
        "suggestedWaitingCount": sum(1 for item in items if item.item_status == ActionItemStatus.PROPOSED),
    }


def review_fact_lines(sections: dict[str, Any]) -> list[str]:
    """The same figures as short lines: given to the narration and written into the Markdown."""
    budget, items = sections["budget"], sections["actionItems"]
    lines = [
        "Error budget: " + (
            "; ".join(f"{row['incidentNumber']} used {row['sharePercent']:g}% of {row['sliName']} ({row['impactState']})" for row in budget["incidents"][:5]) or "no incident of the week has a stated budget figure"
        ) + (f"; {budget['incidentsWithoutFigureCount']} incident(s) without a figure" if budget["incidentsWithoutFigureCount"] else "") + ".",
        f"Policy: {'on' if budget['policyIsEnabled'] else 'off'}; {budget['breachesOpenedCount']} breach(es) opened this week, {len(budget['openBreaches'])} open.",
        f"Follow-ups: {items['openCount']} open, {items['overdueCount']} overdue, {items['doneThisWeekCount']} done this week, {items['acceptedThisWeekCount']} accepted this week, {items['suggestedWaitingCount']} suggestion(s) waiting.",
    ]
    if items["topPriorityWithoutOwner"]:
        lines.append("Top-priority items without an owner: " + "; ".join(items["topPriorityWithoutOwner"]) + ".")
    return lines


def review_markdown_lines(sections: dict[str, Any]) -> list[str]:
    budget, items = sections["budget"], sections["actionItems"]
    lines = ["## Error budget"]
    lines += [f"- {row['incidentNumber']} {row['incidentTitle']}: {row['sharePercent']:g} % of {row['sliName']} ({row['impactState']})" for row in budget["incidents"]] or ["- No incident of the week has a stated budget figure."]
    lines += [f"- Policy {'on' if budget['policyIsEnabled'] else 'off'}: {budget['breachesOpenedCount']} breach(es) opened this week; {len(budget['openBreaches'])} open."]
    lines += ["", "## Follow-ups", f"- {items['openCount']} open, {items['overdueCount']} overdue, {items['doneThisWeekCount']} done this week, {items['acceptedThisWeekCount']} accepted this week."]
    lines += [f"- Overdue: {row['title']} ({row['daysOverdue']} days, {row['owner'] or 'no owner'})" for row in items["overdue"]]
    lines += [f"- Top priority, no owner: {title}" for title in items["topPriorityWithoutOwner"]]
    return [*lines, ""]

"""The postmortem's action items as rows (spec 29, 4.4): the AI's suggestions become ``proposed`` rows, the document's table is rendered from the rows, and finalising needs every
suggestion accepted or discarded. The rows are the truth: the Markdown table is a rendering of them (an edit of the table in the text cannot make the two disagree any more).

The document shows each owner's *role*, never the person (blameless); the tracker shows the person (accountable). The AI wrote only a title and a role in words.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.output_sanitizer import sanitize_ai_line
from keigan.config.settings import Settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ActionItemPriority, ActionItemSource, ActionItemStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.services.action_item_rules import proposed_due_on
from keigan.utils.time_utils import utc_now

_ACTION_ITEMS_SECTION = re.compile(r"^## Action items\s*\n.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
NO_ACTION_ITEMS_TEXT = "No action items recorded."


def incident_reference_of(incident: Incident) -> str:
    return (incident.external_incident_number or incident.incident_id[:8])[:60]


async def replace_proposed_items(
    session: AsyncSession, postmortem: PostmortemReport, incident: Incident, application: Application, suggested_items: Sequence[Any], settings: Settings,
) -> list[ActionItem]:
    """A new draft replaces the earlier suggestions (accepted items stay) with one ``proposed`` row per suggestion the model made, at most the setting."""
    await session.execute(delete(ActionItem).where(ActionItem.postmortem_id == postmortem.postmortem_id, ActionItem.item_status == ActionItemStatus.PROPOSED))
    kept_count = int(await session.scalar(select(func.count()).select_from(ActionItem).where(ActionItem.postmortem_id == postmortem.postmortem_id)) or 0)
    base_moment = incident.resolved_at or utc_now()
    rows: list[ActionItem] = []
    for order, suggestion in enumerate(suggested_items[: settings.action_items_maximum_per_postmortem], start=kept_count):
        rows.append(ActionItem(
            application_id=application.application_id, incident_id=incident.incident_id, postmortem_id=postmortem.postmortem_id, incident_reference_text=incident_reference_of(incident),
            item_source_kind=ActionItemSource.POSTMORTEM, item_title=sanitize_ai_line(suggestion.description, maximum_characters=300), suggested_owner_role_text=sanitize_ai_line(suggestion.owner_role, maximum_characters=200),
            action_type=suggestion.action_type, action_priority=getattr(suggestion, "priority", ActionItemPriority.NORMAL), item_status=ActionItemStatus.PROPOSED,
            due_on=proposed_due_on(base_moment, suggestion.due_in_days, application.time_zone_name, maximum_days=settings.action_items_maximum_due_days), display_order=order,
            created_by_user_principal_name="system:postmortem",
        ))
    session.add_all(rows)
    await session.flush()
    return rows


async def items_of(session: AsyncSession, postmortem_id: str) -> list[ActionItem]:
    return list((await session.scalars(select(ActionItem).where(ActionItem.postmortem_id == postmortem_id).order_by(ActionItem.display_order, ActionItem.created_at))).all())


def render_action_items_table(items: Sequence[ActionItem], roles_by_stakeholder_id: dict[str, str]) -> str:
    """A Markdown table of the rows: action, owner role, due date, type, priority. An item with no owner shows the role the AI suggested; no person is ever named."""
    if not items:
        return NO_ACTION_ITEMS_TEXT
    lines = ["| Action | Owner role | Due | Type | Priority |", "|---|---|---|---|---|"]
    for item in items:
        role = roles_by_stakeholder_id.get(item.owner_stakeholder_id or "") or item.suggested_owner_role_text or "Unassigned"
        due = item.due_on.isoformat() if item.due_on else ""
        lines.append(f"| {item.item_title.replace('|', '/')} | {role.replace('|', '/')} | {due} | {item.action_type} | {item.action_priority} |")
    return "\n".join(lines)


def replace_action_items_section(markdown: str, table: str) -> str:
    """Replaces the text under ``## Action items`` (up to the next ``## `` heading) with ``table``, or appends the section when the document has none."""
    section = f"## Action items\n{table}\n\n"
    if _ACTION_ITEMS_SECTION.search(markdown):
        return _ACTION_ITEMS_SECTION.sub(lambda _: section, markdown, count=1)
    return markdown.rstrip() + "\n\n" + section.rstrip() + "\n"


async def roles_by_stakeholder_id(session: AsyncSession, items: Sequence[ActionItem]) -> dict[str, str]:
    owner_ids = {item.owner_stakeholder_id for item in items if item.owner_stakeholder_id}
    if not owner_ids:
        return {}
    rows = (await session.execute(select(Stakeholder.stakeholder_id, Stakeholder.stakeholder_role).where(Stakeholder.stakeholder_id.in_(owner_ids)))).all()
    return {stakeholder_id: role for stakeholder_id, role in rows}


async def ensure_none_proposed(session: AsyncSession, postmortem_id: str) -> None:
    """Finalising needs a decision on every suggestion: a suggestion nobody accepted is not a commitment."""
    proposed_count = int(await session.scalar(
        select(func.count()).select_from(ActionItem).where(ActionItem.postmortem_id == postmortem_id, ActionItem.item_status == ActionItemStatus.PROPOSED)
    ) or 0)
    if proposed_count:
        raise BusinessValidationException(
            f"Accept or discard the {proposed_count} suggested action item(s) before finalising.", field_errors=[{"field": "actionItems", "message": f"{proposed_count} suggested item(s) are waiting."}],
        )


async def render_final_table(session: AsyncSession, postmortem_id: str) -> str:
    tracked = [item for item in await items_of(session, postmortem_id) if item.item_status != ActionItemStatus.PROPOSED]
    return render_action_items_table(tracked, await roles_by_stakeholder_id(session, tracked))

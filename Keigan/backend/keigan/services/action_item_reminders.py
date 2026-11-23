"""Daily reminders for action items (spec 29, 4.4): one email per owner listing what is due soon or overdue, and one escalation email per lead or manager listing what is long overdue
or has nobody to do it. The emails go through the notification outbox like every other email, in the recipient's language.

The job runs once per application per local day (its deduplication key says so); the rules (``reminder_kind``) decide what each item needs, and an item is stamped when it is included, so a
second run the same day sends nothing.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ExternalSyncStatus, StakeholderRecipientType
from keigan.services.action_item_rules import TRACKED_STATUSES, ReminderKind, days_overdue, local_today, reminder_kind
from keigan.services.notification_service import NotificationService
from keigan.utils.string_table import translate
from keigan.utils.time_utils import utc_now

ACTION_ITEMS_PATH = "/action-items?owner=me"
ESCALATION_PATH = "/action-items?overdueOnly=true"


class ActionItemReminderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.notifications = NotificationService(session)

    async def send_due_reminders(self, application_id: str) -> dict[str, int]:
        """Job handler. Returns how many owners and escalation recipients were emailed and how many items were included."""
        counts = {"owners": 0, "escalations": 0, "items": 0}
        if not self.settings.action_items_reminders_enabled:
            return counts
        application = await self.session.get(Application, application_id)
        if application is None:
            return counts
        now = utc_now()
        today = local_today(application.time_zone_name, now)
        items = list((await self.session.scalars(select(ActionItem).where(ActionItem.application_id == application_id, ActionItem.item_status.in_(TRACKED_STATUSES), ActionItem.due_on.is_not(None),
            or_(ActionItem.external_sync_status.is_(None), ActionItem.external_sync_status != ExternalSyncStatus.LINKED)))).all())  # an item ServiceNow tracks gets its reminders there, not from Keigan
        kinds = {item.action_item_id: self._kind_of(item, today, application.time_zone_name) for item in items}
        due = [item for item in items if kinds[item.action_item_id] is not None]
        if not due:
            return counts
        people = {person.stakeholder_id: person for person in (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id == application_id, Stakeholder.is_active.is_(True)))).all()}
        for_owner: dict[str, list[ActionItem]] = defaultdict(list)
        for_escalation: list[ActionItem] = []
        for item in due:
            owner = people.get(item.owner_stakeholder_id or "")
            reachable = owner is not None and owner.recipient_type == StakeholderRecipientType.PERSON and self.notifications.recipient_address_for(owner, "email")
            if reachable and owner is not None:
                for_owner[owner.stakeholder_id].append(item)
            if not reachable or kinds[item.action_item_id] is ReminderKind.ESCALATE:
                for_escalation.append(item)
        included: set[str] = set()
        for stakeholder_id, owned in for_owner.items():
            owner = people[stakeholder_id]
            await self._email(application, owner, "action_item_reminder", owned, today, ACTION_ITEMS_PATH, people)
            counts["owners"] += 1
            included.update(item.action_item_id for item in owned)
        if for_escalation:
            for recipient in self._escalation_recipients(people):
                await self._email(application, recipient, "action_item_escalation", for_escalation, today, ESCALATION_PATH, people)
                counts["escalations"] += 1
            included.update(item.action_item_id for item in for_escalation)
        for item in items:
            if item.action_item_id in included:
                item.last_reminded_at, item.reminder_count = now, item.reminder_count + 1
        counts["items"] = len(included)
        await self.session.flush()
        return counts

    def _kind_of(self, item: ActionItem, today: date, time_zone_name: str | None) -> ReminderKind | None:
        last_reminded_on = local_today(time_zone_name, item.last_reminded_at) if item.last_reminded_at else None
        return reminder_kind(
            item.item_status, item.action_priority, item.due_on, today, last_reminded_on, days_before_due=self.settings.action_items_reminder_days_before_due,
            overdue_interval_days=self.settings.action_items_overdue_reminder_interval_days, escalate_after_days=self.settings.action_items_escalate_after_overdue_days,
        )

    def _escalation_recipients(self, people: dict[str, Stakeholder]) -> list[Stakeholder]:
        roles = set(self.settings.action_items_escalation_role_list)
        return [
            person for person in sorted(people.values(), key=lambda member: member.display_name)
            if person.recipient_type == StakeholderRecipientType.PERSON and person.stakeholder_role in roles and self.notifications.recipient_address_for(person, "email")
        ]

    async def _email(self, application: Application, recipient: Stakeholder, notification_type: str, items: list[ActionItem], today: date, action_path: str, people: dict[str, Stakeholder]) -> None:
        language = recipient.preferred_language_code
        address = self.notifications.recipient_address_for(recipient, "email")
        assert address is not None
        lines = [self._line(item, language, today, people, show_owner=notification_type == "action_item_escalation") for item in sorted(items, key=lambda item: (item.due_on, item.item_title))]
        rendered = self.notifications.renderer.render_email(
            notification_type, language, application.application_name, application.application_name, facts=[(translate(language, "labels.application"), application.application_name)],
            body_markdown="\n".join(lines), action_path=action_path,
        )
        await self.notifications.queue_email(application.application_id, notification_type, address, rendered)

    @staticmethod
    def _line(item: ActionItem, language: str, today: date, people: dict[str, Stakeholder], *, show_owner: bool) -> str:
        parts = [f"**{item.item_title}**"]
        if item.incident_reference_text:
            parts.append(f"{translate(language, 'labels.incident')}: {item.incident_reference_text}")
        parts.append(f"{translate(language, 'labels.due')}: {item.due_on.isoformat() if item.due_on else ''}")
        overdue = days_overdue(item.item_status, item.due_on, today)
        if overdue:
            parts.append(f"{translate(language, 'labels.days_overdue')}: {overdue}")
        owner = people.get(item.owner_stakeholder_id or "")
        if show_owner:
            parts.append(f"{translate(language, 'labels.owner')}: {owner.display_name}" if owner else f"{translate(language, 'labels.owner_role')}: {item.suggested_owner_role_text or '-'}")
        return "- " + " · ".join(parts)

"""The daily action item reminders and the closed-item retention (spec 29, AC-14, AC-15)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder
from keigan.entities.status_values import ActionItemStatus
from keigan.services.action_item_reminders import ActionItemReminderService
from keigan.services.action_item_rules import local_today
from keigan.services.administration_service import AdministrationService
from keigan.utils.time_utils import utc_now
from support.application_graph import create_application_graph


async def an_application_with_people() -> tuple[str, str]:
    """An application in Tokyo whose team has an owner (a developer who reads Japanese), a lead and a manager; returns (application id, owner id)."""
    graph = await create_application_graph()
    async with open_session() as session:
        application = await session.get(Application, graph.application_id)
        application.time_zone_name = "Asia/Tokyo"
        people = {}
        for name, role, language in (("Owen Owner", "developer", "ja"), ("Lena Lead", "lead", "en"), ("Mia Manager", "manager", "en")):
            person = Stakeholder(application_id=graph.application_id, display_name=name, email_address=f"{name.split()[0].lower()}@example.com", stakeholder_role=role, preferred_language_code=language)
            session.add(person)
            people[role] = person
        await session.flush()
        return graph.application_id, people["developer"].stakeholder_id


async def add_item(application_id: str, *, due_in_days: int, owner_id: str | None, priority: str = "normal", status: str = ActionItemStatus.OPEN, title: str = "Item") -> str:
    async with open_session() as session:
        application = await session.get(Application, application_id)
        today = local_today(application.time_zone_name, utc_now())
        item = ActionItem(
            application_id=application_id, item_source_kind="manual", item_title=title, action_type="prevent", action_priority=priority, item_status=status, owner_stakeholder_id=owner_id,
            due_on=today + timedelta(days=due_in_days),
        )
        session.add(item)
        await session.flush()
        return item.action_item_id


async def emails_to(application_id: str) -> dict[str, NotificationDelivery]:
    async with open_session() as session:
        rows = (await session.scalars(select(NotificationDelivery).where(NotificationDelivery.application_id == application_id, NotificationDelivery.notification_type.like("action_item%")))).all()
        return {row.recipient_address: row for row in rows}


async def send(application_id: str) -> dict[str, int]:
    async with open_session() as session:
        return await ActionItemReminderService(session).send_due_reminders(application_id)


async def test_an_owner_gets_one_email_in_their_language_listing_what_is_due_soon_and_overdue(seed_context) -> None:
    application_id, owner_id = await an_application_with_people()
    await add_item(application_id, due_in_days=2, owner_id=owner_id, title="Soon item")
    await add_item(application_id, due_in_days=-1, owner_id=owner_id, title="Late item")
    await add_item(application_id, due_in_days=20, owner_id=owner_id, title="Far item")
    await add_item(application_id, due_in_days=-5, owner_id=owner_id, title="Done item", status=ActionItemStatus.DONE)
    assert await send(application_id) == {"owners": 1, "escalations": 0, "items": 2}
    email = (await emails_to(application_id))["owen@example.com"]
    assert email.notification_type == "action_item_reminder" and "Soon item" in email.body_text and "Late item" in email.body_text
    assert "Far item" not in email.body_text and "Done item" not in email.body_text
    assert "期限" in email.body_text  # the owner reads Japanese


async def test_a_second_run_the_same_day_sends_nothing(seed_context) -> None:
    application_id, owner_id = await an_application_with_people()
    await add_item(application_id, due_in_days=2, owner_id=owner_id)
    assert (await send(application_id))["items"] == 1
    assert await send(application_id) == {"owners": 0, "escalations": 0, "items": 0}
    assert len(await emails_to(application_id)) == 1


async def test_unowned_and_long_overdue_top_items_go_to_the_leads_and_managers(seed_context) -> None:
    application_id, owner_id = await an_application_with_people()
    await add_item(application_id, due_in_days=-1, owner_id=None, title="Nobody owns this")
    await add_item(application_id, due_in_days=-30, owner_id=owner_id, priority="top", title="Very late top item")
    await add_item(application_id, due_in_days=-30, owner_id=owner_id, priority="low", title="Very late low item")
    assert await send(application_id) == {"owners": 1, "escalations": 2, "items": 3}
    emails = await emails_to(application_id)
    lead_email = emails["lena@example.com"]
    assert lead_email.notification_type == "action_item_escalation" and emails["mia@example.com"].notification_type == "action_item_escalation"
    assert "Nobody owns this" in lead_email.body_text and "Very late top item" in lead_email.body_text and "Very late low item" not in lead_email.body_text
    assert "Owen Owner" in lead_email.body_text
    assert "Very late low item" in emails["owen@example.com"].body_text


async def test_nothing_is_sent_when_reminders_are_switched_off(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "action_items_reminders_enabled", False)
    application_id, owner_id = await an_application_with_people()
    await add_item(application_id, due_in_days=2, owner_id=owner_id)
    assert await send(application_id) == {"owners": 0, "escalations": 0, "items": 0} and not await emails_to(application_id)


async def test_closed_items_expire_after_the_retention_and_open_items_never_do(seed_context) -> None:
    application_id, owner_id = await an_application_with_people()
    closed_old = await add_item(application_id, due_in_days=1, owner_id=owner_id, status=ActionItemStatus.DONE)
    closed_recent = await add_item(application_id, due_in_days=1, owner_id=owner_id, status=ActionItemStatus.WONT_DO)
    still_open = await add_item(application_id, due_in_days=1, owner_id=owner_id)
    retention = get_settings().action_items_closed_retention_days
    async with open_session() as session:
        (await session.get(ActionItem, closed_old)).completed_at = utc_now() - timedelta(days=retention + 1)
        (await session.get(ActionItem, closed_recent)).completed_at = utc_now() - timedelta(days=5)
        (await session.get(ActionItem, still_open)).created_at = utc_now() - timedelta(days=retention * 2)
    async with open_session() as session:
        removed = await AdministrationService(session).run_retention_cleanup()
    assert removed["actionItems"] >= 1
    async with open_session() as session:
        assert await session.get(ActionItem, closed_old) is None
        assert await session.get(ActionItem, closed_recent) is not None and await session.get(ActionItem, still_open) is not None

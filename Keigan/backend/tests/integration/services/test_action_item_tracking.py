"""keigan/services/action_item_tracking_service.py: sending an action item to ServiceNow as a task, and reading the task back (spec 29, 4.7; roadmap D1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.status_values import ActionItemStatus, ExternalSyncStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException
from keigan.integrations.servicenow_client import ServiceNowClient
from keigan.integrations.simulation.servicenow_simulator import ServiceNowSimulator
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_reminders import ActionItemReminderService
from keigan.services.action_item_tracking_service import ActionItemTrackingService
from keigan.utils.time_utils import utc_now
from support import users
from support.application_graph import create_application_graph


@pytest.fixture(autouse=True)
def tracking_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "action_items_external_tracking_enabled", True)


async def an_item(application_id: str, *, status: str = ActionItemStatus.OPEN, source: str = "manual", incident_id: str | None = None, due_in_days: int = 10) -> str:
    async with open_session() as session:
        item = ActionItem(
            application_id=application_id, incident_id=incident_id, item_source_kind=source, item_title="Add an alert on pool saturation", item_details_markdown="At 80 percent.", action_type="detect",
            action_priority="high", item_status=status, due_on=(utc_now() + timedelta(days=due_in_days)).date(),
        )
        session.add(item)
        await session.flush()
        return item.action_item_id


def admin() -> CurrentUser:
    """A Keigan admin. A new object each time: the access check caches the user's roles on it."""
    return CurrentUser(user_principal_name="admin@example.com", display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


def outsider() -> CurrentUser:
    return CurrentUser(user_principal_name=users.NO_ACCESS, display_name="Noa", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=False)


async def sent(application_id: str, item_id: str, seed_context):
    async with open_session() as session:
        return await ActionItemTrackingService(session).send(admin(), item_id)


async def row(item_id: str) -> ActionItem:
    async with open_session() as session:
        return await session.get(ActionItem, item_id)


async def test_sending_an_item_creates_a_task_and_records_its_number_and_state(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    dto = await sent(graph.application_id, item_id, seed_context)
    stored = await row(item_id)
    assert stored.external_system == "servicenow" and stored.external_sync_status == ExternalSyncStatus.LINKED and stored.external_status_text == "Open" and stored.external_synced_at
    assert stored.external_record_identifier and stored.external_reference_text and stored.external_reference_text.startswith("TASK")
    assert dto.external is not None and dto.external.number == stored.external_reference_text and dto.external.sync_status == "linked" and dto.external.url and dto.can_send_external is False


async def test_the_task_has_the_items_title_priority_and_the_incident_number_and_nothing_from_the_postmortem(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    await sent(graph.application_id, item_id, seed_context)
    stored = await row(item_id)
    record = (await ServiceNowSimulator().read_tasks([stored.external_record_identifier]))[0]
    assert record["short_description"] == "Add an alert on pool saturation" and record["priority"] == "2" and "At 80 percent." in record["description"]


async def test_nothing_is_sent_while_tracking_is_switched_off(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "action_items_external_tracking_enabled", False)
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    with pytest.raises(BusinessValidationException, match="switched off"):
        await sent(graph.application_id, item_id, seed_context)
    assert (await row(item_id)).external_sync_status is None


@pytest.mark.parametrize("status", [ActionItemStatus.PROPOSED, ActionItemStatus.DONE, ActionItemStatus.WONT_DO])
async def test_only_a_tracked_item_can_be_sent(seed_context, status: str) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id, status=status)
    with pytest.raises(BusinessValidationException, match="tracked"):
        await sent(graph.application_id, item_id, seed_context)


async def test_an_item_that_is_already_linked_is_not_sent_again(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    await sent(graph.application_id, item_id, seed_context)
    with pytest.raises(BusinessValidationException, match="already tracked"):
        await sent(graph.application_id, item_id, seed_context)


async def test_a_person_who_cannot_edit_the_application_cannot_send(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    async with open_session() as session:
        with pytest.raises(ForbiddenException):
            await ActionItemTrackingService(session).send(outsider(), item_id)


async def test_a_failed_send_is_recorded_and_can_be_tried_again(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.exceptions.keigan_exceptions import IntegrationException

    async def refuse(self: ServiceNowClient, table: str, task_fields: dict) -> dict:
        raise IntegrationException("ServiceNow returned 503: boom with a secret-looking detail")

    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    with monkeypatch.context() as broken:
        broken.setattr(ServiceNowClient, "create_task", refuse)
        dto = await sent(graph.application_id, item_id, seed_context)
    assert dto.external is not None and dto.external.sync_status == "failed" and dto.can_send_external is True and "boom" not in dto.model_dump_json()
    assert (await row(item_id)).external_record_identifier is None
    again = await sent(graph.application_id, item_id, seed_context)
    assert again.external is not None and again.external.sync_status == "linked"


async def sync(application_id: str) -> dict[str, int]:
    async with open_session() as session:
        return await ActionItemTrackingService(session).sync_application(application_id)


async def test_a_sync_mirrors_the_tasks_state_and_leaves_the_item_alone_while_the_task_is_open(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id, status=ActionItemStatus.IN_PROGRESS)
    await sent(graph.application_id, item_id, seed_context)
    record = (await ServiceNowSimulator().read_tasks([(await row(item_id)).external_record_identifier]))[0]
    await ServiceNowSimulator().update_task(record["sys_id"], {"state": "Work in Progress"})
    assert await sync(graph.application_id) == {"checked": 1, "changed": 0, "missing": 0}
    stored = await row(item_id)
    assert stored.external_status_text == "Work in Progress" and stored.item_status == ActionItemStatus.IN_PROGRESS


async def test_closing_the_task_in_servicenow_finishes_the_item_and_stops_its_reminders(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id, due_in_days=1)
    await sent(graph.application_id, item_id, seed_context)
    await ServiceNowSimulator().update_task((await row(item_id)).external_record_identifier, {"state": "Closed Complete"})
    assert await sync(graph.application_id) == {"checked": 1, "changed": 1, "missing": 0}
    stored = await row(item_id)
    assert stored.item_status == ActionItemStatus.DONE and stored.completed_at is not None and stored.completed_by_user_principal_name == "servicenow" and stored.external_status_text == "Closed Complete"


async def test_a_task_closed_without_being_done_becomes_wont_do_with_the_reason(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    await sent(graph.application_id, item_id, seed_context)
    await ServiceNowSimulator().update_task((await row(item_id)).external_record_identifier, {"state": "Closed Skipped"})
    await sync(graph.application_id)
    stored = await row(item_id)
    assert stored.item_status == ActionItemStatus.WONT_DO and "ServiceNow" in (stored.status_reason_text or "")


async def test_a_reopened_task_reopens_the_item(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    await sent(graph.application_id, item_id, seed_context)
    identifier = (await row(item_id)).external_record_identifier
    await ServiceNowSimulator().update_task(identifier, {"state": "Closed Complete"})
    await sync(graph.application_id)
    await ServiceNowSimulator().update_task(identifier, {"state": "Open"})
    await sync(graph.application_id)
    stored = await row(item_id)
    assert stored.item_status == ActionItemStatus.OPEN and stored.completed_at is None and stored.status_reason_text is None


async def test_a_task_deleted_in_servicenow_is_reported_and_the_item_is_not_changed(seed_context) -> None:
    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    await sent(graph.application_id, item_id, seed_context)
    async with open_session() as session:
        stored = await session.get(ActionItem, item_id)
        stored.external_record_identifier = "f" * 32  # a task that does not exist
    assert await sync(graph.application_id) == {"checked": 1, "changed": 0, "missing": 1}
    stored = await row(item_id)
    assert stored.item_status == ActionItemStatus.OPEN and stored.external_status_text == "Not found in ServiceNow"


async def test_a_sync_reads_only_linked_items_of_the_application(seed_context) -> None:
    graph = await create_application_graph()
    await an_item(graph.application_id)  # never sent
    assert await sync(graph.application_id) == {"checked": 0, "changed": 0, "missing": 0}


async def test_a_linked_item_gets_no_reminders_from_keigan(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        application = await session.get(Application, graph.application_id)
        application.time_zone_name = "Asia/Tokyo"
    item_id = await an_item(graph.application_id, due_in_days=1)
    await sent(graph.application_id, item_id, seed_context)
    async with open_session() as session:
        result = await ActionItemReminderService(session).send_due_reminders(graph.application_id)
    assert result["items"] == 0
    assert (await row(item_id)).last_reminded_at is None


async def test_sending_is_audited(seed_context) -> None:
    from keigan.entities.platform_entities import AuditEvent

    graph = await create_application_graph()
    item_id = await an_item(graph.application_id)
    await sent(graph.application_id, item_id, seed_context)
    async with open_session() as session:
        actions = (await session.scalars(select(AuditEvent.action_name).where(AuditEvent.target_entity_id == item_id))).all()
    assert "action_item.external_send" in actions

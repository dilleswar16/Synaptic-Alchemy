"""The check that queues a ServiceNow task read for each application that has action items tracked there (roadmap D1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import IntegrationMode, get_settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.platform_entities import BackgroundJob
from keigan.entities.status_values import ActionItemStatus, ApplicationLifecycleStatus, ExternalSyncStatus
from keigan.utils.time_utils import utc_now
from keigan.workers.job_handlers import JOB_HANDLER_REFERENCES
from keigan.workers.schedulers import build_schedules, enqueue_action_item_task_syncs
from support.application_graph import create_application_graph


async def a_live_application(sync_status: str | None) -> str:
    graph = await create_application_graph()
    async with open_session() as session:
        (await session.get(Application, graph.application_id)).lifecycle_status = ApplicationLifecycleStatus.LIVE
        session.add(ActionItem(
            application_id=graph.application_id, item_source_kind="manual", item_title="Tracked item", action_type="prevent", item_status=ActionItemStatus.OPEN,
            due_on=(utc_now() + timedelta(days=5)).date(), external_system="servicenow" if sync_status else None, external_sync_status=sync_status, external_record_identifier="a" * 32 if sync_status else None,
        ))
    return graph.application_id


async def queued_for(application_id: str) -> list[BackgroundJob]:
    async with open_session() as session:
        jobs = (await session.scalars(select(BackgroundJob).where(BackgroundJob.job_type == "sync_action_item_tasks"))).all()
        return [job for job in jobs if job.job_payload_json.get("application_id") == application_id]


async def run_check() -> None:
    async with open_session() as session:
        await enqueue_action_item_task_syncs(session)


async def test_an_application_with_a_linked_item_is_queued_once_and_one_without_is_not(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "action_items_external_tracking_enabled", True)
    linked, not_sent, failed = await a_live_application(ExternalSyncStatus.LINKED), await a_live_application(None), await a_live_application(ExternalSyncStatus.FAILED)
    await run_check()
    await run_check()
    assert len(await queued_for(linked)) == 1 and not await queued_for(not_sent) and not await queued_for(failed)


async def test_nothing_is_queued_while_tracking_is_off_or_servicenow_is_disabled(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    application_id = await a_live_application(ExternalSyncStatus.LINKED)
    await run_check()  # tracking is off by default
    assert not await queued_for(application_id)
    monkeypatch.setattr(get_settings(), "action_items_external_tracking_enabled", True)
    monkeypatch.setattr(get_settings(), "servicenow_mode", IntegrationMode.DISABLED)
    await run_check()
    assert not await queued_for(application_id)


def test_the_job_has_a_handler_and_a_schedule() -> None:
    assert "sync_action_item_tasks" in JOB_HANDLER_REFERENCES
    assert "action_item_task_sync" in {schedule.schedule_name for schedule in build_schedules()}

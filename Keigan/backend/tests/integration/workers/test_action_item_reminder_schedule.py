"""The hourly check that queues one reminder job per application per local day (spec 29, AC-14)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.application_entities import Application
from keigan.entities.platform_entities import BackgroundJob
from keigan.entities.status_values import ApplicationLifecycleStatus
from keigan.workers.schedulers import enqueue_action_item_reminders
from support.application_graph import create_application_graph


async def reminder_jobs_for(application_id: str) -> list[BackgroundJob]:
    async with open_session() as session:
        jobs = (await session.scalars(select(BackgroundJob).where(BackgroundJob.job_type == "send_action_item_reminders"))).all()
        return [job for job in jobs if job.job_payload_json.get("application_id") == application_id]


async def a_live_application_in(time_zone_name: str) -> str:
    graph = await create_application_graph()
    async with open_session() as session:
        application = await session.get(Application, graph.application_id)
        application.time_zone_name, application.lifecycle_status = time_zone_name, ApplicationLifecycleStatus.LIVE
    return graph.application_id


async def run_check() -> None:
    async with open_session() as session:
        await enqueue_action_item_reminders(session)


async def test_only_an_application_whose_local_hour_is_the_reminder_hour_is_queued_and_only_once(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    tokyo_hour = datetime.now(UTC).astimezone(ZoneInfo("Asia/Tokyo")).hour
    monkeypatch.setattr(get_settings(), "action_items_reminder_hour_local", tokyo_hour)
    in_tokyo, in_new_york = await a_live_application_in("Asia/Tokyo"), await a_live_application_in("America/New_York")
    await run_check()
    await run_check()  # a second check in the same hour, or a second worker, queues nothing more
    assert len(await reminder_jobs_for(in_tokyo)) == 1
    assert not await reminder_jobs_for(in_new_york)


async def test_nothing_is_queued_when_reminders_are_switched_off(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    tokyo_hour = datetime.now(UTC).astimezone(ZoneInfo("Asia/Tokyo")).hour
    monkeypatch.setattr(get_settings(), "action_items_reminder_hour_local", tokyo_hour)
    monkeypatch.setattr(get_settings(), "action_items_reminders_enabled", False)
    application_id = await a_live_application_in("Asia/Tokyo")
    await run_check()
    assert not await reminder_jobs_for(application_id)

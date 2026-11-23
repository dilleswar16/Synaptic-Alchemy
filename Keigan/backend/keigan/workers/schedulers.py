"""Interval schedules that enqueue recurring jobs (ServiceNow polling, SLI collection, predictions, Teams polling, reports)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.database_config import open_session
from keigan.config.settings import IntegrationMode, get_settings
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import ServiceNowAssignmentGroup
from keigan.entities.notification_entities import TeamsIncidentChat
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective
from keigan.entities.status_values import ApplicationLifecycleStatus, ExternalSyncStatus, IntelligenceReportType, TeamsChatStatus
from keigan.services.action_item_rules import local_now
from keigan.services.error_budget_policy_service import enqueue_error_budget_evaluation
from keigan.workers.job_queue import JobQueue

logger = logging.getLogger(__name__)

ScheduleAction = Callable[[AsyncSession], Awaitable[None]]


@dataclass
class IntervalSchedule:
    schedule_name: str
    interval_seconds: float
    action: ScheduleAction
    last_run_monotonic: float = -1e12


async def _live_application_ids(session: AsyncSession) -> list[str]:
    return list((await session.scalars(select(Application.application_id).where(Application.lifecycle_status == ApplicationLifecycleStatus.LIVE))).all())


async def enqueue_servicenow_polls(session: AsyncSession) -> None:
    if get_settings().servicenow_mode == IntegrationMode.DISABLED:
        return
    application_ids_with_groups = set((await session.scalars(select(ServiceNowAssignmentGroup.application_id).distinct())).all())
    for application_id in await _live_application_ids(session):
        if application_id in application_ids_with_groups:
            await JobQueue(session).enqueue("poll_servicenow", {"application_id": application_id}, deduplication_key=f"poll_servicenow:{application_id}", priority_number=20)


async def enqueue_action_item_task_syncs(session: AsyncSession) -> None:
    """Reads the ServiceNow tasks of the applications that have action items tracked there (only while tracking is on and ServiceNow is not disabled)."""
    settings = get_settings()
    if not settings.action_items_external_tracking_enabled or settings.servicenow_mode == IntegrationMode.DISABLED:
        return
    application_ids_with_linked_items = set((await session.scalars(select(ActionItem.application_id).where(ActionItem.external_sync_status == ExternalSyncStatus.LINKED).distinct())).all())
    for application_id in await _live_application_ids(session):
        if application_id in application_ids_with_linked_items:
            await JobQueue(session).enqueue("sync_action_item_tasks", {"application_id": application_id}, deduplication_key=f"sync_action_item_tasks:{application_id}", priority_number=25)


async def enqueue_sli_collection(session: AsyncSession) -> None:
    application_ids_with_slis = set((await session.scalars(select(ServiceLevelIndicator.application_id).distinct())).all())
    for application_id in await _live_application_ids(session):
        if application_id in application_ids_with_slis:
            await JobQueue(session).enqueue("collect_sli_measurements", {"application_id": application_id}, deduplication_key=f"collect_sli:{application_id}", priority_number=60)
            await JobQueue(session).enqueue("evaluate_burn_rates", {"application_id": application_id}, deduplication_key=f"burn_rates:{application_id}", priority_number=61)


async def enqueue_predictive_analysis(session: AsyncSession) -> None:
    for application_id in await _live_application_ids(session):
        await JobQueue(session).enqueue("run_predictive_analysis", {"application_id": application_id}, deduplication_key=f"predictive:{application_id}", priority_number=120)


async def enqueue_teams_chat_polls(session: AsyncSession) -> None:
    if get_settings().teams_mode == IntegrationMode.DISABLED:
        return
    active_chat_ids = (await session.scalars(select(TeamsIncidentChat.teams_incident_chat_id).where(TeamsIncidentChat.chat_status == TeamsChatStatus.ACTIVE))).all()
    for teams_incident_chat_id in active_chat_ids:
        await JobQueue(session).enqueue(
            "poll_incident_chat", {"teams_incident_chat_id": teams_incident_chat_id}, deduplication_key=f"poll_chat:{teams_incident_chat_id}", priority_number=40
        )


async def enqueue_weekly_reports(session: AsyncSession) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    if now.weekday() != settings.intelligence_weekly_report_weekday or now.hour != settings.intelligence_weekly_report_hour:
        return
    iso_year, iso_week, _ = now.isocalendar()
    for application_id in await _live_application_ids(session):
        await JobQueue(session).enqueue(
            "send_intelligence_report", {"application_id": application_id, "report_type": IntelligenceReportType.WEEKLY_DIGEST}, deduplication_key=f"weekly_report:{application_id}:{iso_year}-{iso_week}"
        )
        await JobQueue(session).enqueue("weekly_noise_report", {"application_id": application_id}, deduplication_key=f"noise_report:{application_id}:{iso_year}-{iso_week}")


async def enqueue_action_item_reminders(session: AsyncSession) -> None:
    """Hourly: an application whose local hour is the reminder hour gets one reminder job for its local day (the deduplication key makes a second check or a second worker do nothing)."""
    settings = get_settings()
    if not settings.action_items_reminders_enabled:
        return
    now = datetime.now(UTC)
    for application_id, time_zone_name in (await session.execute(select(Application.application_id, Application.time_zone_name).where(Application.lifecycle_status == ApplicationLifecycleStatus.LIVE))).all():
        local_moment = local_now(time_zone_name, now)
        if local_moment.hour == settings.action_items_reminder_hour_local:
            await JobQueue(session).enqueue(
                "send_action_item_reminders", {"application_id": application_id}, deduplication_key=f"action_item_reminders:{application_id}:{local_moment.date().isoformat()}", priority_number=90
            )


async def enqueue_error_budget_policy(session: AsyncSession) -> None:
    """Every evaluation interval: live applications that have an SLO get their incident budget impacts and policy breaches re-evaluated."""
    application_ids_with_slos = set((await session.scalars(select(ServiceLevelObjective.application_id).distinct())).all())
    for application_id in await _live_application_ids(session):
        if application_id in application_ids_with_slos:
            await enqueue_error_budget_evaluation(session, application_id)


async def enqueue_retention_cleanup(session: AsyncSession) -> None:
    await JobQueue(session).enqueue("retention_cleanup", {}, deduplication_key=f"retention:{datetime.now(UTC).date().isoformat()}", priority_number=200)


def build_schedules() -> list[IntervalSchedule]:
    settings = get_settings()
    return [
        IntervalSchedule("servicenow_poll", settings.servicenow_poll_interval_seconds, enqueue_servicenow_polls),
        IntervalSchedule("action_item_task_sync", settings.servicenow_poll_interval_seconds, enqueue_action_item_task_syncs),
        IntervalSchedule("sli_collection", settings.sli_collection_interval_minutes * 60, enqueue_sli_collection),
        IntervalSchedule("predictive_analysis", settings.predictive_analysis_interval_minutes * 60, enqueue_predictive_analysis),
        IntervalSchedule("teams_chat_poll", settings.teams_chat_poll_interval_minutes * 60, enqueue_teams_chat_polls),
        IntervalSchedule("weekly_reports", 3600, enqueue_weekly_reports),
        IntervalSchedule("action_item_reminders", 3600, enqueue_action_item_reminders),
        IntervalSchedule("error_budget_policy", settings.error_budget_policy_evaluation_interval_minutes * 60, enqueue_error_budget_policy),
        IntervalSchedule("retention_cleanup", 86400, enqueue_retention_cleanup),
    ]


class Scheduler:
    def __init__(self) -> None:
        self.schedules = build_schedules()
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        logger.info("Scheduler started with %s schedules", len(self.schedules))
        while not self._stop_event.is_set():
            loop_time = asyncio.get_running_loop().time()
            for interval_schedule in self.schedules:
                if loop_time - interval_schedule.last_run_monotonic < interval_schedule.interval_seconds:
                    continue
                interval_schedule.last_run_monotonic = loop_time
                try:
                    async with open_session() as session:
                        await interval_schedule.action(session)
                except Exception:  # noqa: BLE001
                    logger.exception("Schedule %s failed", interval_schedule.schedule_name)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=10)
            except TimeoutError:
                pass

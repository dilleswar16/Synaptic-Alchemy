"""Database-backed job queue with leases, retries, back-off and dead-lettering.

``JobQueue.enqueue`` is used by services and schedulers; :class:`JobWorker` runs in the worker process (or inside
the API process locally) and executes handlers from ``workers/job_handlers.py``. Handlers must be idempotent.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.database_config import open_session
from keigan.config.logging_config import set_correlation_id
from keigan.config.settings import get_settings
from keigan.entities.platform_entities import BackgroundJob, PlatformSetting

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = ("queued", "running")
LEASE_DURATION = timedelta(minutes=10)
WORKER_HEARTBEAT_SETTING_KEY = "worker_heartbeat"


class JobQueue:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue(
        self,
        job_type: str,
        job_payload: dict[str, Any] | None = None,
        *,
        deduplication_key: str | None = None,
        available_at: datetime | None = None,
        priority_number: int = 100,
        maximum_attempt_count: int = 3,
    ) -> str:
        """Add a job. If a queued/running job with the same deduplication key exists, return its id instead."""
        if deduplication_key:
            existing_job = await self.session.scalar(
                select(BackgroundJob).where(BackgroundJob.deduplication_key == deduplication_key, BackgroundJob.job_status.in_(ACTIVE_JOB_STATUSES)).limit(1)
            )
            if existing_job is not None:
                return existing_job.background_job_id
        background_job = BackgroundJob(
            job_type=job_type,
            job_payload_json=job_payload or {},
            deduplication_key=deduplication_key,
            available_at=available_at or datetime.now(UTC),
            priority_number=priority_number,
            maximum_attempt_count=maximum_attempt_count,
        )
        self.session.add(background_job)
        await self.session.flush()
        return background_job.background_job_id


class JobWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._stop_event = asyncio.Event()
        self._concurrency_limiter = asyncio.Semaphore(self.settings.worker_concurrency)
        self._running_tasks: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        logger.info("Job worker %s started (concurrency %s)", self.settings.worker_name, self.settings.worker_concurrency)
        last_heartbeat_at = 0.0
        while not self._stop_event.is_set():
            try:
                loop_time = asyncio.get_running_loop().time()
                if loop_time - last_heartbeat_at > 30:
                    await self._write_heartbeat_and_recover_leases()
                    last_heartbeat_at = loop_time
                leased_job_id = await self._lease_next_job() if not self._concurrency_limiter.locked() else None
                if leased_job_id:
                    await self._concurrency_limiter.acquire()
                    job_task = asyncio.create_task(self._execute_job(leased_job_id))
                    self._running_tasks.add(job_task)
                    job_task.add_done_callback(self._running_tasks.discard)
                    continue
            except Exception:  # noqa: BLE001 — the loop must survive any single failure
                logger.exception("Job worker loop error")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.settings.worker_poll_interval_seconds)
            except TimeoutError:
                pass
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)

    async def _lease_next_job(self) -> str | None:
        now = datetime.now(UTC)
        async with open_session() as session:
            candidate_statement = (
                select(BackgroundJob)
                .where(BackgroundJob.job_status == "queued", BackgroundJob.available_at <= now)
                .order_by(BackgroundJob.priority_number, BackgroundJob.available_at)
                .limit(1)
            )
            if not self.settings.uses_sqlite:
                candidate_statement = candidate_statement.with_for_update(skip_locked=True)
            candidate_job = await session.scalar(candidate_statement)
            if candidate_job is None:
                return None
            candidate_job.job_status = "running"
            candidate_job.leased_by_worker_name = self.settings.worker_name
            candidate_job.lease_expires_at = now + LEASE_DURATION
            candidate_job.started_at = now
            candidate_job.attempt_count += 1
            return candidate_job.background_job_id

    async def _execute_job(self, background_job_id: str) -> None:
        from keigan.workers.job_handlers import execute_job_handler

        try:
            async with open_session() as session:
                background_job = await session.get(BackgroundJob, background_job_id)
                if background_job is None:
                    return
                job_type, job_payload = background_job.job_type, dict(background_job.job_payload_json or {})
            set_correlation_id(f"job-{background_job_id[:12]}")
            try:
                job_result = await execute_job_handler(job_type, job_payload)
            except Exception as job_error:  # noqa: BLE001
                await self._record_failure(background_job_id, job_error)
                return
            async with open_session() as session:
                background_job = await session.get(BackgroundJob, background_job_id)
                if background_job is not None:
                    background_job.job_status = "succeeded"
                    background_job.finished_at = datetime.now(UTC)
                    background_job.result_summary_json = job_result if isinstance(job_result, dict) else None
        finally:
            self._concurrency_limiter.release()

    async def _record_failure(self, background_job_id: str, job_error: Exception) -> None:
        async with open_session() as session:
            background_job = await session.get(BackgroundJob, background_job_id)
            if background_job is None:
                return
            error_message = f"{type(job_error).__name__}: {str(job_error)[:1500]}"
            background_job.last_error_message = error_message
            if isinstance(job_error, NotImplementedError) or background_job.attempt_count >= background_job.maximum_attempt_count:
                background_job.job_status = "dead_lettered"
                background_job.finished_at = datetime.now(UTC)
                logger.error("Job %s (%s) dead-lettered: %s", background_job_id, background_job.job_type, error_message)
            else:
                background_job.job_status = "queued"
                background_job.available_at = datetime.now(UTC) + timedelta(seconds=15 * 2 ** background_job.attempt_count)
                logger.warning("Job %s (%s) failed, retry %s scheduled: %s", background_job_id, background_job.job_type, background_job.attempt_count, error_message)

    async def _write_heartbeat_and_recover_leases(self) -> None:
        now = datetime.now(UTC)
        async with open_session() as session:
            await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.job_status == "running", BackgroundJob.lease_expires_at < now)
                .values(job_status="queued", leased_by_worker_name=None, available_at=now)
            )
            heartbeat_setting = await session.get(PlatformSetting, WORKER_HEARTBEAT_SETTING_KEY)
            heartbeat_value = {"workerName": self.settings.worker_name, "heartbeatAt": now.isoformat()}
            if heartbeat_setting is None:
                session.add(PlatformSetting(setting_key=WORKER_HEARTBEAT_SETTING_KEY, setting_value_json=heartbeat_value, setting_description="Last worker heartbeat"))
            else:
                heartbeat_setting.setting_value_json = heartbeat_value

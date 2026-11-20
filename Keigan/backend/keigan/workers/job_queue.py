"""Database-backed job queue with leases, retries, back-off and dead-lettering.

``JobQueue.enqueue`` is used by services and schedulers; :class:`JobWorker` runs in the worker process (or inside
the API process locally) and executes handlers from ``workers/job_handlers.py``. Handlers must be idempotent.

Several worker pods share one database, so correctness rests on the database, not on process memory:
- one active job per deduplication key is a filtered unique index (``uq_background_job_active_deduplication_key``);
- a job is leased with one guarded ``UPDATE ... WHERE job_status = 'queued'`` (works on SQLite, SQL Server and PostgreSQL);
- a running job renews its lease, so a long handler is never started a second time.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Update, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.database_config import open_session
from keigan.config.logging_config import set_correlation_id
from keigan.config.settings import get_settings
from keigan.entities.platform_entities import ACTIVE_JOB_STATUSES, BackgroundJob, PlatformSetting
from keigan.workers.worker_settings import WorkerSettings, get_worker_settings
from keigan.entities.status_values import JobStatus

logger = logging.getLogger(__name__)

WORKER_HEARTBEAT_SETTING_KEY = "worker_heartbeat"
ENQUEUE_ATTEMPTS = 3  # a winning job that finishes between our two statements frees its key again, so the insert is tried once more
LEASE_CLAIM_ATTEMPTS = 5  # each lost claim means another worker took that job, so the next candidate is tried straight away


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
        """Add a job. If a queued/running job with the same deduplication key exists, return its id instead.

        The database enforces the rule, so two pods enqueuing the same key at the same moment still create one job:
        the loser's insert is rejected by the unique index and the winner's id is returned.
        """
        def new_job() -> BackgroundJob:
            return BackgroundJob(
                job_type=job_type, job_payload_json=job_payload or {}, deduplication_key=deduplication_key, available_at=available_at or datetime.now(UTC),
                priority_number=priority_number, maximum_attempt_count=maximum_attempt_count,
            )

        if not deduplication_key:
            background_job = new_job()
            self.session.add(background_job)
            await self.session.flush()
            return background_job.background_job_id
        for attempt_number in range(1, ENQUEUE_ATTEMPTS + 1):
            existing_job_id = await self._find_active_job(deduplication_key)
            if existing_job_id is not None:
                return existing_job_id
            background_job = new_job()
            try:
                async with self.session.begin_nested():  # a SAVEPOINT: only the failed insert is undone, not the caller's work
                    self.session.add(background_job)
                    await self.session.flush()
                return background_job.background_job_id
            except IntegrityError:
                logger.info("Job with deduplication key %s was queued by another worker at the same moment (attempt %s)", deduplication_key, attempt_number)
                if attempt_number == ENQUEUE_ATTEMPTS:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover - the loop returns or raises

    async def _find_active_job(self, deduplication_key: str) -> str | None:
        return await self.session.scalar(
            select(BackgroundJob.background_job_id).where(BackgroundJob.deduplication_key == deduplication_key, BackgroundJob.job_status.in_(ACTIVE_JOB_STATUSES)).limit(1)
        )


class JobWorker:
    def __init__(self, worker_settings: WorkerSettings | None = None) -> None:
        self.settings = get_settings()
        self.worker_settings = worker_settings or get_worker_settings()
        self._stop_event = asyncio.Event()
        self._concurrency_limiter = asyncio.Semaphore(self.settings.worker_concurrency)
        self._running_tasks: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        logger.info("Job worker %s started (concurrency %s)", self.settings.worker_name, self.settings.worker_concurrency)
        last_heartbeat_at = float("-inf")
        while not self._stop_event.is_set():
            try:
                loop_time = asyncio.get_running_loop().time()
                if loop_time - last_heartbeat_at > self.worker_settings.worker_heartbeat_interval_seconds:
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

    @staticmethod
    def _build_claim_statement(background_job_id: str, worker_name: str, now: datetime, lease_duration: timedelta) -> Update:
        """Take a job for this worker, but only if it is still queued: the guard is what makes two workers unable to run one job.

        SQL Server ignores SQLAlchemy's ``with_for_update(skip_locked=True)`` (no UPDLOCK/READPAST hint is rendered), so the
        lease must not depend on row locks. The caller checks that exactly one row was updated.
        """
        return (
            update(BackgroundJob)
            .where(BackgroundJob.background_job_id == background_job_id, BackgroundJob.job_status == JobStatus.QUEUED)
            .values(job_status=JobStatus.RUNNING, leased_by_worker_name=worker_name, lease_expires_at=now + lease_duration, started_at=now, attempt_count=BackgroundJob.attempt_count + 1)
            .execution_options(synchronize_session=False)
        )

    async def _lease_next_job(self) -> str | None:
        for _ in range(LEASE_CLAIM_ATTEMPTS):
            now = datetime.now(UTC)
            async with open_session() as session:
                candidate_job_id = await session.scalar(
                    select(BackgroundJob.background_job_id)
                    .where(BackgroundJob.job_status == JobStatus.QUEUED, BackgroundJob.available_at <= now)
                    .order_by(BackgroundJob.priority_number, BackgroundJob.available_at)
                    .limit(1)
                )
                if candidate_job_id is None:
                    return None
                claim_result = await session.execute(
                    self._build_claim_statement(candidate_job_id, self.settings.worker_name, now, timedelta(seconds=self.worker_settings.job_lease_duration_seconds))
                )
                if claim_result.rowcount == 1:
                    return candidate_job_id
            logger.debug("Job %s was leased by another worker first; trying the next one", candidate_job_id)
        return None

    async def _renew_lease(self, background_job_id: str) -> bool:
        """Push the lease of a job this worker is running forward. False means the lease is gone (the job was re-queued or finished elsewhere)."""
        new_expiry = datetime.now(UTC) + timedelta(seconds=self.worker_settings.job_lease_duration_seconds)
        async with open_session() as session:
            renewal_result = await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.background_job_id == background_job_id, BackgroundJob.job_status == JobStatus.RUNNING, BackgroundJob.leased_by_worker_name == self.settings.worker_name)
                .values(lease_expires_at=new_expiry)
                .execution_options(synchronize_session=False)
            )
            return renewal_result.rowcount == 1

    async def _keep_lease_alive(self, background_job_id: str) -> None:
        """Renew the lease on a fixed interval until cancelled, so recovery never mistakes a long-running job for a dead one."""
        while True:
            await asyncio.sleep(self.worker_settings.job_lease_renewal_interval_seconds)
            try:
                if not await self._renew_lease(background_job_id):
                    logger.warning("Job %s lost its lease while running; another worker may run it again (handlers are idempotent)", background_job_id)
                    return
            except Exception:  # noqa: BLE001 — a database hiccup must not stop the handler; the lease has room for a missed renewal
                logger.warning("Could not renew the lease of job %s; will retry", background_job_id, exc_info=True)

    async def _run_handler_while_renewing_lease(self, background_job_id: str, job_type: str, job_payload: dict[str, Any]) -> Any:
        from keigan.workers.job_handlers import execute_job_handler

        lease_renewal_task = asyncio.create_task(self._keep_lease_alive(background_job_id))
        try:
            return await execute_job_handler(job_type, job_payload)
        finally:
            lease_renewal_task.cancel()
            await asyncio.gather(lease_renewal_task, return_exceptions=True)

    async def _execute_job(self, background_job_id: str) -> None:
        try:
            async with open_session() as session:
                background_job = await session.get(BackgroundJob, background_job_id)
                if background_job is None:
                    return
                job_type, job_payload = background_job.job_type, dict(background_job.job_payload_json or {})
            set_correlation_id(f"job-{background_job_id[:12]}")
            try:
                job_result = await self._run_handler_while_renewing_lease(background_job_id, job_type, job_payload)
            except Exception as job_error:  # noqa: BLE001
                await self._record_failure(background_job_id, job_error)
                return
            async with open_session() as session:
                background_job = await session.get(BackgroundJob, background_job_id)
                if background_job is not None:
                    background_job.job_status = JobStatus.SUCCEEDED
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
                background_job.job_status = JobStatus.DEAD_LETTERED
                background_job.finished_at = datetime.now(UTC)
                logger.error("Job %s (%s) dead-lettered: %s", background_job_id, background_job.job_type, error_message)
            else:
                background_job.job_status = JobStatus.QUEUED
                background_job.available_at = datetime.now(UTC) + timedelta(seconds=15 * 2 ** background_job.attempt_count)
                logger.warning("Job %s (%s) failed, retry %s scheduled: %s", background_job_id, background_job.job_type, background_job.attempt_count, error_message)

    async def _write_heartbeat_and_recover_leases(self) -> None:
        """Record that this worker is alive and re-queue running jobs whose lease expired (their worker died).

        A job whose worker is alive keeps renewing ``lease_expires_at`` (see ``_keep_lease_alive``), so it never matches here.
        """
        now = datetime.now(UTC)
        async with open_session() as session:
            await session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.job_status == JobStatus.RUNNING, BackgroundJob.lease_expires_at < now)
                .values(job_status=JobStatus.QUEUED, leased_by_worker_name=None, available_at=now)
            )
            heartbeat_setting = await session.get(PlatformSetting, WORKER_HEARTBEAT_SETTING_KEY)
            heartbeat_value = {"workerName": self.settings.worker_name, "heartbeatAt": now.isoformat()}
            if heartbeat_setting is None:
                session.add(PlatformSetting(setting_key=WORKER_HEARTBEAT_SETTING_KEY, setting_value_json=heartbeat_value, setting_description="Last worker heartbeat"))
            else:
                heartbeat_setting.setting_value_json = heartbeat_value

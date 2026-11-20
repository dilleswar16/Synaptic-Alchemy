"""keigan/workers/job_queue.py: deduplication, failure handling and lease recovery."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.entities.platform_entities import BackgroundJob
from keigan.workers.job_queue import JobQueue, JobWorker

NOT_BEFORE_TOMORROW = datetime.now(UTC) + timedelta(days=1)  # keeps test jobs out of drain_jobs()


async def _enqueue(job_type: str, **options: object) -> str:
    async with open_session() as session:
        return await JobQueue(session).enqueue(job_type, {}, **options)  # type: ignore[arg-type]


async def test_enqueue_with_an_active_deduplication_key_returns_the_existing_job(seed_context) -> None:
    key = f"test-dedup:{uuid.uuid4()}"
    first_job_id = await _enqueue("retention_cleanup", deduplication_key=key, available_at=NOT_BEFORE_TOMORROW)
    second_job_id = await _enqueue("retention_cleanup", deduplication_key=key)
    assert second_job_id == first_job_id


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="H4: dedup is check-then-insert, so two concurrent transactions both insert")
async def test_concurrent_enqueue_with_one_key_keeps_one_active_job(seed_context) -> None:
    key = f"test-race:{uuid.uuid4()}"
    try:
        async with open_session() as first_session, open_session() as second_session:
            await JobQueue(first_session).enqueue("retention_cleanup", {}, deduplication_key=key, available_at=NOT_BEFORE_TOMORROW)
            await JobQueue(second_session).enqueue("retention_cleanup", {}, deduplication_key=key, available_at=NOT_BEFORE_TOMORROW)
    except Exception:  # noqa: BLE001 — a constraint violation on the second commit is the desired outcome
        pass
    async with open_session() as session:
        job_count = await session.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.deduplication_key == key))
    assert job_count == 1, f"{job_count} active jobs share one deduplication key"


async def test_unknown_job_type_is_dead_lettered_without_retries(seed_context) -> None:
    job_id = await _enqueue("no_such_job_type", maximum_attempt_count=3, available_at=NOT_BEFORE_TOMORROW)
    worker = JobWorker()
    await worker._concurrency_limiter.acquire()  # _execute_job releases it
    await worker._execute_job(job_id)
    async with open_session() as session:
        job = await session.get(BackgroundJob, job_id)
    assert job is not None
    assert job.job_status == "dead_lettered"
    assert job.last_error_message.startswith("NotImplementedError")


async def test_failed_attempt_below_the_limit_is_requeued_with_back_off(seed_context) -> None:
    job_id = await _enqueue("retention_cleanup", maximum_attempt_count=3, available_at=NOT_BEFORE_TOMORROW)
    async with open_session() as session:
        (await session.get(BackgroundJob, job_id)).attempt_count = 1  # type: ignore[union-attr]
    before_failure = datetime.now(UTC)
    await JobWorker()._record_failure(job_id, RuntimeError("transient"))
    async with open_session() as session:
        job = await session.get(BackgroundJob, job_id)
    assert job is not None and job.job_status == "queued"
    assert job.available_at >= before_failure + timedelta(seconds=30)  # 15 s × 2^attempt_count(1)


async def test_failed_last_attempt_is_dead_lettered(seed_context) -> None:
    job_id = await _enqueue("retention_cleanup", maximum_attempt_count=2, available_at=NOT_BEFORE_TOMORROW)
    async with open_session() as session:
        (await session.get(BackgroundJob, job_id)).attempt_count = 2  # type: ignore[union-attr]
    await JobWorker()._record_failure(job_id, RuntimeError("still failing"))
    async with open_session() as session:
        job = await session.get(BackgroundJob, job_id)
    assert job is not None and job.job_status == "dead_lettered"


async def test_job_with_an_expired_lease_returns_to_the_queue(seed_context) -> None:
    async with open_session() as session:
        stuck_job = BackgroundJob(
            job_type="retention_cleanup", job_payload_json={}, job_status="running", lease_expires_at=datetime.now(UTC) - timedelta(minutes=1), available_at=NOT_BEFORE_TOMORROW
        )
        session.add(stuck_job)
        await session.flush()
        job_id = stuck_job.background_job_id
    await JobWorker()._write_heartbeat_and_recover_leases()
    async with open_session() as session:
        recovered = await session.get(BackgroundJob, job_id)
    assert recovered is not None and recovered.job_status == "queued"

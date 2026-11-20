"""keigan/workers/job_queue.py: deduplication, failure handling and lease recovery."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import IntegrityError

from keigan.config.database_config import open_session
from keigan.entities.platform_entities import BackgroundJob
from keigan.workers.job_queue import JobQueue, JobWorker
from keigan.workers.worker_settings import WorkerSettings

NOT_BEFORE_TOMORROW = datetime.now(UTC) + timedelta(days=1)  # keeps test jobs out of drain_jobs()


async def _enqueue(job_type: str, **options: object) -> str:
    async with open_session() as session:
        return await JobQueue(session).enqueue(job_type, {}, **options)  # type: ignore[arg-type]


async def test_enqueue_with_an_active_deduplication_key_returns_the_existing_job(seed_context) -> None:
    key = f"test-dedup:{uuid.uuid4()}"
    first_job_id = await _enqueue("retention_cleanup", deduplication_key=key, available_at=NOT_BEFORE_TOMORROW)
    second_job_id = await _enqueue("retention_cleanup", deduplication_key=key)
    assert second_job_id == first_job_id


async def test_concurrent_enqueue_with_one_key_keeps_one_active_job(seed_context) -> None:
    """Pods enqueue at the same moment: every caller must get the id of the single job that won."""
    key = f"test-race:{uuid.uuid4()}"
    job_ids = await asyncio.gather(*[_enqueue("retention_cleanup", deduplication_key=key, available_at=NOT_BEFORE_TOMORROW) for _ in range(5)])
    async with open_session() as session:
        job_count = await session.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.deduplication_key == key))
    assert job_count == 1, f"{job_count} active jobs share one deduplication key"
    assert len(set(job_ids)) == 1, f"callers were given different job ids: {job_ids}"


async def test_enqueue_that_loses_the_insert_race_returns_the_winning_job(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-check read is stale (the other pod's insert was not committed yet); the unique index then rejects ours."""
    key = f"test-lost-race:{uuid.uuid4()}"
    winner_job_id = await _enqueue("retention_cleanup", deduplication_key=key, available_at=NOT_BEFORE_TOMORROW)
    original_find_active_job = JobQueue._find_active_job
    stale_reads_left = [1]

    async def stale_once(self: JobQueue, deduplication_key: str):  # type: ignore[no-untyped-def]
        if stale_reads_left[0]:
            stale_reads_left[0] -= 1
            return None
        return await original_find_active_job(self, deduplication_key)

    monkeypatch.setattr(JobQueue, "_find_active_job", stale_once)
    assert await _enqueue("retention_cleanup", deduplication_key=key, available_at=NOT_BEFORE_TOMORROW) == winner_job_id


async def test_database_rejects_a_second_active_job_with_the_same_deduplication_key(seed_context) -> None:
    key = f"test-unique:{uuid.uuid4()}"
    async with open_session() as session:
        session.add(BackgroundJob(job_type="retention_cleanup", deduplication_key=key, job_status="queued", available_at=NOT_BEFORE_TOMORROW))
    with pytest.raises(IntegrityError):
        async with open_session() as session:
            session.add(BackgroundJob(job_type="retention_cleanup", deduplication_key=key, job_status="running", available_at=NOT_BEFORE_TOMORROW))


async def test_finished_job_does_not_block_a_new_job_with_the_same_deduplication_key(seed_context) -> None:
    key = f"test-finished:{uuid.uuid4()}"
    async with open_session() as session:
        session.add(BackgroundJob(job_type="retention_cleanup", deduplication_key=key, job_status="succeeded", available_at=NOT_BEFORE_TOMORROW))
    new_job_id = await _enqueue("retention_cleanup", deduplication_key=key, available_at=NOT_BEFORE_TOMORROW)
    async with open_session() as session:
        statuses = sorted((await session.scalars(select(BackgroundJob.job_status).where(BackgroundJob.deduplication_key == key))).all())
    assert statuses == ["queued", "succeeded"]
    assert new_job_id


async def test_jobs_without_a_deduplication_key_can_be_queued_many_times(seed_context) -> None:
    first_job_id = await _enqueue("retention_cleanup", available_at=NOT_BEFORE_TOMORROW)
    second_job_id = await _enqueue("retention_cleanup", available_at=NOT_BEFORE_TOMORROW)
    assert first_job_id != second_job_id


async def test_two_workers_never_lease_the_same_job(seed_context) -> None:
    """SQL Server ignores FOR UPDATE SKIP LOCKED, so the lease itself must be an atomic, guarded update."""
    job_id = await _enqueue("retention_cleanup", priority_number=-1000)  # sorts before every other queued job
    leased_job_ids = await asyncio.gather(JobWorker()._lease_next_job(), JobWorker()._lease_next_job())
    try:
        assert leased_job_ids.count(job_id) == 1, f"the same job was leased by both workers: {leased_job_ids}"
    finally:
        async with open_session() as session:
            await session.execute(update(BackgroundJob).where(BackgroundJob.background_job_id.in_([id_ for id_ in leased_job_ids if id_] + [job_id])).values(job_status="succeeded", finished_at=datetime.now(UTC)))


def test_lease_statement_only_claims_a_job_that_is_still_queued_on_sql_server() -> None:
    claim_statement = JobWorker._build_claim_statement("job-1", "worker-a", datetime(2026, 11, 20, 8, 0, tzinfo=UTC), timedelta(minutes=10))
    compiled = claim_statement.compile(dialect=mssql.dialect())
    assert str(compiled).endswith("WHERE background_job.background_job_id = :background_job_id_1 AND background_job.job_status = :job_status_1")
    assert compiled.params["background_job_id_1"] == "job-1" and compiled.params["job_status_1"] == "queued"
    assert "attempt_count=(background_job.attempt_count + :attempt_count_1)" in str(compiled).replace(", ", ",").replace("= ", "=")


async def test_running_job_keeps_its_lease_while_a_long_handler_runs(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    """H5: a handler that outlives the lease must not be handed to another worker."""
    worker_settings = WorkerSettings(job_lease_duration_seconds=0.6, job_lease_renewal_interval_seconds=0.15)
    long_worker, other_worker = JobWorker(worker_settings), JobWorker(worker_settings)

    async def slow_handler(job_type: str, job_payload: dict) -> dict:
        await asyncio.sleep(1.5)  # more than twice the lease
        return {}

    monkeypatch.setattr("keigan.workers.job_handlers.execute_job_handler", slow_handler)
    job_id = await _enqueue("retention_cleanup", priority_number=-1000)
    assert await long_worker._lease_next_job() == job_id
    await long_worker._concurrency_limiter.acquire()  # _execute_job releases it
    running_task = asyncio.create_task(long_worker._execute_job(job_id))
    await asyncio.sleep(1.0)  # the original lease ran out at 0.6 s
    await other_worker._write_heartbeat_and_recover_leases()
    async with open_session() as session:
        job_while_running = await session.get(BackgroundJob, job_id)
    await running_task
    async with open_session() as session:
        finished_job = await session.get(BackgroundJob, job_id)
    assert job_while_running is not None and job_while_running.job_status == "running", "another worker took over a job that is still running"
    assert finished_job is not None and finished_job.job_status == "succeeded" and finished_job.attempt_count == 1


async def test_lease_renewal_reports_a_lost_lease_when_the_job_was_already_requeued(seed_context) -> None:
    job_id = await _enqueue("retention_cleanup", available_at=NOT_BEFORE_TOMORROW)  # status queued: nobody holds the lease
    assert await JobWorker()._renew_lease(job_id) is False


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


# ── INVESTIGATION_MAX_CONCURRENT ──────────────────────────────────────────────────────────────────


async def _insert_job(job_type: str, job_status: str, priority_number: int = 100) -> str:
    async with open_session() as session:
        job = BackgroundJob(job_type=job_type, job_status=job_status, priority_number=priority_number, available_at=datetime.now(UTC) - timedelta(minutes=1),
                            lease_expires_at=datetime.now(UTC) + timedelta(minutes=10) if job_status == "running" else None)
        session.add(job)
        await session.flush()
        return job.background_job_id


async def _finish_jobs(job_ids: list[str]) -> None:
    async with open_session() as session:
        await session.execute(update(BackgroundJob).where(BackgroundJob.background_job_id.in_(job_ids)).values(job_status="succeeded", finished_at=datetime.now(UTC)))


async def _running_investigation_count() -> int:
    async with open_session() as session:
        return int(await session.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.job_type == "run_investigation", BackgroundJob.job_status == "running")) or 0)


async def test_investigation_waits_in_the_queue_when_the_concurrency_limit_is_reached(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    """The limit protects the AI budget and the model: a burst of alerts queues investigations instead of starting them all."""
    worker = JobWorker()
    monkeypatch.setattr(worker.settings, "investigation_max_concurrent", await _running_investigation_count() + 1)
    running_id = await _insert_job("run_investigation", "running")
    waiting_investigation_id = await _insert_job("run_investigation", "queued", priority_number=-1000)
    other_job_id = await _insert_job("retention_cleanup", "queued", priority_number=-999)
    try:
        leased_job_id = await worker._lease_next_job()
        assert leased_job_id == other_job_id, "a queued investigation was started although the limit was reached, or it blocked the jobs behind it"
        async with open_session() as session:
            waiting_investigation = await session.get(BackgroundJob, waiting_investigation_id)
        assert waiting_investigation is not None and waiting_investigation.job_status == "queued"
    finally:
        await _finish_jobs([running_id, waiting_investigation_id, other_job_id])


async def test_investigation_starts_when_it_is_under_the_concurrency_limit(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    worker = JobWorker()
    monkeypatch.setattr(worker.settings, "investigation_max_concurrent", await _running_investigation_count() + 2)
    running_id = await _insert_job("run_investigation", "running")
    waiting_investigation_id = await _insert_job("run_investigation", "queued", priority_number=-1000)
    try:
        assert await worker._lease_next_job() == waiting_investigation_id
    finally:
        await _finish_jobs([running_id, waiting_investigation_id])


async def test_the_lease_itself_refuses_an_investigation_when_another_worker_just_filled_the_limit(seed_context) -> None:
    """The candidate query and the claim are two statements; the claim must repeat the limit or two pods can both pass the first check."""
    running_id = await _insert_job("run_investigation", "running")
    waiting_investigation_id = await _insert_job("run_investigation", "queued", priority_number=-1000)
    try:
        claim = JobWorker._build_claim_statement(waiting_investigation_id, "worker-a", datetime.now(UTC), timedelta(minutes=10), {"run_investigation": await _running_investigation_count()})
        async with open_session() as session:
            assert (await session.execute(claim)).rowcount == 0
    finally:
        await _finish_jobs([running_id, waiting_investigation_id])


def test_the_investigation_limit_is_read_from_settings() -> None:
    worker = JobWorker()
    assert worker._concurrency_limits() == {"run_investigation": worker.settings.investigation_max_concurrent}


def test_the_limit_check_in_the_lease_compiles_for_sql_server_with_the_job_table_counted_under_an_alias() -> None:
    claim_statement = JobWorker._build_claim_statement("job-1", "worker-a", datetime(2026, 11, 20, 8, 0, tzinfo=UTC), timedelta(minutes=10), {"run_investigation": 3})
    compiled = str(claim_statement.compile(dialect=mssql.dialect()))
    assert "count(*)" in compiled and "background_job_1.job_type" in compiled, compiled


def test_the_limited_job_type_is_a_registered_job_handler() -> None:
    from keigan.workers.job_handlers import JOB_HANDLER_REFERENCES
    from keigan.workers.job_queue import INVESTIGATION_JOB_TYPE

    assert INVESTIGATION_JOB_TYPE in JOB_HANDLER_REFERENCES

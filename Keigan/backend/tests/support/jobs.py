"""Run queued background jobs synchronously through the real worker code."""

from __future__ import annotations

from keigan.workers.job_queue import JobWorker


async def drain_jobs(maximum_jobs: int = 200) -> list[str]:
    """Lease and execute jobs until none are available now. Returns the ids of the jobs that ran.

    Jobs that fail are rescheduled with back-off by the worker, so they are not retried within one call.
    """
    worker = JobWorker()
    executed_job_ids: list[str] = []
    while len(executed_job_ids) < maximum_jobs:
        leased_job_id = await worker._lease_next_job()
        if leased_job_id is None:
            break
        await worker._concurrency_limiter.acquire()  # _execute_job releases it
        await worker._execute_job(leased_job_id)
        executed_job_ids.append(leased_job_id)
    return executed_job_ids

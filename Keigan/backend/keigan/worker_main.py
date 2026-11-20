"""Worker process entrypoint: ``python -m keigan.worker_main`` (runs job consumers and schedulers)."""

from __future__ import annotations

import asyncio
import signal

from keigan.config.database_config import create_database_schema
from keigan.config.logging_config import configure_logging
from keigan.config.settings import get_settings
from keigan.workers.job_queue import JobWorker
from keigan.workers.schedulers import Scheduler


async def run_worker_process() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, use_json_format=not settings.is_local_environment)
    if settings.auto_create_schema:
        await create_database_schema()
    job_worker, scheduler = JobWorker(), Scheduler()
    running_loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            running_loop.add_signal_handler(stop_signal, lambda: (job_worker.stop(), scheduler.stop()))
        except NotImplementedError:  # Windows event loops do not support signal handlers
            pass
    await asyncio.gather(job_worker.run_forever(), scheduler.run_forever())


if __name__ == "__main__":
    asyncio.run(run_worker_process())

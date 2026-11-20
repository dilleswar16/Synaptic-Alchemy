"""Tuning values of the job worker and retention cleanup, read from the environment like every other Keigan setting.

They live next to the worker (not in ``config/settings.py``) so the queue can change without touching the shared settings class.
Defaults are safe for production: a job is re-queued only after its worker has been silent for ``JOB_LEASE_DURATION_SECONDS``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from keigan.config.settings import BACKEND_ROOT_DIRECTORY


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT_DIRECTORY / ".env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # A running job holds a lease; the worker renews it while the handler runs, so a long investigation is never started twice.
    job_lease_duration_seconds: float = Field(default=600.0, gt=0)
    job_lease_renewal_interval_seconds: float = Field(default=120.0, gt=0)
    worker_heartbeat_interval_seconds: float = Field(default=30.0, gt=0)
    # A handler that runs longer than this is stopped and the job fails (retried, then dead-lettered). Without it a hung job renews its lease for ever and
    # keeps counting against limits such as INVESTIGATION_MAX_CONCURRENT.
    job_maximum_runtime_seconds: float = Field(default=3600.0, gt=0)
    # Retention deletes rows in batches of this size so one cleanup never holds a long lock or fills the transaction log.
    retention_delete_batch_size: int = Field(default=500, gt=0)

    @model_validator(mode="after")
    def renewal_must_happen_well_before_the_lease_expires(self) -> WorkerSettings:
        if self.job_lease_renewal_interval_seconds * 2 > self.job_lease_duration_seconds:
            raise ValueError("JOB_LEASE_RENEWAL_INTERVAL_SECONDS must be at most half of JOB_LEASE_DURATION_SECONDS, so one missed renewal does not lose the lease.")
        return self


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()

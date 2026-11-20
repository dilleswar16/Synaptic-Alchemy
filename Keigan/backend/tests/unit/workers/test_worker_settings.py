"""keigan/workers/worker_settings.py: lease timing must leave room for a missed renewal."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from keigan.workers.worker_settings import WorkerSettings


def test_defaults_renew_the_lease_well_before_it_expires() -> None:
    settings = WorkerSettings()
    assert settings.job_lease_duration_seconds == 600 and settings.job_lease_renewal_interval_seconds == 120


def test_renewal_interval_longer_than_half_the_lease_is_refused() -> None:
    with pytest.raises(ValidationError, match="at most half"):
        WorkerSettings(job_lease_duration_seconds=100, job_lease_renewal_interval_seconds=60)

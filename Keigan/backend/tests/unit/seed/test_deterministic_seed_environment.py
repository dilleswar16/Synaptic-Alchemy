"""The deterministic seed environment fixes the clock, identifiers and randomness for ONE scoped run, then puts the real sources back."""

from __future__ import annotations

import random
import secrets
import uuid
from datetime import UTC, datetime

import pytest

from keigan.entities import base_entity
from keigan.seed.deterministic_seed_environment import deterministic_seed_environment

REFERENCE_TIME = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)


def test_clock_inside_the_run_is_the_reference_time() -> None:
    with deterministic_seed_environment(REFERENCE_TIME):
        assert base_entity.utc_now() == REFERENCE_TIME
        assert base_entity.datetime.now(UTC) == REFERENCE_TIME


def test_naive_local_clock_is_utc_so_the_result_does_not_depend_on_the_machine_time_zone() -> None:
    with deterministic_seed_environment(REFERENCE_TIME):
        assert base_entity.datetime.now() == datetime(2026, 11, 20, 12, 0, 0)


def test_identifiers_count_up_as_valid_version_4_uuids() -> None:
    with deterministic_seed_environment(REFERENCE_TIME):
        first, second = uuid.uuid4(), uuid.uuid4()
    assert str(first) == "00000000-0000-4000-8000-000000000001"
    assert str(second) == "00000000-0000-4000-8000-000000000002"


def test_two_runs_with_the_same_seed_produce_the_same_identifiers_secrets_and_random_numbers() -> None:
    def one_run() -> tuple[str, str, str, float]:
        with deterministic_seed_environment(REFERENCE_TIME, random_seed=7):
            return str(uuid.uuid4()), secrets.token_hex(8), secrets.token_urlsafe(16), random.random()

    assert one_run() == one_run()


def test_a_different_random_seed_gives_different_secrets() -> None:
    with deterministic_seed_environment(REFERENCE_TIME, random_seed=1):
        first = secrets.token_hex(16)
    with deterministic_seed_environment(REFERENCE_TIME, random_seed=2):
        second = secrets.token_hex(16)
    assert first != second


def test_real_sources_are_restored_after_the_run() -> None:
    real_uuid4, real_token_hex, real_token_urlsafe = uuid.uuid4, secrets.token_hex, secrets.token_urlsafe
    real_datetime = base_entity.datetime
    random.seed(99)
    expected_next_random = random.Random(99).random()

    with deterministic_seed_environment(REFERENCE_TIME):
        assert base_entity.datetime is not real_datetime

    assert (uuid.uuid4, secrets.token_hex, secrets.token_urlsafe) == (real_uuid4, real_token_hex, real_token_urlsafe)
    assert base_entity.datetime is real_datetime
    assert random.random() == expected_next_random
    assert abs((base_entity.utc_now() - datetime.now(UTC)).total_seconds()) < 60


def test_real_sources_are_restored_when_the_run_fails() -> None:
    real_uuid4, real_datetime = uuid.uuid4, base_entity.datetime
    with pytest.raises(RuntimeError, match="seed failed"):
        with deterministic_seed_environment(REFERENCE_TIME):
            raise RuntimeError("seed failed")
    assert uuid.uuid4 is real_uuid4
    assert base_entity.datetime is real_datetime


def test_datetimes_built_by_libraries_still_count_as_datetime_inside_the_run() -> None:
    with deterministic_seed_environment(REFERENCE_TIME):
        assert isinstance(datetime(2026, 1, 1), base_entity.datetime)
        assert isinstance(base_entity.datetime.now(UTC), datetime)


def test_evidence_queries_run_one_at_a_time_inside_the_run_so_shared_counters_cannot_interleave_and_the_limit_comes_back_after() -> None:
    from keigan.services import evidence_service

    real_limit = evidence_service.MAXIMUM_CONCURRENT_QUERIES
    with deterministic_seed_environment(REFERENCE_TIME):
        assert evidence_service.MAXIMUM_CONCURRENT_QUERIES == 1
    assert evidence_service.MAXIMUM_CONCURRENT_QUERIES == real_limit

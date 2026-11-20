"""Migrations that add a unique index must first repair rows that already break it (databases created before the index)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIRECTORY = Path(__file__).resolve().parents[3]
INITIAL_REVISION = "94692c828bd3"


def _alembic(database_file: Path, *arguments: str) -> None:
    child_environment = {key: value for key, value in os.environ.items() if key != "DATABASE_SCHEMA"}
    child_environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_file.as_posix()}"
    completed = subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=BACKEND_DIRECTORY, env=child_environment, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr


@pytest.fixture
def database_with_duplicates(tmp_path: Path) -> Path:
    """A database at the initial revision that holds the duplicates the old, lock-based code could create."""
    database_file = tmp_path / "old.db"
    _alembic(database_file, "upgrade", INITIAL_REVISION)
    with sqlite3.connect(database_file) as connection:
        for alert_id, last_seen_at in (("alert-old", "2026-11-01 10:00:00.000000"), ("alert-new", "2026-11-01 11:00:00.000000")):
            connection.execute(
                "INSERT INTO alert (alert_id, application_id, alert_fingerprint, rule_name, severity_level, alert_status, alert_summary, occurrence_count, state_change_count, is_flapping, first_seen_at, last_seen_at)"
                " VALUES (?, 'app-1', 'fingerprint-1', 'rule', 2, 'firing', '', 1, 1, 0, '2026-11-01 09:00:00.000000', ?)", (alert_id, last_seen_at),
            )
        for job_id, status, created_at in (("job-old-running", "running", "2026-11-01 10:00:00.000000"), ("job-newer-queued", "queued", "2026-11-01 11:00:00.000000"), ("job-newest-queued", "queued", "2026-11-01 12:00:00.000000")):
            connection.execute(
                "INSERT INTO background_job (background_job_id, job_type, job_payload_json, job_status, priority_number, deduplication_key, attempt_count, maximum_attempt_count, available_at, created_at)"
                " VALUES (?, 'retention_cleanup', '{}', ?, 100, 'same-key', 0, 3, ?, ?)", (job_id, status, created_at, created_at),
            )
    return database_file


def test_upgrade_keeps_only_the_newest_open_alert_per_fingerprint(database_with_duplicates: Path) -> None:
    _alembic(database_with_duplicates, "upgrade", "head")
    with sqlite3.connect(database_with_duplicates) as connection:
        statuses = dict(connection.execute("SELECT alert_id, alert_status FROM alert").fetchall())
        resolved_at = connection.execute("SELECT resolved_at FROM alert WHERE alert_id = 'alert-old'").fetchone()[0]
    assert statuses == {"alert-old": "resolved", "alert-new": "firing"}
    assert resolved_at == "2026-11-01 10:00:00.000000"


def test_upgrade_keeps_the_running_job_and_cancels_its_queued_duplicates(database_with_duplicates: Path) -> None:
    _alembic(database_with_duplicates, "upgrade", "head")
    with sqlite3.connect(database_with_duplicates) as connection:
        statuses = dict(connection.execute("SELECT background_job_id, job_status FROM background_job").fetchall())
    assert statuses == {"job-old-running": "running", "job-newer-queued": "cancelled", "job-newest-queued": "cancelled"}


def test_downgrade_removes_the_indexes_and_columns_again(database_with_duplicates: Path) -> None:
    _alembic(database_with_duplicates, "upgrade", "head")
    _alembic(database_with_duplicates, "downgrade", INITIAL_REVISION)
    with sqlite3.connect(database_with_duplicates) as connection:
        index_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        alert_source_columns = {row[1] for row in connection.execute("PRAGMA table_info(alert_source)")}
    assert "uq_alert_open_fingerprint" not in index_names and "uq_background_job_active_deduplication_key" not in index_names
    assert "webhook_secret_name" not in alert_source_columns

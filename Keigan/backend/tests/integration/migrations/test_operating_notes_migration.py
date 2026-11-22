"""Operating notes migration: three nullable columns on the application, nothing backfilled, and a reversible downgrade."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "e4c8a1d7b2f6"
NOTES_REVISION = "f1b9d3a5c7e2"
NOTES_COLUMNS = {"operating_notes_text", "operating_notes_updated_at", "operating_notes_updated_by_user_principal_name"}


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def test_upgrade_adds_the_columns_and_existing_applications_have_no_notes(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        insert_row(connection, "application", application_id="app-1", application_code="APP1")
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert NOTES_COLUMNS <= column_names(connection, "application")
        assert connection.execute("SELECT operating_notes_text, operating_notes_updated_at, operating_notes_updated_by_user_principal_name FROM application WHERE application_id = 'app-1'").fetchone() == (None, None, None)


def test_the_new_columns_are_the_only_change_to_the_application_table(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        columns_before = column_names(connection, "application")
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert column_names(connection, "application") - columns_before == NOTES_COLUMNS


def test_the_sql_server_script_adds_unicode_columns_and_the_text_column_can_hold_the_largest_allowed_notes() -> None:
    script = sql_server_script(PREVIOUS_REVISION, NOTES_REVISION)
    assert "ALTER TABLE keigan.application ADD operating_notes_text NVARCHAR(max) NULL;" in script
    assert "ALTER TABLE keigan.application ADD operating_notes_updated_at DATETIME2(6) NULL;" in script
    assert "ALTER TABLE keigan.application ADD operating_notes_updated_by_user_principal_name NVARCHAR(320) NULL;" in script
    assert f"UPDATE keigan.alembic_version SET version_num='{NOTES_REVISION}' WHERE keigan.alembic_version.version_num = '{PREVIOUS_REVISION}'" in script


def test_downgrade_removes_the_columns(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert not NOTES_COLUMNS & column_names(connection, "application")

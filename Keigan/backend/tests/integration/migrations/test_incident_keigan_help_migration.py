"""The incident's answer to "how did Keigan's analysis help?": one nullable column with a CHECK on its four words."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "f7c3e9a1b5d2"
REVISION = "a1b5c9d3e7f2"


def test_an_incident_resolved_before_the_revision_has_no_answer(tmp_path: Path) -> None:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "incident", incident_id="incident-1", application_id="application-1")
    run_alembic("upgrade", REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT keigan_help FROM incident WHERE incident_id = 'incident-1'").fetchone() == (None,)


def test_the_downgrade_drops_the_column(tmp_path: Path) -> None:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", REVISION, database_file=database)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert "keigan_help" not in [row[1] for row in connection.execute("PRAGMA table_info(incident)")]


def test_the_sql_server_script_adds_the_column_and_its_check() -> None:
    script = sql_server_script(PREVIOUS_REVISION, REVISION)
    assert "ALTER TABLE keigan.incident ADD keigan_help NVARCHAR(20) NULL" in script
    assert "ck_incident_keigan_help_values CHECK (keigan_help IN ('found_cause', 'helped_partly', 'did_not_help', 'not_used'))" in script

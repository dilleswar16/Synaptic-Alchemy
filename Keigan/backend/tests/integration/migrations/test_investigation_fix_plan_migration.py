"""Suggested fixes, phase 2 (spec 33): the fix plan column on the investigation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from support.schema_revisions import column_names, database_at, run_alembic, sql_server_script

PREVIOUS_REVISION = "a1d5c9e3f7b2"
REVISION = "c3e7a1b5d9f4"


def test_the_column_is_added_and_removed(tmp_path: Path) -> None:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert "fix_plan_json" in column_names(connection, "investigation")
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert "fix_plan_json" not in column_names(connection, "investigation")


def test_the_sql_server_script_adds_the_column() -> None:
    assert "ALTER TABLE keigan.investigation ADD fix_plan_json" in sql_server_script(PREVIOUS_REVISION, REVISION)

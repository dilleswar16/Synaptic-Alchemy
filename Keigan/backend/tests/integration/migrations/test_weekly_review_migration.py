"""Weekly health review (spec 31): the three review columns on the digest."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from support.schema_revisions import column_names, database_at, run_alembic, sql_server_script

PREVIOUS_REVISION = "f4a8c2e6b0d7"
REVISION = "a1d5c9e3f7b2"


def test_the_columns_are_added_and_removed(tmp_path: Path) -> None:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert {"reviewed_at", "reviewed_by_user_principal_name", "review_note_text"} <= set(column_names(connection, "intelligence_report"))
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert not {"reviewed_at", "review_note_text"} & set(column_names(connection, "intelligence_report"))


def test_the_sql_server_script_adds_the_columns() -> None:
    script = sql_server_script(PREVIOUS_REVISION, REVISION)
    assert "ALTER TABLE keigan.intelligence_report ADD reviewed_at" in script and "review_note_text NVARCHAR(2000)" in script

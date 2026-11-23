"""Action items linked to the record they came from (C4: a runbook finding) and to the task that tracks them in ServiceNow (D1): new columns and one more source value."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from support.schema_revisions import column_names, database_at, run_alembic, sql_server_script

PREVIOUS_REVISION = "c3e7a1b5d9f4"
REVISION = "d5a9b3e7c1f8"
NEW_COLUMNS = {"external_system", "external_record_identifier", "external_status_text", "external_synced_at", "external_sync_status"}


def test_the_columns_are_added_and_removed(tmp_path: Path) -> None:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    with sqlite3.connect(database) as connection:
        assert not NEW_COLUMNS & set(column_names(connection, "action_item"))
    run_alembic("upgrade", REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert NEW_COLUMNS <= set(column_names(connection, "action_item"))
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert not NEW_COLUMNS & set(column_names(connection, "action_item"))


def test_existing_items_stay_unlinked(tmp_path: Path) -> None:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    with sqlite3.connect(database) as connection:
        from support.schema_revisions import insert_row

        insert_row(connection, "application", application_id="app-1")
        insert_row(connection, "action_item", action_item_id="item-1", application_id="app-1", item_source_kind="manual", item_title="Old item", action_type="prevent", action_priority="normal", item_status="open")
    run_alembic("upgrade", REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT external_system, external_sync_status FROM action_item WHERE action_item_id = 'item-1'").fetchone() == (None, None)


def test_the_sql_server_script_adds_the_columns_the_checks_and_the_new_source() -> None:
    script = sql_server_script(PREVIOUS_REVISION, REVISION)
    for column in NEW_COLUMNS:
        assert f"ALTER TABLE keigan.action_item ADD {column}" in script
    assert "ck_action_item_external_sync_status_values" in script and "'pending'" in script and "'linked'" in script and "'failed'" in script
    assert "ck_action_item_item_source_kind_values" in script and "'runbook_health'" in script

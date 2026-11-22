"""Action items (spec 29): the table, its checks and its references."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "c8a2e4f6b1d3"
ACTION_ITEMS_REVISION = "e7b3a9d1c5f2"


@pytest.fixture
def database_with_the_table(tmp_path: Path) -> Path:
    database = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", ACTION_ITEMS_REVISION, database_file=database)
    return database


def an_item(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = dict(
        action_item_id="item-1", application_id="application-1", item_source_kind="manual", item_title="Add a connection pool alert", action_type="detect", item_status="open",
        action_priority="normal", due_on_change_count=0, reminder_count=0, display_order=0,
    )
    values.update(overrides)
    return values


def test_the_table_is_created_with_its_columns(database_with_the_table: Path) -> None:
    with sqlite3.connect(database_with_the_table) as connection:
        assert {"action_item_id", "application_id", "incident_id", "postmortem_id", "owner_stakeholder_id", "item_status", "due_on", "original_due_on", "external_reference_text"} <= set(column_names(connection, "action_item"))


def test_a_status_priority_type_or_source_outside_the_enum_is_refused(database_with_the_table: Path) -> None:
    with sqlite3.connect(database_with_the_table) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "action_item", **an_item())
        for column, bad_value in (("item_status", "finished"), ("action_priority", "p0"), ("action_type", "fix"), ("item_source_kind", "magic")):
            with pytest.raises(sqlite3.IntegrityError):
                insert_row(connection, "action_item", **an_item(action_item_id=f"bad-{column}", **{column: bad_value}))


def test_an_item_is_deleted_with_its_application_but_not_with_its_incident(database_with_the_table: Path) -> None:
    with sqlite3.connect(database_with_the_table) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "incident", incident_id="incident-1", application_id="application-1")
        insert_row(connection, "action_item", **an_item(incident_id="incident-1"))
        with pytest.raises(sqlite3.IntegrityError):  # the incident cannot be removed while an item still points at it (retention releases it first)
            connection.execute("DELETE FROM incident WHERE incident_id = 'incident-1'")
        connection.execute("DELETE FROM application WHERE application_id = 'application-1'")
        assert connection.execute("SELECT COUNT(*) FROM action_item").fetchone() == (0,)


def test_the_downgrade_drops_the_table(database_with_the_table: Path) -> None:
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_with_the_table)
    with sqlite3.connect(database_with_the_table) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'action_item'").fetchone() is None


def test_the_sql_server_script_creates_the_table_with_its_checks_and_indexes() -> None:
    script = sql_server_script(PREVIOUS_REVISION, ACTION_ITEMS_REVISION)
    assert "CREATE TABLE keigan.action_item" in script
    assert "CONSTRAINT ck_action_item_item_status_values CHECK (item_status IN ('proposed', 'open', 'in_progress', 'blocked', 'done', 'wont_do'))" in script
    assert "CREATE INDEX ix_action_item_application_id_item_status_due_on ON keigan.action_item (application_id, item_status, due_on)" in script

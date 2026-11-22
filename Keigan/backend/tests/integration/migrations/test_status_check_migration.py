"""H13 migration: CHECK constraints rendered from the entities, a clear failure before them when existing rows hold other values, and the SQLite behaviour."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase
from support.schema_revisions import COLUMNS_CHECKED_AFTER_THE_CHECK_REVISION, TABLES_ADDED_AFTER_THE_CHECK_REVISION, column_of_values_check, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "c9e4f1b8d3a7"
CHECK_REVISION = "d2a6b0c5e8f9"


def checks_in_the_entities() -> list[tuple[str, CheckConstraint]]:
    return [(table.name, constraint) for table in EntityBase.metadata.sorted_tables for constraint in table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name and constraint.name.endswith("_values") and table.name not in TABLES_ADDED_AFTER_THE_CHECK_REVISION
            and column_of_values_check(table.name, constraint.name) not in COLUMNS_CHECKED_AFTER_THE_CHECK_REVISION]


@pytest.fixture(scope="module")
def script() -> str:
    """Alembic offline mode for SQL Server's dialect. The T-SQL was not executed (no SQL Server available)."""
    return sql_server_script(PREVIOUS_REVISION, CHECK_REVISION)


def test_the_sql_server_script_adds_the_constraint_of_every_constrained_column_with_the_values_of_the_entity(script: str) -> None:
    constraints = checks_in_the_entities()
    assert len(constraints) >= 40
    for table_name, constraint in constraints:
        expected = f"ALTER TABLE keigan.{table_name} ADD CONSTRAINT {constraint.name} CHECK ({constraint.sqltext})"
        assert expected in script, expected


def test_the_literal_values_in_the_script_are_the_ones_the_code_writes(script: str) -> None:
    assert "ADD CONSTRAINT ck_alert_alert_status_values CHECK (alert_status IN ('firing', 'resolved'))" in script
    assert "ADD CONSTRAINT ck_background_job_job_status_values CHECK (job_status IN ('queued', 'running', 'succeeded', 'failed', 'dead_lettered', 'cancelled'))" in script


def test_each_constraint_is_preceded_by_a_check_that_stops_with_a_clear_message_when_rows_hold_other_values(script: str) -> None:
    for table_name, constraint in checks_in_the_entities():
        column_name = constraint.name.removeprefix(f"ck_{table_name}_").removesuffix("_values")
        guard = f"IF EXISTS (SELECT 1 FROM keigan.{table_name} WHERE {column_name} IS NOT NULL AND NOT ({constraint.sqltext})) THROW 50000, N'"
        add = f"ALTER TABLE keigan.{table_name} ADD CONSTRAINT {constraint.name} CHECK"
        assert guard in script and script.index(guard) < script.index(add), (table_name, column_name)
    message_start = script.index("THROW 50000, N'") + len("THROW 50000, N'")
    message = script[message_start:script.index("'", message_start)]
    assert "keigan.alert_source.source_tool" in message and "correct those rows" in message and "run this script again" in message


def test_the_downgrade_drops_the_constraints(script: str) -> None:
    downgrade_script = run_alembic("downgrade", f"{CHECK_REVISION}:{PREVIOUS_REVISION}", "--sql", sql_server=True)
    assert "ALTER TABLE keigan.alert DROP CONSTRAINT ck_alert_alert_status_values" in downgrade_script


def test_a_sqlite_database_is_upgraded_without_a_rebuild_and_keeps_every_row(tmp_path: Path) -> None:
    """SQLite cannot add a CHECK to an existing table without a rebuild (which cascade-deletes rows): rows stay, local databases are recreated to get the constraints."""
    database_file = database_at(tmp_path, PREVIOUS_REVISION)
    with sqlite3.connect(database_file) as connection:
        insert_row(connection, "application", application_id="app-1", application_code="APP1")
        insert_row(connection, "incident", incident_id="inc-1", application_id="app-1", incident_status="a status nobody wrote")
    run_alembic("upgrade", CHECK_REVISION, database_file=database_file)
    with sqlite3.connect(database_file) as connection:
        assert connection.execute("SELECT incident_status FROM incident").fetchall() == [("a status nobody wrote",)]
        assert connection.execute("SELECT COUNT(*) FROM application").fetchone()[0] == 1

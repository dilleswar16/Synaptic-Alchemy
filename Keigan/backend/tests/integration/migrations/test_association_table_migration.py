"""H11 migration: JSON id lists become association rows, with the data copied first (never dropped), on SQLite and in the T-SQL Alembic renders."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "3be32fbc3e37"
ASSOCIATION_REVISION = "a3f5c0d1e2b4"
JSON_COLUMNS_BY_TABLE = {
    "incident": "affected_service_ids_json", "investigation": ("investigated_service_ids_json", "matched_runbook_ids_json"), "conversation": "application_ids_json",
    "alert_group": "affected_service_ids_json", "maintenance_window": "applies_to_service_ids_json", "runbook": "applies_to_service_ids_json",
    "stakeholder": "subscribed_service_ids_json", "application_topology": "generated_from_document_ids_json",
}


def build_old_database(directory: Path) -> Path:
    """A database at the previous revision holding lists as JSON, including an unknown id, a duplicate, a JSON null and an empty column."""
    database_file = database_at(directory, PREVIOUS_REVISION)
    with sqlite3.connect(database_file) as connection:
        insert_row(connection, "application", application_id="app-1", application_code="APP1")
        for service_id in ("svc-1", "svc-2", "svc-3"):
            insert_row(connection, "monitored_service", service_id=service_id, application_id="app-1")
        insert_row(connection, "incident", incident_id="inc-1", application_id="app-1", affected_service_ids_json=json.dumps(["svc-2", "svc-gone", "svc-1", "svc-2"]))
        insert_row(connection, "incident", incident_id="inc-null", application_id="app-1", affected_service_ids_json="null")
        insert_row(connection, "incident", incident_id="inc-empty", application_id="app-1")
        insert_row(connection, "runbook", runbook_id="run-1", application_id="app-1", applies_to_service_ids_json=json.dumps(["svc-3"]))
        insert_row(connection, "investigation", investigation_id="inv-1", application_id="app-1", investigated_service_ids_json=json.dumps(["svc-1"]), matched_runbook_ids_json=json.dumps(["run-1", "run-gone"]))
        insert_row(connection, "conversation", conversation_id="conv-1", application_ids_json=json.dumps(["app-1", "app-gone"]))
        insert_row(connection, "alert_group", alert_group_id="grp-1", application_id="app-1", affected_service_ids_json=json.dumps(["svc-3", "svc-1"]))
        insert_row(connection, "maintenance_window", maintenance_window_id="win-1", application_id="app-1", applies_to_service_ids_json=json.dumps(["svc-1", "svc-2"]))
        insert_row(connection, "stakeholder", stakeholder_id="stk-1", application_id="app-1", subscribed_service_ids_json=json.dumps(["svc-2"]))
        insert_row(connection, "knowledge_document", knowledge_document_id="doc-1", application_id="app-1")
        insert_row(connection, "application_topology", topology_id="top-1", application_id="app-1", generated_from_document_ids_json=json.dumps(["doc-1", "doc-gone"]))
    return database_file


@pytest.fixture
def old_database(tmp_path: Path) -> Path:
    return build_old_database(tmp_path)


@pytest.fixture(scope="module")
def upgraded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database_file = build_old_database(tmp_path_factory.mktemp("associations"))
    run_alembic("upgrade", ASSOCIATION_REVISION, database_file=database_file)
    return database_file


def link_rows(database_file: Path, table: str, owner_column: str, linked_column: str) -> list[tuple[str, str, int]]:
    with sqlite3.connect(database_file) as connection:
        return connection.execute(f"SELECT {owner_column}, {linked_column}, position FROM {table} ORDER BY {owner_column}, position").fetchall()


def test_every_list_is_copied_in_order_and_ids_of_rows_that_no_longer_exist_are_skipped(upgraded_database: Path) -> None:
    assert link_rows(upgraded_database, "incident_affected_service", "incident_id", "service_id") == [("inc-1", "svc-2", 0), ("inc-1", "svc-1", 2)]
    assert link_rows(upgraded_database, "investigation_investigated_service", "investigation_id", "service_id") == [("inv-1", "svc-1", 0)]
    assert link_rows(upgraded_database, "investigation_matched_runbook", "investigation_id", "runbook_id") == [("inv-1", "run-1", 0)]
    assert link_rows(upgraded_database, "conversation_application", "conversation_id", "application_id") == [("conv-1", "app-1", 0)]
    assert link_rows(upgraded_database, "alert_group_affected_service", "alert_group_id", "service_id") == [("grp-1", "svc-3", 0), ("grp-1", "svc-1", 1)]
    assert link_rows(upgraded_database, "maintenance_window_applies_to_service", "maintenance_window_id", "service_id") == [("win-1", "svc-1", 0), ("win-1", "svc-2", 1)]
    assert link_rows(upgraded_database, "runbook_applies_to_service", "runbook_id", "service_id") == [("run-1", "svc-3", 0)]
    assert link_rows(upgraded_database, "stakeholder_subscribed_service", "stakeholder_id", "service_id") == [("stk-1", "svc-2", 0)]
    assert link_rows(upgraded_database, "topology_source_document", "topology_id", "knowledge_document_id") == [("top-1", "doc-1", 0)]


def test_the_json_columns_are_gone_after_the_data_was_copied(upgraded_database: Path) -> None:
    with sqlite3.connect(upgraded_database) as connection:
        remaining_json_columns = [column for table in JSON_COLUMNS_BY_TABLE for column in column_names(connection, table) if column.endswith("_ids_json")]
        incident_count = connection.execute("SELECT COUNT(*) FROM incident").fetchone()[0]
    assert remaining_json_columns == []
    assert incident_count == 3  # dropping a column rebuilds nothing: no row was lost or cascade-deleted


def test_the_foreign_keys_and_the_index_on_the_second_column_exist(upgraded_database: Path) -> None:
    with sqlite3.connect(upgraded_database) as connection:
        foreign_keys = {(row[2], row[3], row[6]) for row in connection.execute("PRAGMA foreign_key_list(incident_affected_service)")}
        index_names = {row[1] for row in connection.execute("PRAGMA index_list(incident_affected_service)")}
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("INSERT INTO incident_affected_service (incident_id, service_id, position) VALUES ('inc-1', 'svc-gone', 0)")
    assert foreign_keys == {("incident", "incident_id", "CASCADE"), ("monitored_service", "service_id", "NO ACTION")}
    assert "ix_incident_affected_service_service_id" in index_names


def test_downgrade_puts_the_lists_back_as_json_in_order(old_database: Path) -> None:
    run_alembic("upgrade", ASSOCIATION_REVISION, database_file=old_database)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=old_database)
    with sqlite3.connect(old_database) as connection:
        incident_list = json.loads(connection.execute("SELECT affected_service_ids_json FROM incident WHERE incident_id = 'inc-1'").fetchone()[0])
        empty_list = connection.execute("SELECT affected_service_ids_json FROM incident WHERE incident_id = 'inc-empty'").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert incident_list == ["svc-2", "svc-1"]
    assert empty_list is None
    assert "incident_affected_service" not in tables


def test_the_sql_server_script_copies_with_openjson_before_it_drops_each_column() -> None:
    """Rendered with Alembic offline mode for SQL Server's dialect; the T-SQL itself was not executed (no SQL Server available)."""
    script = sql_server_script(PREVIOUS_REVISION, ASSOCIATION_REVISION)
    copy_statement = "INSERT INTO keigan.incident_affected_service"
    drop_statement = "ALTER TABLE keigan.incident DROP COLUMN affected_service_ids_json"
    assert "CROSS APPLY OPENJSON(" in script and "ISJSON(" in script
    assert copy_statement in script and drop_statement in script
    assert script.index(copy_statement) < script.index(drop_statement)
    assert "CREATE TABLE keigan.incident_affected_service" in script
    assert "CONSTRAINT fk_incident_affected_service_service_id_monitored_service FOREIGN KEY(service_id) REFERENCES keigan.monitored_service (service_id)" in script
    assert "CREATE INDEX ix_incident_affected_service_service_id ON keigan.incident_affected_service (service_id)" in script
    for statement_text in script.split("GO"):
        if "INSERT INTO keigan." in statement_text and "_service" in statement_text:
            assert "WHERE" in statement_text and "EXISTS" in statement_text  # only ids of rows that exist are copied

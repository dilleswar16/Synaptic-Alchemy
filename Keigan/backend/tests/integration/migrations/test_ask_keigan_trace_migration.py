"""Ask Keigan trace migration: two new tables (answer runs and their steps) with the keys, checks and indexes the entities declare, and a reversible downgrade."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase
from support.schema_revisions import column_names, database_at, run_alembic, sql_server_script

PREVIOUS_REVISION = "f1b9d3a5c7e2"
TRACE_REVISION = "a7c3e9f1b5d2"
TRACE_TABLES = ("chat_answer_run", "chat_run_step")


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_upgrade_creates_both_tables_with_every_column_the_entities_declare(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        assert not set(TRACE_TABLES) & table_names(connection)
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        for table_name in TRACE_TABLES:
            assert column_names(connection, table_name) == {column.name for column in EntityBase.metadata.tables[table_name].columns}


def test_the_foreign_keys_cascade_only_along_one_path_and_everything_else_is_no_action(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        run_keys = {(row[2], row[3], row[6]) for row in connection.execute("PRAGMA foreign_key_list(chat_answer_run)")}
        step_keys = {(row[2], row[3], row[6]) for row in connection.execute("PRAGMA foreign_key_list(chat_run_step)")}
    assert run_keys == {
        ("conversation", "conversation_id", "CASCADE"), ("conversation_message", "user_message_id", "NO ACTION"),
        ("conversation_message", "assistant_message_id", "NO ACTION"), ("investigation", "investigation_id", "NO ACTION"),
    }
    assert step_keys == {("chat_answer_run", "answer_run_id", "CASCADE"), ("chat_run_step", "parent_run_step_id", "NO ACTION")}


def test_the_unique_constraints_and_indexes_of_the_spec_exist(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        index_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        table_sql = {table: connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()[0] for table in TRACE_TABLES}
    assert {
        "ix_chat_answer_run_conversation_id", "ix_chat_answer_run_requested_by_user_principal_name_started_at", "ix_chat_answer_run_investigation_id",
        "ix_chat_run_step_application_id", "ix_chat_run_step_tool_name",
    } <= index_names
    assert "uq_chat_answer_run_conversation_id_client_request_id" in table_sql["chat_answer_run"]
    assert "uq_chat_run_step_answer_run_id_sequence_number" in table_sql["chat_run_step"]


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("chat_answer_run", "conversation_scope"), ("chat_answer_run", "run_status"), ("chat_answer_run", "stop_reason"), ("chat_answer_run", "tool_calling_mode"),
        ("chat_run_step", "step_kind"), ("chat_run_step", "step_status"),
    ],
)
def test_the_value_checks_are_in_the_migrated_database(database_before_the_revision: Path, table: str, column: str) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        table_sql = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()[0]
    assert f"ck_{table}_{column}_values" in table_sql


def test_the_sql_server_script_creates_both_tables_with_unicode_text_that_can_hold_the_largest_outputs() -> None:
    script = sql_server_script(PREVIOUS_REVISION, TRACE_REVISION)
    assert "CREATE TABLE keigan.chat_answer_run" in script
    assert "CREATE TABLE keigan.chat_run_step" in script
    assert "output_json NVARCHAR(max)" in script and "model_view_text NVARCHAR(max)" in script and "model_text NVARCHAR(max)" in script
    assert "client_request_id NVARCHAR(64) NOT NULL" in script
    assert f"UPDATE keigan.alembic_version SET version_num='{TRACE_REVISION}' WHERE keigan.alembic_version.version_num = '{PREVIOUS_REVISION}'" in script


def test_downgrade_drops_both_tables(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert not set(TRACE_TABLES) & table_names(connection)

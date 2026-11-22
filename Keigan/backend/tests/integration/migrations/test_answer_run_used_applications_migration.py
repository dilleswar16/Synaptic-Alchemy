"""The run of an Ask Keigan answer keeps the applications whose data it used, so a person who loses access to one no longer sees the answer (spec 23, 6.6)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "c5e7a9b3d1f4"
USED_APPLICATIONS_REVISION = "b8d4f2a6c0e3"
COLUMN = "used_application_ids_json"


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def test_the_run_gets_a_nullable_column_and_an_earlier_run_keeps_working_without_it(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        assert COLUMN not in column_names(connection, "chat_answer_run")
        insert_row(connection, "conversation", conversation_id="conversation-1")
        insert_row(connection, "conversation_message", message_id="question-1", conversation_id="conversation-1")
        insert_row(
            connection, "chat_answer_run", answer_run_id="earlier", conversation_id="conversation-1", user_message_id="question-1", client_request_id="earlier", run_status="completed",
            conversation_scope="investigation", tool_calling_mode="native",
        )
    run_alembic("upgrade", USED_APPLICATIONS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert COLUMN in column_names(connection, "chat_answer_run")
        assert connection.execute(f"SELECT {COLUMN} FROM chat_answer_run WHERE answer_run_id = 'earlier'").fetchone() == (None,)


def test_the_downgrade_drops_the_column(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", USED_APPLICATIONS_REVISION, database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert COLUMN not in column_names(connection, "chat_answer_run")


def test_the_sql_server_script_adds_one_nullable_json_column() -> None:
    script = sql_server_script(PREVIOUS_REVISION, USED_APPLICATIONS_REVISION)
    assert f"ALTER TABLE keigan.chat_answer_run ADD {COLUMN} NVARCHAR(max) NULL" in script

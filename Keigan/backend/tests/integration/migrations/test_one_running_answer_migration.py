"""One running answer per conversation is guaranteed by the database: a filtered unique index on ``chat_answer_run``, and the older duplicates it would refuse are ended first.
The same revision adds the column that keeps the parameters of a failed answer's error."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "a7c3e9f1b5d2"
INDEX_REVISION = "c5e7a9b3d1f4"
INDEX_NAME = "uq_chat_answer_run_one_running_per_conversation"


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def add_conversation(connection: sqlite3.Connection, conversation_id: str) -> None:
    insert_row(connection, "conversation", conversation_id=conversation_id)
    insert_row(connection, "conversation_message", message_id=f"question-{conversation_id}", conversation_id=conversation_id)


def add_run(connection: sqlite3.Connection, run_id: str, conversation_id: str, run_status: str, started_at: str) -> None:
    insert_row(
        connection, "chat_answer_run", answer_run_id=run_id, conversation_id=conversation_id, user_message_id=f"question-{conversation_id}", client_request_id=run_id,
        run_status=run_status, started_at=started_at, conversation_scope="keigan_ai_chat", tool_calling_mode="native",
    )


def test_the_index_is_unique_and_filtered_to_running_runs(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        index_sql = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (INDEX_NAME,)).fetchone()[0].upper()
        add_conversation(connection, "conversation-1")
        add_run(connection, "run-1", "conversation-1", "running", "2026-01-01 00:00:00.000000")
        add_run(connection, "run-2", "conversation-1", "completed", "2026-01-01 00:00:01.000000")
        add_run(connection, "run-3", "conversation-1", "completed", "2026-01-01 00:00:02.000000")
        with pytest.raises(sqlite3.IntegrityError):
            add_run(connection, "run-4", "conversation-1", "running", "2026-01-01 00:00:03.000000")
    assert "UNIQUE" in index_sql and "RUN_STATUS = 'RUNNING'" in index_sql


def test_older_duplicate_running_runs_are_ended_as_interrupted_and_the_newest_stays_running(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        add_conversation(connection, "conversation-1")
        add_conversation(connection, "conversation-2")
        add_run(connection, "old", "conversation-1", "running", "2026-01-01 00:00:00.000000")
        add_run(connection, "new", "conversation-1", "running", "2026-01-01 00:05:00.000000")
        add_run(connection, "alone", "conversation-2", "running", "2026-01-01 00:00:00.000000")
    run_alembic("upgrade", INDEX_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        rows = {row[0]: row[1:] for row in connection.execute("SELECT answer_run_id, run_status, stop_reason, error_code FROM chat_answer_run")}
    assert rows == {"old": ("failed", "failed", "answer_interrupted"), "new": ("running", None, None), "alone": ("running", None, None)}


def test_the_run_gets_a_nullable_column_for_the_parameters_of_its_error(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        assert "error_parameters_json" not in column_names(connection, "chat_answer_run")
        add_conversation(connection, "conversation-1")
        add_run(connection, "earlier", "conversation-1", "completed", "2026-01-01 00:00:00.000000")
    run_alembic("upgrade", INDEX_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert "error_parameters_json" in column_names(connection, "chat_answer_run")
        assert connection.execute("SELECT error_parameters_json FROM chat_answer_run WHERE answer_run_id = 'earlier'").fetchone() == (None,)  # existing rows keep working


def test_the_downgrade_drops_the_index_and_the_column(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", INDEX_REVISION, database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (INDEX_NAME,)).fetchone()[0] == 0
        assert "error_parameters_json" not in column_names(connection, "chat_answer_run")


def test_the_sql_server_script_creates_a_filtered_unique_index_after_ending_the_duplicates() -> None:
    script = sql_server_script(PREVIOUS_REVISION, INDEX_REVISION)
    assert "ALTER TABLE keigan.chat_answer_run ADD error_parameters_json NVARCHAR(max) NULL" in script
    assert f"CREATE UNIQUE INDEX {INDEX_NAME} ON keigan.chat_answer_run (conversation_id) WHERE run_status = 'running'" in script
    assert script.index("UPDATE keigan.chat_answer_run") < script.index("CREATE UNIQUE INDEX")

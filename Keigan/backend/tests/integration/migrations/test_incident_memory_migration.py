"""Similar incident memory (spec 34): the three tables, their checks, the one live entry per investigation and the one answer per person and suggestion."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "d5a9b3e7c1f8"
REVISION = "e6b2d8f4a0c3"
NOW = "2026-11-24 00:00:00"


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", REVISION, database_file=path)
    return path


def an_entry(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = dict(
        incident_memory_entry_id="entry-1", application_id="application-1", investigation_id="investigation-1", entry_status="active", occurred_at=NOW, incident_title_text="Claims API slow",
        cause_source="none", fix_source="none", search_terms_json="{}", service_ids_json="[]", built_at=NOW, created_at=NOW, updated_at=NOW,
    )
    values.update(overrides)
    return values


def test_the_three_tables_exist(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"incident_memory_entry", "incident_memory_key", "incident_memory_relevance_feedback"} <= names


def test_a_status_or_source_outside_the_enum_is_refused(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        for column, value in (("entry_status", "deleted"), ("cause_source", "guess"), ("fix_source", "guess")):
            with pytest.raises(sqlite3.IntegrityError):
                insert_row(connection, "incident_memory_entry", **an_entry(incident_memory_entry_id=f"bad-{column}", investigation_id=f"bad-{column}", **{column: value}))


def test_an_investigation_has_one_entry(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "incident_memory_entry", **an_entry())
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "incident_memory_entry", **an_entry(incident_memory_entry_id="entry-2"))


def test_a_key_kind_outside_the_enum_is_refused_and_one_key_is_stored_once_per_entry(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "incident_memory_entry", **an_entry())
        key = dict(incident_memory_entry_id="entry-1", key_kind="service", key_value_hash="a" * 64, key_display_text="claims-api")
        insert_row(connection, "incident_memory_key", **key)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "incident_memory_key", **key)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "incident_memory_key", **{**key, "key_kind": "invented", "key_value_hash": "b" * 64})


def test_a_person_answers_once_per_suggestion_and_only_relevant_or_not_relevant(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "incident_memory_entry", **an_entry())
        feedback = dict(relevance_feedback_id="f-1", investigation_id="investigation-2", incident_memory_entry_id="entry-1", user_principal_name="a@example.com", relevance_verdict="relevant", recorded_at=NOW)
        insert_row(connection, "incident_memory_relevance_feedback", **feedback)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "incident_memory_relevance_feedback", **{**feedback, "relevance_feedback_id": "f-2"})
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "incident_memory_relevance_feedback", **{**feedback, "relevance_feedback_id": "f-3", "user_principal_name": "b@example.com", "relevance_verdict": "maybe"})


def test_the_downgrade_drops_the_tables(database: Path) -> None:
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'incident_memory_%'").fetchone() is None


def test_the_sql_server_script_creates_the_tables_with_their_checks_and_cascades() -> None:
    script = sql_server_script(PREVIOUS_REVISION, REVISION)
    assert "CREATE TABLE keigan.incident_memory_entry" in script and "CREATE TABLE keigan.incident_memory_key" in script and "CREATE TABLE keigan.incident_memory_relevance_feedback" in script
    assert "ck_incident_memory_key_key_kind_values CHECK (key_kind IN ('service', 'shared_resource', 'alert_rule', 'error_signature', 'change_operation', 'dependency_target', 'incident_category'))" in script
    assert "uq_incident_memory_entry_investigation_id" in script

"""Decision trace (spec 28): the trace step table, the usage-record link and its index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "d3f8b1a4c7e9"
DECISION_TRACE_REVISION = "c8a2e4f6b1d3"


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def test_the_table_the_column_and_the_index_are_added_and_earlier_usage_rows_keep_working(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        assert "investigation_trace_step_id" not in column_names(connection, "llm_usage_record")
        insert_row(connection, "llm_usage_record", llm_usage_record_id="earlier", feature_name="triage", provider_name="gemini", model_name="m", model_tier="fast", outcome_status="succeeded")
    run_alembic("upgrade", DECISION_TRACE_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert {"trace_step_id", "investigation_id", "sequence_number", "step_kind", "raw_output_json", "adjustments_json", "input_manifest_json"} <= set(column_names(connection, "investigation_trace_step"))
        assert connection.execute("SELECT investigation_trace_step_id FROM llm_usage_record WHERE llm_usage_record_id = 'earlier'").fetchone() == (None,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'ix_llm_usage_record_investigation_id'").fetchone() is not None


def test_a_step_is_deleted_with_its_investigation_and_the_order_is_unique(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", DECISION_TRACE_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "investigation", investigation_id="investigation-1", application_id="application-1")
        step = dict(investigation_id="investigation-1", stage_name="triage", step_kind="inputs", step_status="succeeded")
        insert_row(connection, "investigation_trace_step", trace_step_id="step-1", sequence_number=1, **step)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "investigation_trace_step", trace_step_id="step-2", sequence_number=1, **step)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "investigation_trace_step", trace_step_id="step-3", sequence_number=2, **{**step, "step_kind": "not_a_kind"})
        connection.execute("DELETE FROM investigation WHERE investigation_id = 'investigation-1'")
        assert connection.execute("SELECT COUNT(*) FROM investigation_trace_step").fetchone() == (0,)


def test_the_downgrade_removes_everything(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", DECISION_TRACE_REVISION, database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert "investigation_trace_step_id" not in column_names(connection, "llm_usage_record")
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'investigation_trace_step'").fetchone() is None


def test_the_sql_server_script_creates_the_table_with_its_checks_the_column_and_the_index() -> None:
    script = sql_server_script(PREVIOUS_REVISION, DECISION_TRACE_REVISION)
    assert "CREATE TABLE keigan.investigation_trace_step" in script
    assert "CONSTRAINT ck_investigation_trace_step_step_kind_values CHECK (step_kind IN ('inputs', 'ai_call', 'evidence', 'decision', 'outcome'))" in script
    assert "ALTER TABLE keigan.llm_usage_record ADD investigation_trace_step_id" in script
    assert "CREATE INDEX ix_llm_usage_record_investigation_id ON keigan.llm_usage_record (investigation_id)" in script

"""Honest outcomes (spec 27): new columns and the coverage-gap table, and the backfill of what Keigan's own code wrote into evidence rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "b8d4f2a6c0e3"
HONEST_OUTCOMES_REVISION = "d3f8b1a4c7e9"
NEW_COLUMNS = {
    "investigation_hypothesis": {"hypothesis_state", "proposed_hypothesis_state", "state_guard_code", "state_reason_markdown"},
    "investigation": {"investigation_outcome", "proposed_investigation_outcome", "outcome_guard_code", "outcome_reason_markdown", "leading_perspective_reason_markdown"},
    "investigation_evidence": {"check_outcome", "baseline_comparison"},
}


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def add_evidence(connection: sqlite3.Connection, code: str, *, summary: str, category: str, matched: int) -> None:
    insert_row(
        connection, "investigation_evidence", evidence_id=f"evidence-{code}", investigation_id="investigation-1", evidence_code=code, evidence_source_kind="log_analytics",
        evidence_category=category, evidence_title=f"Evidence {code}", evidence_summary=summary, matched_record_count=matched,
    )


def test_the_columns_and_the_gap_table_are_added_and_earlier_rows_keep_working(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        for table, columns in NEW_COLUMNS.items():
            assert not columns & set(column_names(connection, table))
    run_alembic("upgrade", HONEST_OUTCOMES_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        for table, columns in NEW_COLUMNS.items():
            assert columns <= set(column_names(connection, table))
        assert {"coverage_gap_id", "investigation_id", "gap_kind", "reason_code", "service_name", "source_kind", "parameters_json"} <= set(column_names(connection, "investigation_coverage_gap"))


def test_evidence_written_before_the_revision_gets_a_check_outcome_and_a_baseline_comparison_from_its_text(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "investigation", investigation_id="investigation-1", application_id="application-1")
        add_evidence(connection, "E1", summary="Not available: the workspace refused access. Keigan cannot rule this source in or out.", category="error_logs", matched=0)
        add_evidence(connection, "E2", summary="Rule-out: no errors beyond the usual background rate.", category="error_logs", matched=3)
        add_evidence(connection, "E3", summary="Latency was normal.", category="latency", matched=0)
        add_evidence(connection, "E4", summary="Error rate rose from 0.2 to 8 percent.", category="error_logs", matched=412)
        add_evidence(connection, "E5", summary="A deployment ran 4 minutes before the first alert.", category="change_event", matched=1)
        add_evidence(connection, "E6", summary="2 of 5 probes failed.", category="synthetic_probe", matched=5)
    run_alembic("upgrade", HONEST_OUTCOMES_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        rows = dict((code, (outcome, baseline)) for code, outcome, baseline in connection.execute("SELECT evidence_code, check_outcome, baseline_comparison FROM investigation_evidence"))
    assert rows == {
        "E1": ("not_checked", "compared"), "E2": ("no_signal", "compared"), "E3": ("no_signal", "compared"), "E4": ("signal", "compared"),
        "E5": ("signal", "no_baseline_for_source"), "E6": ("signal", "no_baseline_for_source"),
    }


def test_an_earlier_investigation_has_no_state_and_no_outcome(database_before_the_revision: Path) -> None:
    with sqlite3.connect(database_before_the_revision) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "investigation", investigation_id="investigation-1", application_id="application-1")
        insert_row(connection, "investigation_hypothesis", hypothesis_id="hypothesis-1", investigation_id="investigation-1", analysis_perspective="application", hypothesis_title="A")
    run_alembic("upgrade", HONEST_OUTCOMES_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert connection.execute("SELECT investigation_outcome, outcome_guard_code FROM investigation").fetchone() == (None, None)
        assert connection.execute("SELECT hypothesis_state, state_guard_code FROM investigation_hypothesis").fetchone() == (None, None)


def test_the_downgrade_removes_the_columns_and_the_table(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", HONEST_OUTCOMES_REVISION, database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        for table, columns in NEW_COLUMNS.items():
            assert not columns & set(column_names(connection, table))
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'investigation_coverage_gap'").fetchone() is None


def test_the_sql_server_script_adds_the_columns_with_their_check_constraints_and_the_table() -> None:
    script = sql_server_script(PREVIOUS_REVISION, HONEST_OUTCOMES_REVISION)
    for table, columns in NEW_COLUMNS.items():
        for column in columns:
            assert f"ALTER TABLE keigan.{table} ADD {column}" in script
    assert "CONSTRAINT ck_investigation_investigation_outcome_values CHECK (investigation_outcome IN ('cause_identified', 'inconclusive', 'cause_not_visible'))" in script
    assert "CREATE TABLE keigan.investigation_coverage_gap" in script
    assert "UPDATE keigan.investigation_evidence SET check_outcome = 'not_checked' WHERE evidence_summary LIKE 'Not available:%'" in script

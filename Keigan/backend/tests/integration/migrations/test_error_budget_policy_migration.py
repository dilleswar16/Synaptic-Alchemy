"""Error budget policy (spec 30): the three tables, their checks and the filtered unique indexes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "e7b3a9d1c5f2"
REVISION = "f4a8c2e6b0d7"


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", REVISION, database_file=path)
    return path


def a_breach(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = dict(
        error_budget_policy_breach_id="b-1", application_id="application-1", breach_kind="budget_exhausted", slo_id="slo-1", window_days=30, detected_at="2026-11-23 00:00:00",
        requirement_status="open", requirement_changed_at="2026-11-23 00:00:00", is_provisional=0, created_at="2026-11-23 00:00:00", updated_at="2026-11-23 00:00:00",
    )
    values.update(overrides)
    return values


def test_the_three_tables_exist(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"error_budget_policy", "incident_budget_impact", "error_budget_policy_breach"} <= names


def test_a_kind_or_status_outside_the_enum_is_refused(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        for column, value in (("breach_kind", "invented"), ("requirement_status", "pending")):
            with pytest.raises(sqlite3.IntegrityError):
                insert_row(connection, "error_budget_policy_breach", **a_breach(error_budget_policy_breach_id=f"bad-{column}", **{column: value}))


def test_only_one_open_breach_per_exhausted_slo_and_one_single_incident_breach_per_incident(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        insert_row(connection, "application", application_id="application-1")
        insert_row(connection, "error_budget_policy_breach", **a_breach())
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "error_budget_policy_breach", **a_breach(error_budget_policy_breach_id="b-2"))
        insert_row(connection, "error_budget_policy_breach", **a_breach(error_budget_policy_breach_id="b-3", requirement_status="ended"))  # a closed one does not count


def test_the_downgrade_drops_the_tables(database: Path) -> None:
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'incident_budget_impact'").fetchone() is None


def test_the_sql_server_script_replaces_the_action_item_source_check_and_creates_the_filtered_indexes() -> None:
    script = sql_server_script(PREVIOUS_REVISION, REVISION)
    assert "CREATE TABLE keigan.error_budget_policy_breach" in script
    assert "ck_action_item_item_source_kind_values CHECK (item_source_kind IN ('postmortem', 'manual', 'error_budget_policy'))" in script
    assert "uq_error_budget_policy_breach_open_exhausted" in script and "WHERE breach_kind = 'budget_exhausted' AND requirement_status = 'open'" in script

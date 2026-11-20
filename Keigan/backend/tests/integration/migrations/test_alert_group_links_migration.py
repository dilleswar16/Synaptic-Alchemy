"""H14 migration: alert group, investigation and incident links that disagreed are repaired, and investigation.alert_group_id (the duplicate) is dropped."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "a3f5c0d1e2b4"
LINKS_REVISION = "b7d2e9a4c6f1"


def build_old_database(directory: Path) -> Path:
    """Rows the old code could leave behind: two-way links that were only set on one side, or that named different incidents."""
    database_file = database_at(directory, PREVIOUS_REVISION)
    with sqlite3.connect(database_file) as connection:
        insert_row(connection, "application", application_id="app-1", application_code="APP1")
        for incident_id in ("inc-a", "inc-b"):
            insert_row(connection, "incident", incident_id=incident_id, application_id="app-1")
        # group has no pointer, the investigation names the group as its origin
        insert_row(connection, "investigation", investigation_id="inv-origin", application_id="app-1", alert_group_id="grp-origin")
        insert_row(connection, "alert_group", alert_group_id="grp-origin", application_id="app-1")
        # the investigation has an incident, the group has none
        insert_row(connection, "investigation", investigation_id="inv-1", application_id="app-1", incident_id="inc-a")
        insert_row(connection, "alert_group", alert_group_id="grp-1", application_id="app-1", investigation_id="inv-1")
        # the group has an incident, the investigation has none
        insert_row(connection, "investigation", investigation_id="inv-2", application_id="app-1")
        insert_row(connection, "alert_group", alert_group_id="grp-2", application_id="app-1", investigation_id="inv-2", incident_id="inc-b")
        # both name different incidents
        insert_row(connection, "investigation", investigation_id="inv-3", application_id="app-1", incident_id="inc-a")
        insert_row(connection, "alert_group", alert_group_id="grp-3", application_id="app-1", investigation_id="inv-3", incident_id="inc-b")
        # two groups share one investigation that has no incident
        insert_row(connection, "investigation", investigation_id="inv-5", application_id="app-1")
        insert_row(connection, "alert_group", alert_group_id="grp-5a", application_id="app-1", investigation_id="inv-5", incident_id="inc-b")
        insert_row(connection, "alert_group", alert_group_id="grp-5b", application_id="app-1", investigation_id="inv-5")
        # a group that already has an investigation keeps it; the origin pointer of another investigation is dropped with the column
        insert_row(connection, "investigation", investigation_id="inv-6", application_id="app-1")
        insert_row(connection, "investigation", investigation_id="inv-6-other", application_id="app-1", alert_group_id="grp-6")
        insert_row(connection, "alert_group", alert_group_id="grp-6", application_id="app-1", investigation_id="inv-6")
    return database_file


@pytest.fixture
def old_database(tmp_path: Path) -> Path:
    return build_old_database(tmp_path)


@pytest.fixture(scope="module")
def upgraded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database_file = build_old_database(tmp_path_factory.mktemp("links"))
    run_alembic("upgrade", LINKS_REVISION, database_file=database_file)
    return database_file


def group_links(database_file: Path) -> dict[str, tuple[str | None, str | None]]:
    with sqlite3.connect(database_file) as connection:
        return {row[0]: (row[1], row[2]) for row in connection.execute("SELECT alert_group_id, investigation_id, incident_id FROM alert_group")}


def investigation_incidents(database_file: Path) -> dict[str, str | None]:
    with sqlite3.connect(database_file) as connection:
        return dict(connection.execute("SELECT investigation_id, incident_id FROM investigation").fetchall())


def test_a_group_without_a_pointer_gets_the_investigation_that_named_it(upgraded_database: Path) -> None:
    assert group_links(upgraded_database)["grp-origin"] == ("inv-origin", None)


def test_the_group_follows_the_incident_of_its_investigation_and_the_investigation_takes_the_incident_of_its_group(upgraded_database: Path) -> None:
    links, incidents = group_links(upgraded_database), investigation_incidents(upgraded_database)
    assert links["grp-1"] == ("inv-1", "inc-a")
    assert links["grp-2"] == ("inv-2", "inc-b") and incidents["inv-2"] == "inc-b"
    assert links["grp-3"] == ("inv-3", "inc-a")  # the investigation's incident wins: it is a real foreign key the incident room already shows
    assert links["grp-5a"] == ("inv-5", "inc-b") and links["grp-5b"] == ("inv-5", "inc-b") and incidents["inv-5"] == "inc-b"
    assert links["grp-6"] == ("inv-6", None)


def test_no_group_disagrees_with_its_investigation_after_the_repair(upgraded_database: Path) -> None:
    with sqlite3.connect(upgraded_database) as connection:
        disagreements = connection.execute(
            "SELECT alert_group.alert_group_id FROM alert_group JOIN investigation ON investigation.investigation_id = alert_group.investigation_id WHERE alert_group.incident_id IS NOT investigation.incident_id"
        ).fetchall()
    assert disagreements == []


def test_the_duplicate_column_and_its_index_are_gone_and_no_row_was_lost(upgraded_database: Path) -> None:
    with sqlite3.connect(upgraded_database) as connection:
        investigation_count = connection.execute("SELECT COUNT(*) FROM investigation").fetchone()[0]
        group_count = connection.execute("SELECT COUNT(*) FROM alert_group").fetchone()[0]
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(investigation)")}
        assert "alert_group_id" not in column_names(connection, "investigation")
    assert (investigation_count, group_count) == (7, 7)
    assert "ix_investigation_alert_group_id" not in indexes


def test_downgrade_restores_the_origin_group_of_each_investigation(old_database: Path) -> None:
    run_alembic("upgrade", LINKS_REVISION, database_file=old_database)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=old_database)
    with sqlite3.connect(old_database) as connection:
        origins = dict(connection.execute("SELECT investigation_id, alert_group_id FROM investigation WHERE alert_group_id IS NOT NULL").fetchall())
    assert origins["inv-origin"] == "grp-origin" and origins["inv-1"] == "grp-1" and origins["inv-5"] == "grp-5a"


def test_the_sql_server_script_repairs_before_it_drops_the_column() -> None:
    """Rendered with Alembic offline mode; the T-SQL was not executed (no SQL Server available)."""
    script = sql_server_script(PREVIOUS_REVISION, LINKS_REVISION)
    repair = "UPDATE keigan.alert_group SET incident_id"
    drop_index = "DROP INDEX ix_investigation_alert_group_id ON keigan.investigation"
    drop_column = "ALTER TABLE keigan.investigation DROP COLUMN alert_group_id"
    assert "UPDATE keigan.alert_group SET investigation_id" in script and repair in script and "UPDATE keigan.investigation SET incident_id" in script
    assert script.index(repair) < script.index(drop_index) < script.index(drop_column)

"""Team members migration: invitation columns, the wider role check, and one person per application per address (stopping first when existing rows break it)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import column_names, database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "d2a6b0c5e8f9"
TEAM_REVISION = "e4c8a1d7b2f6"


def _add_people(database_file: Path, *people: tuple[str, str, str]) -> None:
    """People ``(stakeholder_id, recipient_type, email)`` on one application, as the earlier code could store them (no uniqueness rule, any letter case)."""
    with sqlite3.connect(database_file) as connection:
        insert_row(connection, "application", application_id="app-1", application_code="APP1")
        for stakeholder_id, recipient_type, email_address in people:
            insert_row(connection, "stakeholder", stakeholder_id=stakeholder_id, application_id="app-1", recipient_type=recipient_type, display_name=stakeholder_id, email_address=email_address)


@pytest.fixture
def database_before_the_revision(tmp_path: Path) -> Path:
    return database_at(tmp_path, PREVIOUS_REVISION)


def test_upgrade_adds_the_invitation_columns_and_stores_addresses_in_lower_case(database_before_the_revision: Path) -> None:
    _add_people(database_before_the_revision, ("rui", "person", "Rui.Reader@Example.com"), ("channel", "teams_channel", "Ops@Example.com"))
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        columns = column_names(connection, "stakeholder")
        stored = dict(connection.execute("SELECT stakeholder_id, email_address FROM stakeholder").fetchall())
        invited_at = connection.execute("SELECT invited_at FROM stakeholder WHERE stakeholder_id = 'rui'").fetchone()[0]
    assert {"invited_at", "invited_by_user_principal_name", "last_invitation_sent_at", "joined_at"} <= columns
    assert stored == {"rui": "rui.reader@example.com", "channel": "ops@example.com"}
    assert invited_at is None, "existing people must read as listed, not as invited"


def test_upgrade_stops_when_two_people_of_one_application_share_an_address_in_any_letter_case(database_before_the_revision: Path) -> None:
    _add_people(database_before_the_revision, ("first", "person", "same@example.com"), ("second", "person", "SAME@example.com"))
    with pytest.raises(AssertionError, match="two people of one application share an email address"):
        run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        assert "invited_at" not in column_names(connection, "stakeholder"), "the migration changed the database although it stopped"


def test_a_distribution_list_and_a_person_may_share_an_address_but_two_people_may_not(database_before_the_revision: Path) -> None:
    _add_people(database_before_the_revision, ("person", "person", "team@example.com"), ("list", "distribution_list", "team@example.com"))
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "stakeholder", stakeholder_id="third", application_id="app-1", recipient_type="person", display_name="third", email_address="team@example.com")


def test_the_sql_server_script_replaces_the_role_check_with_the_four_new_roles() -> None:
    script = sql_server_script(PREVIOUS_REVISION, TEAM_REVISION)
    assert "ALTER TABLE keigan.stakeholder DROP CONSTRAINT ck_stakeholder_stakeholder_role_values" in script
    assert "CHECK (stakeholder_role IN ('sre', 'developer', 'manager', 'executive', 'business_owner', 'vendor_contact', 'lead', 'infra', 'devops', 'tester'))" in script
    assert "CREATE UNIQUE INDEX uq_stakeholder_application_email ON keigan.stakeholder (application_id, email_address) WHERE email_address IS NOT NULL AND recipient_type = 'person'" in script
    assert script.index("THROW 50000") < script.index("ALTER TABLE keigan.stakeholder ADD invited_at"), "the duplicate check must run before anything is changed"


def test_downgrade_removes_the_columns_and_the_index(database_before_the_revision: Path) -> None:
    run_alembic("upgrade", "head", database_file=database_before_the_revision)
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database_before_the_revision)
    with sqlite3.connect(database_before_the_revision) as connection:
        index_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "invited_at" not in column_names(connection, "stakeholder")
    assert "uq_stakeholder_application_email" not in index_names

"""Similar incident memory (spec 34, phase 4): the table that says which remembered incidents were given to an investigation's AI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from support.schema_revisions import database_at, insert_row, run_alembic, sql_server_script

PREVIOUS_REVISION = "e6b2d8f4a0c3"
REVISION = "f7c3e9a1b5d2"


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = database_at(tmp_path, PREVIOUS_REVISION)
    run_alembic("upgrade", REVISION, database_file=path)
    return path


def test_a_remembered_incident_is_referenced_once_per_investigation(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        row = dict(investigation_id="investigation-1", incident_memory_entry_id="entry-1", position=0)
        insert_row(connection, "investigation_memory_reference", **row)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(connection, "investigation_memory_reference", **row)
        insert_row(connection, "investigation_memory_reference", **{**row, "incident_memory_entry_id": "entry-2", "position": 1})


def test_the_downgrade_drops_the_table(database: Path) -> None:
    run_alembic("downgrade", PREVIOUS_REVISION, database_file=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'investigation_memory_reference'").fetchone() is None


def test_the_sql_server_script_cascades_from_the_investigation_but_not_from_the_entry() -> None:
    script = sql_server_script(PREVIOUS_REVISION, REVISION)
    assert "CREATE TABLE keigan.investigation_memory_reference" in script
    assert "fk_investigation_memory_reference_investigation_id_investigation FOREIGN KEY(investigation_id) REFERENCES keigan.investigation (investigation_id) ON DELETE CASCADE" in script
    entry_key = script[script.index("fk_investigation_memory_reference_incident_memory_entry_id_incident_memory_entry"):]
    assert "ON DELETE CASCADE" not in entry_key.split("\n", 1)[0]

"""Schema drift (H21): Alembic migrations, the entities and the Azure SQL scripts must all describe the same database.

A developer who changes an entity and forgets the migration, or the regenerated Azure SQL scripts, fails this suite.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, create_engine, text

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase
from support.schema_revisions import COLUMNS_CHECKED_AFTER_THE_CHECK_REVISION, TABLES_ADDED_AFTER_THE_CHECK_REVISION, column_of_values_check

BACKEND_DIRECTORY = Path(__file__).resolve().parents[3]
AZURE_SQL_DIRECTORY = BACKEND_DIRECTORY.parent / "database" / "azure_sql"
FOREIGN_KEY_REVISION = "c9e4f1b8d3a7"
CHECK_REVISION = "d2a6b0c5e8f9"
GENERATED_SCRIPT_NAMES = ("01_create_schema.sql", "02_create_tables.sql", "03_create_foreign_keys.sql", "04_create_indexes.sql", "05_reference_data.sql", "06_grant_keigan_identity.sql", "run_all.sql")


@pytest.fixture(scope="module")
def migrated_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An empty SQLite file brought to the newest revision by ``alembic upgrade head`` (what the Helm migration job runs)."""
    database_file = tmp_path_factory.mktemp("alembic") / "migrated.db"
    child_environment = {key: value for key, value in os.environ.items() if key != "DATABASE_SCHEMA"}
    child_environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_file.as_posix()}"
    completed = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIRECTORY, env=child_environment, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    return database_file


def revision_module(revision: str):  # noqa: ANN201
    configuration = Config(str(BACKEND_DIRECTORY / "alembic.ini"))
    configuration.set_main_option("script_location", str(BACKEND_DIRECTORY / "migrations"))
    configuration.set_main_option("path_separator", "os")  # no prepend_sys_path splitting warning
    return ScriptDirectory.from_config(configuration).get_revision(revision).module


def foreign_keys_added_by_the_foreign_key_revision() -> list:
    """The keys revision c9e4f1b8d3a7 adds on SQL Server. SQLite cannot add a key to an existing table without a rebuild that cascade-deletes rows,
    so a SQLite database built by ``alembic upgrade head`` lacks exactly these (a fresh ``create_all`` database has them)."""
    return list(revision_module(FOREIGN_KEY_REVISION).FOREIGN_KEYS)


def test_migrations_produce_the_schema_the_entities_describe(migrated_database: Path) -> None:
    engine = create_engine(f"sqlite:///{migrated_database.as_posix()}")
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), EntityBase.metadata)
    engine.dispose()
    sqlite_cannot_add = {(foreign_key.table, foreign_key.column) for foreign_key in foreign_keys_added_by_the_foreign_key_revision()}
    differences = [difference for difference in differences if not (difference[0] == "add_fk" and (difference[1].table.name, difference[1].column_keys[0]) in sqlite_cannot_add)]
    assert differences == [], f"Entities and Alembic migrations disagree; add a migration for: {differences}"


def test_the_foreign_keys_the_revision_adds_are_the_ones_the_entities_declare() -> None:
    """The revision's list (table, column, target, ON DELETE) is typed once in the migration; it must match what the entities say, or SQL Server and fresh databases would differ."""
    for foreign_key in foreign_keys_added_by_the_foreign_key_revision():
        constraints = [
            constraint for constraint in EntityBase.metadata.tables[foreign_key.table].foreign_key_constraints
            if list(constraint.column_keys) == [foreign_key.column] and constraint.referred_table.name == foreign_key.referred_table
        ]
        assert len(constraints) == 1, f"{foreign_key.table}.{foreign_key.column} has no matching foreign key in the entities"
        assert constraints[0].ondelete == foreign_key.ondelete, f"{foreign_key.table}.{foreign_key.column}: ON DELETE differs between the migration and the entity"


def test_the_check_constraints_the_revision_adds_are_the_ones_the_entities_declare() -> None:
    """The revision freezes which columns it covers (the values come from the entities); a new CHECK on an entity needs its own revision."""
    declared = {
        (table.name, constraint.name.removeprefix(f"ck_{table.name}_").removesuffix("_values"))
        for table in EntityBase.metadata.sorted_tables
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name and constraint.name.endswith("_values") and table.name not in TABLES_ADDED_AFTER_THE_CHECK_REVISION
        and column_of_values_check(table.name, constraint.name) not in COLUMNS_CHECKED_AFTER_THE_CHECK_REVISION
    }
    assert set(revision_module(CHECK_REVISION).CONSTRAINED_COLUMNS) == declared


def test_partial_unique_indexes_keep_their_filter_in_the_migrated_database(migrated_database: Path) -> None:
    """Alembic's comparison ignores index filters, so check the ones that carry a business rule directly."""
    engine = create_engine(f"sqlite:///{migrated_database.as_posix()}")
    with engine.connect() as connection:
        index_sql = dict(connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")).all())
    engine.dispose()
    for index_name in ("uq_incident_external_number", "uq_alert_open_fingerprint", "uq_background_job_active_deduplication_key", "uq_stakeholder_application_email", "uq_chat_answer_run_one_running_per_conversation"):
        assert index_name in index_sql, f"{index_name} is missing from the migrated database"
        assert "UNIQUE" in index_sql[index_name].upper() and " WHERE " in index_sql[index_name].upper(), index_sql[index_name]


def _without_generation_timestamp(script_text: str) -> str:
    return re.sub(r"^-- Generated by .* on \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", "-- Generated by <generator>", script_text, flags=re.MULTILINE)


def test_azure_sql_scripts_match_what_the_generator_produces_from_the_entities(tmp_path: Path) -> None:
    child_environment = {key: value for key, value in os.environ.items() if key not in ("DATABASE_URL", "DATABASE_SCHEMA")}
    completed = subprocess.run(
        [sys.executable, str(BACKEND_DIRECTORY / "scripts" / "generate_azure_sql_ddl.py"), str(tmp_path), "keigan"], cwd=BACKEND_DIRECTORY, env=child_environment, capture_output=True, text=True, timeout=180
    )
    assert completed.returncode == 0, completed.stderr
    for script_name in GENERATED_SCRIPT_NAMES:
        committed = _without_generation_timestamp((AZURE_SQL_DIRECTORY / script_name).read_text(encoding="utf-8"))
        regenerated = _without_generation_timestamp((tmp_path / script_name).read_text(encoding="utf-8"))
        assert committed == regenerated, f"database/azure_sql/{script_name} is out of date: run backend/scripts/generate_azure_sql_ddl.py and commit the result"


def test_azure_sql_delta_scripts_match_what_alembic_offline_mode_produces(tmp_path: Path) -> None:
    child_environment = {key: value for key, value in os.environ.items() if key not in ("DATABASE_URL", "DATABASE_SCHEMA")}
    generator = str(BACKEND_DIRECTORY / "scripts" / "generate_azure_sql_migration_scripts.py")
    completed = subprocess.run([sys.executable, generator, str(tmp_path), "keigan"], cwd=BACKEND_DIRECTORY, env=child_environment, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    regenerated_names = sorted(path.name for path in tmp_path.glob("*.sql"))
    committed_names = sorted(path.name for path in (AZURE_SQL_DIRECTORY / "migrations").glob("*.sql"))
    assert regenerated_names == committed_names, "database/azure_sql/migrations is missing a revision or holds a stale one: run backend/scripts/generate_azure_sql_migration_scripts.py"
    for script_name in regenerated_names:
        committed = (AZURE_SQL_DIRECTORY / "migrations" / script_name).read_text(encoding="utf-8")
        assert committed == (tmp_path / script_name).read_text(encoding="utf-8"), f"{script_name} is stale: run backend/scripts/generate_azure_sql_migration_scripts.py"

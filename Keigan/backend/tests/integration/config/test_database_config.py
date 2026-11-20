"""keigan/config/database_config.py: a local SQLite file made by an older Keigan is reported with the fix, not with "no such column"."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from keigan.config.database_config import LocalDatabaseOutOfDateError, describe_missing_columns, find_missing_columns
from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase


@pytest.fixture
def current_database():  # noqa: ANN201
    engine = create_engine("sqlite://")
    EntityBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_a_database_made_from_the_current_entities_is_not_out_of_date(current_database) -> None:  # noqa: ANN001
    with current_database.connect() as connection:
        assert find_missing_columns(connection) == {}


def test_a_column_added_to_an_entity_after_the_file_was_made_is_found(current_database) -> None:  # noqa: ANN001
    with current_database.begin() as connection:
        connection.execute(text("ALTER TABLE stakeholder DROP COLUMN joined_at"))
        connection.execute(text("ALTER TABLE stakeholder DROP COLUMN invited_at"))
    with current_database.connect() as connection:
        assert find_missing_columns(connection) == {"stakeholder": ["invited_at", "joined_at"]}


def test_a_table_the_file_lacks_entirely_is_not_reported_because_create_all_makes_it(current_database) -> None:  # noqa: ANN001
    with current_database.begin() as connection:
        connection.execute(text("DROP TABLE stakeholder_subscribed_service"))
    with current_database.connect() as connection:
        assert find_missing_columns(connection) == {}


def test_the_message_names_the_table_the_columns_and_the_fix() -> None:
    error = LocalDatabaseOutOfDateError(describe_missing_columns({"stakeholder": ["joined_at", "invited_at"]}, "./data/keigan.db"))
    message = str(error)
    assert "stakeholder" in message and "joined_at" in message and "invited_at" in message
    assert "./data/keigan.db" in message and "delete" in message.lower() and "start Keigan again" in message

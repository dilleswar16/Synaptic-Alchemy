"""Alembic environment: async engine from Keigan settings, metadata from every entity module."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from keigan.config.database_config import get_database_engine
from keigan.config.settings import get_settings
from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase

target_metadata = EntityBase.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout (``alembic upgrade head --sql``) for review by a DBA."""
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True, compare_type=True,
        version_table_schema=get_settings().database_schema_or_none,
    )
    with context.begin_transaction():
        context.run_migrations()


def apply_migrations(connection: Connection) -> None:
    database_schema = get_settings().database_schema_or_none
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite needs batch mode for ALTER TABLE
        version_table_schema=database_schema,  # alembic_version lives next to Keigan's tables (e.g. keigan.alembic_version)
        include_schemas=bool(database_schema),
        include_name=lambda name, object_type, _parent: object_type != "schema" or name == database_schema,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    async with get_database_engine().connect() as connection:
        await connection.run_sync(apply_migrations)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

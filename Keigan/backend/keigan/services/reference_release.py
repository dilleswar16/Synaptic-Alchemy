"""Release the rows that still point at rows about to be deleted (H11, H12).

A foreign key declared without ON DELETE (NO ACTION) stops the database from deleting a referenced row. Those keys exist where
SQL Server would otherwise see two cascade paths from an application to the same table. Instead of every delete listing the
referencing tables by hand, this walks the foreign keys in the entity metadata once, so a new reference is released
automatically and the list can never drift from the schema.

Rule per referencing column: a nullable column is set to NULL (the row stays, it just no longer names the deleted row); a column
that cannot be NULL (an association row, a dependency edge) means the row is meaningless without its target, so the row is deleted.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import Column, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase


def columns_that_block_deleting(referenced_column: Column) -> list[Column]:
    """Columns of other tables that reference ``referenced_column`` with NO ACTION (CASCADE and SET NULL keys need no help)."""
    blocking_columns: list[Column] = []
    for table in EntityBase.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            if foreign_key.column is referenced_column and foreign_key.constraint is not None and foreign_key.constraint.ondelete in (None, "NO ACTION"):
                blocking_columns.append(foreign_key.parent)
    return blocking_columns


async def release_references(session: AsyncSession, referenced_attribute: InstrumentedAttribute, referenced_ids: Collection[str]) -> None:
    """Call before deleting the rows whose ``referenced_attribute`` (a primary key) is in ``referenced_ids``."""
    if not referenced_ids:
        return
    referenced_column = referenced_attribute.property.columns[0]
    for blocking_column in columns_that_block_deleting(referenced_column):
        table = blocking_column.table
        if blocking_column.nullable and not blocking_column.primary_key:
            await session.execute(update(table).where(blocking_column.in_(referenced_ids)).values({blocking_column.key: None}))
        else:
            await session.execute(delete(table).where(blocking_column.in_(referenced_ids)))

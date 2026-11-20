"""Generic asynchronous repository (the Spring Data ``JpaRepository`` equivalent)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.base_entity import EntityBase
from keigan.exceptions.keigan_exceptions import NotFoundException

EntityType = TypeVar("EntityType", bound=EntityBase)


class BaseRepository(Generic[EntityType]):
    """CRUD helpers for one entity class. Create domain repositories only when custom queries are needed."""

    def __init__(self, session: AsyncSession, entity_class: type[EntityType]):
        self.session = session
        self.entity_class = entity_class

    async def get_by_id(self, entity_identifier: Any) -> EntityType | None:
        if entity_identifier is None:
            return None
        return await self.session.get(self.entity_class, entity_identifier)

    async def get_required(self, entity_identifier: Any, entity_label: str | None = None) -> EntityType:
        entity = await self.get_by_id(entity_identifier)
        if entity is None:
            readable_label = entity_label or self.entity_class.__tablename__.replace("_", " ")
            raise NotFoundException(f"The {readable_label} was not found.")
        return entity

    async def find_all(
        self,
        *conditions: ColumnElement[bool],
        order_by: Sequence[Any] | Any | None = None,
        limit: int | None = None,
    ) -> list[EntityType]:
        statement = self._filtered_select(*conditions)
        if order_by is not None:
            statement = statement.order_by(*(order_by if isinstance(order_by, (list, tuple)) else [order_by]))
        if limit is not None:
            statement = statement.limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def find_one(self, *conditions: ColumnElement[bool]) -> EntityType | None:
        return (await self.session.scalars(self._filtered_select(*conditions).limit(1))).first()

    async def count(self, *conditions: ColumnElement[bool]) -> int:
        statement = select(func.count()).select_from(self.entity_class)
        if conditions:
            statement = statement.where(*conditions)
        return int((await self.session.scalar(statement)) or 0)

    async def exists(self, *conditions: ColumnElement[bool]) -> bool:
        return await self.find_one(*conditions) is not None

    async def paginate(
        self,
        *conditions: ColumnElement[bool],
        order_by: Sequence[Any] | Any | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EntityType], int]:
        bounded_page_size = max(1, min(page_size, 200))
        bounded_page = max(1, page)
        total_count = await self.count(*conditions)
        statement = self._filtered_select(*conditions)
        if order_by is not None:
            statement = statement.order_by(*(order_by if isinstance(order_by, (list, tuple)) else [order_by]))
        statement = statement.offset((bounded_page - 1) * bounded_page_size).limit(bounded_page_size)
        return list((await self.session.scalars(statement)).all()), total_count

    async def add(self, entity: EntityType) -> EntityType:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_all(self, entities: Sequence[EntityType]) -> list[EntityType]:
        self.session.add_all(list(entities))
        await self.session.flush()
        return list(entities)

    async def delete(self, entity: EntityType) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_where(self, *conditions: ColumnElement[bool]) -> int:
        result = await self.session.execute(delete(self.entity_class).where(*conditions))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def _filtered_select(self, *conditions: ColumnElement[bool]) -> Select[tuple[EntityType]]:
        statement = select(self.entity_class)
        if conditions:
            statement = statement.where(*conditions)
        return statement

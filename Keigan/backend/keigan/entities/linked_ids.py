"""Ordered lists of ids of other Keigan rows, stored as association rows instead of a JSON column (H11).

An association row is ``(owner id, linked id, position)`` with a composite primary key and real foreign keys, so a list can
never hold an id that no longer exists and the database can answer "which incidents touch this service?". ``position``
keeps the list order (the first affected service of an incident is its primary one).

Reading: ``incident.affected_service_ids`` (a read-only property built with :func:`linked_ids_property`).
Writing: ``incident.replace_linked_ids("affected_service_links", service_ids)`` (the only writer, defined once on the mixin).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm.attributes import set_committed_value


class OrderedLinkColumns:
    """Columns every association entity shares. Subclasses add the two id columns and set ``linked_id_attribute``."""

    linked_id_attribute: ClassVar[str]
    position: Mapped[int] = mapped_column(Integer, default=0)


def ordered_links_relationship(link_class_name: str) -> Mapped[list[Any]]:
    """Relationship from an owner to its association rows, in list order.

    ``selectin`` loads the rows with the owner (async sessions cannot lazy-load); ``passive_deletes`` leaves removing the rows
    of a deleted owner to the database's ON DELETE CASCADE."""
    return relationship(link_class_name, order_by=f"{link_class_name}.position", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


def linked_ids_property(relationship_name: str) -> property:
    """Read-only list of the linked ids of one association relationship."""
    return property(lambda owner: owner.linked_ids(relationship_name), doc=f"Linked ids held by {relationship_name}, in list order.")


class LinkedIdsMixin:
    """Gives an owner entity the one way to read and replace the ids held by its association relationships."""

    link_relationship_names: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **column_values: Any) -> None:
        super().__init__(**column_values)
        for relationship_name in self.link_relationship_names:
            if relationship_name not in self.__dict__:
                set_committed_value(self, relationship_name, [])  # mark the empty list as loaded now: a flushed object could not lazy-load it in an async session

    def linked_ids(self, relationship_name: str) -> list[str]:
        links = getattr(self, relationship_name)
        return [getattr(link, type(link).linked_id_attribute) for link in links]

    def replace_linked_ids(self, relationship_name: str, identifiers: Iterable[str | None]) -> None:
        """Make the list exactly ``identifiers`` (duplicates and empty values dropped, order kept)."""
        links = getattr(self, relationship_name)
        link_class = type(self).__mapper__.relationships[relationship_name].mapper.class_
        id_attribute = link_class.linked_id_attribute
        wanted_identifiers = list(dict.fromkeys(identifier for identifier in identifiers if identifier))
        existing_links = {getattr(link, id_attribute): link for link in links}
        links[:] = [
            existing_links[identifier] if identifier in existing_links else link_class(**{id_attribute: identifier})
            for identifier in wanted_identifiers
        ]
        for position, link in enumerate(links):
            link.position = position

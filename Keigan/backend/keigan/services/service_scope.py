"""Which of the services a user named really belong to the application (one query, shared by every form that takes a list of service ids)."""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.application_entities import MonitoredService


async def unknown_service_ids(session: AsyncSession, application_id: str, service_ids: Collection[str] | None) -> set[str]:
    """The ids in ``service_ids`` that are not services of ``application_id`` (an empty or missing list has none)."""
    if not service_ids:
        return set()
    known_ids = set((await session.scalars(select(MonitoredService.service_id).where(MonitoredService.application_id == application_id, MonitoredService.service_id.in_(service_ids)))).all())
    return set(service_ids) - known_ids

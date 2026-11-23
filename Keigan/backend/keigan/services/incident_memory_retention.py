"""Removing the memory of incidents that are deleted (spec 34, 4.2): an entry lives exactly as long as the investigation it was built from.

Called before the investigations are deleted, by incident retention and by application deletion. Children go first (answers about the entry, then its keys, then the entry), in an order that is
valid with or without ON DELETE CASCADE.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryKey, IncidentMemoryRelevanceFeedback


async def delete_incident_memory(session: AsyncSession, investigation_ids: Any) -> int:
    """Delete the entries built from these investigations (a list of ids or a ``select`` of them), with their keys and every answer about them. Returns the entries removed."""
    entry_ids = select(IncidentMemoryEntry.incident_memory_entry_id).where(IncidentMemoryEntry.investigation_id.in_(investigation_ids))
    await session.execute(delete(IncidentMemoryRelevanceFeedback).where(
        or_(IncidentMemoryRelevanceFeedback.investigation_id.in_(investigation_ids), IncidentMemoryRelevanceFeedback.incident_memory_entry_id.in_(entry_ids))
    ))
    await session.execute(delete(IncidentMemoryKey).where(IncidentMemoryKey.incident_memory_entry_id.in_(entry_ids)))
    return (await session.execute(delete(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id.in_(investigation_ids)))).rowcount or 0

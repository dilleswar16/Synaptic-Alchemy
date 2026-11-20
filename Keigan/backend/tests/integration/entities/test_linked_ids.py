"""keigan/entities/linked_ids.py (H11): lists of ids of other Keigan rows live in association tables with real foreign keys."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Incident, IncidentAffectedService


async def new_incident(session, application_id: str, service_ids: list[str]) -> Incident:
    incident = Incident(application_id=application_id, incident_title="Linked ids", incident_status="new")
    incident.replace_linked_ids("affected_service_links", service_ids)
    session.add(incident)
    await session.flush()
    return incident


async def test_the_list_comes_back_in_the_order_it_was_written(seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    wanted = [seed_context.service_id("CLMJP", name) for name in ("claims-nightly-etl", "claims-api")]
    async with open_session() as session:
        incident = await new_incident(session, clmjp, wanted)
        incident_id = incident.incident_id
    async with open_session() as session:
        reloaded = await session.get(Incident, incident_id)
        assert reloaded.affected_service_ids == wanted


async def test_replacing_the_list_drops_duplicates_empty_values_and_removed_ids(seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    first, second, third = (seed_context.service_id("CLMJP", name) for name in ("claims-nightly-etl", "claims-api", "claims-sql"))
    async with open_session() as session:
        incident = await new_incident(session, clmjp, [first, second])
        incident.replace_linked_ids("affected_service_links", [third, first, first, None, ""])
        await session.flush()
        incident_id = incident.incident_id
    async with open_session() as session:
        rows = (await session.execute(select(IncidentAffectedService.service_id, IncidentAffectedService.position).where(IncidentAffectedService.incident_id == incident_id).order_by(IncidentAffectedService.position))).all()
    assert rows == [(third, 0), (first, 1)]


async def test_the_database_rejects_a_service_that_does_not_exist(seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    with pytest.raises(IntegrityError):
        async with open_session() as session:
            await new_incident(session, clmjp, ["no-such-service"])


async def test_deleting_the_incident_removes_its_links(seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        incident = await new_incident(session, clmjp, [seed_context.service_id("CLMJP", "claims-api")])
        incident_id = incident.incident_id
    async with open_session() as session:
        await session.execute(delete(Incident).where(Incident.incident_id == incident_id))
    async with open_session() as session:
        remaining = await session.scalar(select(func.count()).select_from(IncidentAffectedService).where(IncidentAffectedService.incident_id == incident_id))
    assert remaining == 0

"""keigan/services/alert_group_link_service.py (H14): one place links an alert group to its investigation and incident, and disagreement is refused."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import AlertGroup
from keigan.entities.incident_entities import Incident, Investigation
from keigan.exceptions.keigan_exceptions import ConflictException, NotFoundException
from keigan.services.alert_group_link_service import AlertGroupLinkService

pytestmark = pytest.mark.usefixtures("seed_context")


async def make_rows(session, application_id: str) -> tuple[AlertGroup, Investigation, Incident]:
    group = AlertGroup(application_id=application_id, group_title="Linked group")
    investigation = Investigation(application_id=application_id)
    incident = Incident(application_id=application_id, incident_title="Linked incident")
    session.add_all([group, investigation, incident])
    await session.flush()
    return group, investigation, incident


async def test_linking_an_investigation_and_an_incident_sets_every_side(seed_context) -> None:
    async with open_session() as session:
        group, investigation, incident = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        await AlertGroupLinkService(session).link(group, investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        assert (group.investigation_id, group.incident_id, investigation.incident_id) == (investigation.investigation_id, incident.incident_id, incident.incident_id)


async def test_a_group_linked_to_an_investigation_that_has_an_incident_gets_that_incident(seed_context) -> None:
    async with open_session() as session:
        group, investigation, incident = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        investigation.incident_id = incident.incident_id
        await AlertGroupLinkService(session).link(group, investigation_id=investigation.investigation_id)
        assert group.incident_id == incident.incident_id


async def test_linking_an_incident_to_a_group_updates_the_incident_of_its_investigation(seed_context) -> None:
    async with open_session() as session:
        group, investigation, incident = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        service = AlertGroupLinkService(session)
        await service.link(group, investigation_id=investigation.investigation_id)
        await service.link(group, incident_id=incident.incident_id)
        assert investigation.incident_id == incident.incident_id and group.incident_id == incident.incident_id


async def test_linking_the_same_rows_twice_changes_nothing(seed_context) -> None:
    async with open_session() as session:
        group, investigation, incident = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        service = AlertGroupLinkService(session)
        await service.link(group, investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        await service.link(group, investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        assert (group.investigation_id, group.incident_id) == (investigation.investigation_id, incident.incident_id)


async def test_an_incident_that_disagrees_with_the_investigation_of_the_group_is_refused(seed_context) -> None:
    async with open_session() as session:
        group, investigation, incident = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        other_incident = Incident(application_id=group.application_id, incident_title="Other incident")
        session.add(other_incident)
        await session.flush()
        service = AlertGroupLinkService(session)
        await service.link(group, investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        with pytest.raises(ConflictException) as refusal:
            await service.link(group, incident_id=other_incident.incident_id)
        assert "different incidents" in str(refusal.value.detail)
        assert (group.incident_id, investigation.incident_id) == (incident.incident_id, incident.incident_id)


async def test_an_investigation_of_another_incident_is_refused_for_a_group_that_has_an_incident(seed_context) -> None:
    async with open_session() as session:
        group, investigation, incident = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        other_investigation = Investigation(application_id=group.application_id, incident_id=incident.incident_id)
        other_incident = Incident(application_id=group.application_id, incident_title="Other incident")
        session.add_all([other_investigation, other_incident])
        await session.flush()
        group.incident_id = other_incident.incident_id
        with pytest.raises(ConflictException):
            await AlertGroupLinkService(session).link(group, investigation_id=other_investigation.investigation_id)
        assert group.investigation_id is None


async def test_a_group_that_has_an_investigation_cannot_get_a_second_one(seed_context) -> None:
    async with open_session() as session:
        group, investigation, _ = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        second_investigation = Investigation(application_id=group.application_id)
        session.add(second_investigation)
        await session.flush()
        service = AlertGroupLinkService(session)
        await service.link(group, investigation_id=investigation.investigation_id)
        with pytest.raises(ConflictException) as refusal:
            await service.link(group, investigation_id=second_investigation.investigation_id)
        assert "already covered by another investigation" in str(refusal.value.detail)


async def test_rows_of_another_application_are_refused(seed_context) -> None:
    async with open_session() as session:
        group, _, _ = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        foreign_investigation = Investigation(application_id=seed_context.application_ids_by_code["CHAD"])
        session.add(foreign_investigation)
        await session.flush()
        with pytest.raises(ConflictException) as refusal:
            await AlertGroupLinkService(session).link(group, investigation_id=foreign_investigation.investigation_id)
        assert "same application" in str(refusal.value.detail)


async def test_an_unknown_investigation_is_reported_as_not_found(seed_context) -> None:
    async with open_session() as session:
        group, _, _ = await make_rows(session, seed_context.application_ids_by_code["CLMJP"])
        with pytest.raises(NotFoundException):
            await AlertGroupLinkService(session).link(group, investigation_id="no-such-investigation")


async def test_no_alert_group_in_the_database_disagrees_with_its_investigation(seed_context) -> None:
    """The seeded data went through the alert pipeline, the incident poller and the investigation flows: none of them may leave a disagreement."""
    async with open_session() as session:
        disagreements = (await session.execute(text(
            "SELECT alert_group.alert_group_id FROM alert_group JOIN investigation ON investigation.investigation_id = alert_group.investigation_id "
            "WHERE alert_group.incident_id IS NOT investigation.incident_id"
        ))).all()
    assert disagreements == []

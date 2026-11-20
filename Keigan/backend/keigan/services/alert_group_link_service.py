"""The one place that links an alert group to the investigation that covers it and the incident it belongs to (H14).

Source of truth: the alert group's own ``investigation_id`` and ``incident_id`` (real foreign keys). Several groups can share one
investigation or one incident (a new group of an open incident joins that incident's investigation), so the group is the side that
says what covers it; an investigation does not store which group it came from. The one remaining duplicate is the incident that
both the group and its investigation name. Every write goes through :meth:`AlertGroupLinkService.link`, which refuses a
combination where they would name different incidents, so the two can never disagree.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.alert_entities import AlertGroup
from keigan.entities.incident_entities import Incident, Investigation
from keigan.exceptions.keigan_exceptions import ConflictException, NotFoundException


class AlertGroupLinkService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def link(self, alert_group: AlertGroup, *, investigation_id: str | None = None, incident_id: str | None = None) -> None:
        """Link ``alert_group`` to an investigation and/or an incident, keeping every side consistent.

        Raises NotFoundException for an unknown row and ConflictException when the rows belong to different applications, the group
        already has another investigation, or the group, its investigation and the incident would name different incidents."""
        if investigation_id and alert_group.investigation_id and investigation_id != alert_group.investigation_id:
            raise ConflictException("This alert group is already covered by another investigation. A group has one investigation; open that one instead.")
        investigation = await self._load(Investigation, investigation_id or alert_group.investigation_id, "investigation")
        incident = await self._load(Incident, incident_id, "incident")
        for linked_row in (investigation, incident):
            if linked_row is not None and linked_row.application_id != alert_group.application_id:
                raise ConflictException("The alert group, its investigation and its incident must belong to the same application.")
        named_incident_ids = {identifier for identifier in (incident_id, alert_group.incident_id, investigation.incident_id if investigation else None) if identifier}
        if len(named_incident_ids) > 1:
            raise ConflictException("The alert group and its investigation belong to different incidents, so they cannot be linked to this one. Open the incident the investigation belongs to instead.")
        resolved_incident_id = next(iter(named_incident_ids), None)
        if investigation is not None:
            alert_group.investigation_id = investigation.investigation_id
            investigation.incident_id = resolved_incident_id
        alert_group.incident_id = resolved_incident_id

    async def _load(self, entity_class: type[Investigation] | type[Incident], identifier: str | None, noun: str) -> Investigation | Incident | None:
        if not identifier:
            return None
        row = await self.session.get(entity_class, identifier)
        if row is None:
            raise NotFoundException(f"The {noun} was not found.")
        return row

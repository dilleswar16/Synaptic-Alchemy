"""When two incidents are 'the same kind' (spec 29 and 30): the same category on the same primary service. One definition, used by the predictive detector and the error budget policy."""

from __future__ import annotations

from keigan.entities.incident_entities import Incident

UNCLASSIFIED = "unclassified"


def recurrence_key(incident: Incident) -> tuple[str, str]:
    """(category, first affected service id). The service id is empty when the incident names no service; such incidents are never grouped."""
    return (incident.incident_category or UNCLASSIFIED, (incident.affected_service_ids or [""])[0])

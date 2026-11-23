"""Similar past incidents as the API sends and receives them (spec 34, 4.7). No score is returned: it means nothing to a person, and the order carries it."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel
from keigan.entities.status_values import IncidentMemoryRelevanceVerdict


class MemoryApplicationDto(ApiModel):
    application_id: str
    application_name: str


class MatchReasonDto(ApiModel):
    key_kind: str
    display_text: str


class SimilarIncidentDto(ApiModel):
    memory_entry_id: str
    application: MemoryApplicationDto
    is_same_application: bool
    incident_id: str | None = None
    incident_number: str | None = None
    incident_title: str
    investigation_id: str
    occurred_at: datetime
    age_days: int
    verdict: str | None = None  # the admin's verdict on that investigation; null = not reviewed
    cause_text: str | None = None  # not sent when that investigation's own analysis was marked incorrect
    cause_source: str
    fix_text: str | None = None
    fix_source: str
    match_reasons: list[MatchReasonDto] = Field(default_factory=list)
    is_rejected: bool = False  # an admin marked that past analysis incorrect: listed apart, labelled
    is_stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
    my_relevance_verdict: str | None = None
    can_hide: bool = False


class SimilarIncidentsResponse(ApiModel):
    items: list[SimilarIncidentDto] = Field(default_factory=list)
    is_available: bool = True  # false while the investigation is still running: matching needs its evidence


class RelevanceRequest(ApiModel):
    verdict: IncidentMemoryRelevanceVerdict


class HideMemoryRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=500)

"""What the model may send to an Ask Keigan tool (spec 23, section 5.1).

Closed schemas (``extra="forbid"``): every field is described for the model and every text and list has a length limit. They live in ``ai`` so the
tool registry, the tool implementations and the offline mock planner share one definition.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from keigan.entities.status_values import (
    AlertGroupStatus, IncidentSource, IncidentStatus, InvestigationStatus, Priority, SignalSeverity, SignalStatus, SloHealthStatus, StakeholderRole,
)

ApplicationCode = Annotated[str, Field(max_length=40, description="Code of one application from the list you were given.")]
LookbackHours = Annotated[int, Field(ge=1, le=720, description="How far back to look, in hours (at most 30 days).")]


class SearchKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode
    query: str = Field(min_length=2, max_length=300, description="What to look for, in a few words.")


class QueryLogsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode
    service_name: str = Field(max_length=200, description="Exact service name of this application.")
    question: str = Field(min_length=3, max_length=300, description="What to count or chart, in plain words.")
    lookback_minutes: int = Field(default=60, ge=5, description="How far back the window reaches, in minutes. The window ends now. Very long windows are shortened to the configured maximum.")
    wants_pattern: bool = Field(default=False, description="True for a pattern over time (a chart), false for one number.")
    failures_only: bool = Field(default=True, description="True to count failed requests or errors only.")


class GetEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(max_length=36, description="The investigation the evidence belongs to.")
    evidence_code: str = Field(pattern=r"^[Ee]\d{1,3}$", max_length=4, description="Code of one evidence item of that investigation, for example E3.")


class GetInvestigationTimelineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(max_length=36, description="The investigation whose timeline to read.")


class ListRecentChangesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode
    lookback_hours: LookbackHours = 24


class FindRunbooksInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode
    symptoms: str = Field(min_length=2, max_length=300, description="The symptom or failure, for example 'database connection timeouts'.")
    maximum_results: int = Field(default=3, ge=1, le=5, description="How many runbooks to return at most.")


class GetTopologyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode


class GetSloStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to check. Empty means every application you were given.")
    statuses: list[SloHealthStatus] = Field(default_factory=list, max_length=4, description="Only SLOs in these states. Empty means every state.")


class GetInvestigationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(max_length=36, description="The investigation to open.")


class ListInvestigationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to list. Empty means every application you were given.")
    statuses: list[InvestigationStatus] = Field(default_factory=list, max_length=6, description="Only investigations in these states. Empty means every state.")
    incident_id: str | None = Field(default=None, max_length=36, description="Only the investigations of this incident.")
    lookback_hours: LookbackHours = 168


class ListIncidentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to list. Empty means every application you were given.")
    statuses: list[IncidentStatus] = Field(default_factory=list, max_length=6, description="Only incidents in these states. Empty means every state.")
    priorities: list[Priority] = Field(default_factory=list, max_length=4, description="Only incidents with these priorities. Empty means every priority.")
    sources: list[IncidentSource] = Field(default_factory=list, max_length=3, description="Only incidents from these sources. Empty means every source.")
    lookback_hours: LookbackHours = 168
    text: str | None = Field(default=None, max_length=120, description="Words in the title or the ServiceNow number.")


class GetIncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_reference: str = Field(max_length=60, description="Keigan incident id or ServiceNow number, for example INC0012345.")


class ListAlertGroupsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to list. Empty means every application you were given.")
    statuses: list[AlertGroupStatus] = Field(default_factory=list, max_length=4, description="Only alert groups in these states. Empty means every state.")
    lookback_hours: LookbackHours = 24
    minimum_priority_score: float | None = Field(default=None, ge=0, le=100, description="Only alert groups at or above this priority score (0 to 100).")


class GetAlertGroupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_group_id: str = Field(max_length=36, description="The alert group to open.")


class GetAlertNoiseSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to count. Empty means every application you were given.")
    lookback_hours: LookbackHours = 168


class GetSloHistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slo_id: str = Field(max_length=36, description="The SLO whose history to read.")
    lookback_hours: LookbackHours = 168


class ListPredictiveSignalsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to list. Empty means every application you were given.")
    severities: list[SignalSeverity] = Field(default_factory=list, max_length=3, description="Only signals of these severities. Empty means every severity.")
    statuses: list[SignalStatus] = Field(default_factory=list, max_length=5, description="Only signals in these states. Empty means open and acknowledged.")


class GetHealthScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode
    days: int = Field(default=30, ge=7, le=90, description="How many days of trend to return.")


class ListTeamMembersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_code: ApplicationCode
    roles: list[StakeholderRole] = Field(default_factory=list, max_length=10, description="Only team members in these roles. Empty means every role.")


class GetReliabilityMetricsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_codes: list[ApplicationCode] = Field(default_factory=list, max_length=20, description="Codes of the applications to measure. Empty means every application you were given.")
    lookback_hours: LookbackHours = 720


class FindSimilarIncidentsInput(BaseModel):
    """Exactly one of an investigation, an incident or a description in words (with the application it is about)."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str | None = Field(default=None, max_length=36, description="Find past incidents like this investigation.")
    incident_id: str | None = Field(default=None, max_length=36, description="Find past incidents like this incident (its latest finished investigation).")
    text: str | None = Field(default=None, min_length=3, max_length=500, description="Describe the situation in a few words. Needs application_code.")
    application_code: ApplicationCode | None = Field(default=None, description="The application the description is about. Only for text.")

    @model_validator(mode="after")
    def exactly_one_way_to_ask(self) -> "FindSimilarIncidentsInput":
        given = [name for name in ("investigation_id", "incident_id", "text") if getattr(self, name)]
        if len(given) != 1:
            raise ValueError("Give exactly one of investigation_id, incident_id or text.")
        if self.text and not self.application_code:
            raise ValueError("A description needs application_code.")
        return self

"""What the model may send to an Ask Keigan tool (spec 23, section 5.1).

Closed schemas (``extra="forbid"``): every field is described for the model and every text and list has a length limit. They live in ``ai`` so the
tool registry, the tool implementations and the offline mock planner share one definition.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from keigan.entities.status_values import SloHealthStatus

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

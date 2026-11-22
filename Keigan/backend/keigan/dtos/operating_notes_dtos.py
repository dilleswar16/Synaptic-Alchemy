"""Operating notes: the application team's guidance for the AI."""

from __future__ import annotations

from datetime import datetime

from keigan.dtos.common_dtos import ApiModel


class OperatingNotesUpdateRequest(ApiModel):
    text: str  # trimmed by the service; an empty value clears the notes


class OperatingNotesResponse(ApiModel):
    text: str
    maximum_characters: int
    updated_at: datetime | None = None
    updated_by: str | None = None

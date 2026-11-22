"""What an investigation could not check (spec 27, 4.3): collected by code during the run, stored as rows, and told to the model in a trusted section.

A source that could not be read is not evidence: it is neither a sign of a cause nor of a healthy system. So it never gets an evidence code. It becomes a gap here, with a fixed
kind and reason code, and the model is told about it so it cannot treat silence as health. Gaps are written from catalogue names and fixed codes only; no text of an exception or of
an integration is ever stored or shown (the sentences below are Keigan's own).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.prompt_library import sanitize_prompt_value
from keigan.entities.incident_entities import InvestigationCoverageGap
from keigan.entities.status_values import CoverageGapKind, CoverageGapReason
from keigan.exceptions.keigan_exceptions import ForbiddenException, IntegrationException, ReaderNotAvailableException
from keigan.utils.query_safety import QueryRejectedError

# One plain sentence per reason: the evidence text, the log and the prompt section all use these, so they cannot disagree.
REASON_SENTENCES: dict[CoverageGapReason, str] = {
    CoverageGapReason.ACCESS_REFUSED: "Keigan's identity was refused access to this source (a read role is missing)",
    CoverageGapReason.THROTTLED: "the source was busy and asked Keigan to slow down",
    CoverageGapReason.SOURCE_NOT_FOUND: "the source was not found (it may have been renamed or removed)",
    CoverageGapReason.SOURCE_ERROR: "the source returned an error",
    CoverageGapReason.TIMED_OUT: "the source took too long to answer",
    CoverageGapReason.NOT_APPROVED: "this source is not approved for this application",
    CoverageGapReason.QUERY_REJECTED: "Keigan's query safety rules refused the query",
    CoverageGapReason.READER_NOT_AVAILABLE: "Keigan cannot read this kind of tool yet",
    CoverageGapReason.AI_UNAVAILABLE: "the AI model was not available",
    CoverageGapReason.AI_OUTPUT_INVALID: "the AI's reply could not be used",
    CoverageGapReason.UNKNOWN: "for a reason Keigan could not identify",
}
_REASON_BY_INTEGRATION_ERROR_CODE = {
    "azure_forbidden": CoverageGapReason.ACCESS_REFUSED,
    "azure_throttled": CoverageGapReason.THROTTLED,
    "azure_not_found": CoverageGapReason.SOURCE_NOT_FOUND,
}
NOTHING_MISSING_SENTENCE = "Keigan read every source it planned to."


def classify_query_failure(query_error: Exception) -> CoverageGapReason:
    """The reason code of a failed read, by the type and error code of what was raised (the integration's own text is never kept)."""
    if isinstance(query_error, ReaderNotAvailableException):
        return CoverageGapReason.READER_NOT_AVAILABLE
    if isinstance(query_error, IntegrationException):
        return _REASON_BY_INTEGRATION_ERROR_CODE.get(query_error.error_code, CoverageGapReason.SOURCE_ERROR)
    if isinstance(query_error, (TimeoutError, httpx.TimeoutException)):
        return CoverageGapReason.TIMED_OUT
    if isinstance(query_error, ForbiddenException):
        return CoverageGapReason.NOT_APPROVED
    if isinstance(query_error, QueryRejectedError):
        return CoverageGapReason.QUERY_REJECTED
    return CoverageGapReason.UNKNOWN


@dataclass(frozen=True)
class CoverageGapEntry:
    kind: CoverageGapKind
    reason: CoverageGapReason | None = None
    service_id: str | None = None
    service_name: str | None = None
    source_kind: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)


class CoverageGapCollector:
    """The gaps of one investigation run, in the order they were found."""

    def __init__(self) -> None:
        self._entries: list[CoverageGapEntry] = []
        self._persisted_count = 0

    @property
    def entries(self) -> tuple[CoverageGapEntry, ...]:
        return tuple(self._entries)

    def add(
        self, kind: CoverageGapKind, reason: CoverageGapReason | None = None, *, service_id: str | None = None, service_name: str | None = None,
        source_kind: str | None = None, parameters: Mapping[str, Any] | None = None,
    ) -> None:
        self._entries.append(CoverageGapEntry(kind, reason, service_id, service_name, source_kind, dict(parameters or {})))

    async def persist_new(self, session: AsyncSession, investigation_id: str) -> list[InvestigationCoverageGap]:
        """Stores the gaps found since the last call (the evidence stage writes its own before the hypotheses start; later stages add theirs)."""
        first_new = self._persisted_count
        rows = [
            InvestigationCoverageGap(
                investigation_id=investigation_id, display_order=order, gap_kind=entry.kind, reason_code=entry.reason, service_id=entry.service_id,
                service_name=entry.service_name, source_kind=entry.source_kind, parameters_json=dict(entry.parameters) or None,
            )
            for order, entry in enumerate(self._entries) if order >= first_new
        ]
        self._persisted_count = len(self._entries)
        session.add_all(rows)
        await session.flush()
        return rows

    def render_for_prompt(self) -> str:
        """The trusted prompt section "What Keigan could not check": every line is built from a catalogue name and a fixed sentence."""
        if not self._entries:
            return NOTHING_MISSING_SENTENCE
        return "\n".join(f"- {_sentence_of(entry)}" for entry in self._entries)


def _sentence_of(entry: CoverageGapEntry) -> str:
    service = sanitize_prompt_value(entry.service_name or "a service")
    source = f" ({sanitize_prompt_value(entry.source_kind)})" if entry.source_kind else ""
    reason = REASON_SENTENCES[entry.reason] if entry.reason else REASON_SENTENCES[CoverageGapReason.UNKNOWN]
    parameters = entry.parameters
    count, limit = parameters.get("count"), parameters.get("limit")
    match entry.kind:
        case CoverageGapKind.SOURCE_NOT_READABLE:
            return f"{service}{source} could not be read: {reason}."
        case CoverageGapKind.CHANGES_NOT_READABLE:
            return f"Recent deployments and configuration changes could not be read: {reason}."
        case CoverageGapKind.SERVICE_WITHOUT_TELEMETRY:
            return f"{service} has no log or metric source connected, so nothing was checked for it."
        case CoverageGapKind.SERVICES_BEYOND_LIMIT:
            names = ", ".join(sanitize_prompt_value(str(name)) for name in parameters.get("serviceNames", []))
            return f"{count} service(s) were not examined because of the limit of {limit} services: {names}."
        case CoverageGapKind.CHECKS_BEYOND_LIMIT:
            return f"{count} check(s) on {service} were not run because of the limit of {limit} checks per service."
        case CoverageGapKind.PLANNED_QUERY_REJECTED:
            return f"A query the AI planned for {service} was refused by Keigan's query safety rules."
        case CoverageGapKind.PLANNED_QUERY_FAILED:
            return f"A query the AI planned for {service} failed: {reason}."
        case CoverageGapKind.RESULTS_LEFT_OUT:
            return f"{count} low-signal result(s) were left out to stay within the evidence budget."
        case CoverageGapKind.PERSPECTIVE_NOT_ANALYSED:
            return f"The {sanitize_prompt_value(str(parameters.get('perspective', 'a')))} analysis produced no usable result: {reason}."
    raise ValueError(f"Unhandled coverage gap kind: {entry.kind}")

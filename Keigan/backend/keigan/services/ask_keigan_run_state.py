"""What the answer loop remembers about one run: the tool calls it executed and the sources an answer may cite (spec 23, 4.8)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from keigan.entities.status_values import ChatRunStepStatus


@dataclass(frozen=True)
class ExecutedToolCall:
    """One tool call that was run (succeeded, failed or refused). A call that was skipped has no citation code and is not kept here."""

    citation_code: str
    run_step_id: str
    tool_name: str
    tool_label: str
    status: ChatRunStepStatus
    summary: str | None  # the code-written one-line summary of a succeeded call


@dataclass(frozen=True)
class AnswerCitation:
    """A source an answer may cite: a tool call of this answer (``run_step_id``), or a record the scope already holds (evidence, runbook)."""

    code: str
    title: str
    run_step_id: str | None = None
    evidence_code: str | None = None
    runbook_id: str | None = None

    def as_payload(self) -> dict[str, JsonValue]:
        """The citation as the screen reads it (the ``Citation`` of the answer snapshot)."""
        optional_fields = {"runStepId": self.run_step_id, "evidenceCode": self.evidence_code, "runbookId": self.runbook_id}
        return {"code": self.code, **{name: value for name, value in optional_fields.items() if value is not None}, "title": self.title}

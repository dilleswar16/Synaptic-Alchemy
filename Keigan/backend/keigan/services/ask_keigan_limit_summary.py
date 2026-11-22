"""The deterministic answer for a run that stopped at its tool-call limit or token budget without a usable model answer (spec 23, 4.8)."""

from __future__ import annotations

from collections.abc import Sequence

from keigan.entities.status_values import ChatAnswerStopReason, ChatRunStepStatus
from keigan.services.ask_keigan_run_state import ExecutedToolCall
from keigan.utils.string_table import translate

_TABLE = "ask_keigan_answers"
_INTRODUCTION_KEY_BY_STOP_REASON = {ChatAnswerStopReason.TOOL_LIMIT_REACHED: "limit_reached.tool_limit", ChatAnswerStopReason.TOKEN_BUDGET_REACHED: "limit_reached.token_budget"}


def limit_reached_answer(stop_reason: ChatAnswerStopReason, maximum_tool_calls: int, calls: Sequence[ExecutedToolCall], language_code: str | None) -> str:
    """The reason Keigan stopped, then one line per check: what it found (with its citation) or that it could not be done. A failed check is never an empty result."""
    introduction = translate(language_code, f"{_TABLE}.{_INTRODUCTION_KEY_BY_STOP_REASON[stop_reason]}", maximum=maximum_tool_calls)
    finding_lines = [_finding_line(call, language_code) for call in calls if call.status is not ChatRunStepStatus.SKIPPED]
    if not finding_lines:
        return f"{introduction}\n\n{translate(language_code, f'{_TABLE}.limit_reached.nothing_found')}"
    return introduction + "\n\n" + "\n".join(finding_lines)


def _finding_line(call: ExecutedToolCall, language_code: str | None) -> str:
    if call.status is ChatRunStepStatus.SUCCEEDED:
        return f"- {call.summary} [{call.citation_code}]"
    return f"- {translate(language_code, f'{_TABLE}.check_not_done', toolLabel=call.tool_label)}"

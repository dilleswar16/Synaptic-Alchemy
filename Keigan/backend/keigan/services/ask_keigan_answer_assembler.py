"""Builds the finished answer of a run: citations checked against real sources, follow-ups split off, markdown sanitised, trust flags set (spec 23, 4.8)."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from keigan.ai.ask_keigan_answer_format import is_fixed_refusal, separate_adjacent_citations
from keigan.ai.ask_keigan_follow_ups import split_follow_ups
from keigan.ai.output_sanitizer import sanitize_ai_markdown
from keigan.ai.prompt_safety import find_citation_codes, remove_invalid_citations
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services.ask_keigan_run_state import AnswerCitation, ExecutedToolCall

_CODE_PARTS = re.compile(r"([A-Z]+)(\d+)")
_KIND_ORDER = "TERK"  # tool calls first, then evidence, runbooks, knowledge


@dataclass(frozen=True)
class AssembledAnswer:
    markdown: str
    follow_ups: tuple[str, ...]
    citations: tuple[AnswerCitation, ...]
    is_unverified: bool
    is_refusal: bool


def build_citation_targets(reference_citations: Mapping[str, AnswerCitation], accepted_prefixes: Collection[str], executed_calls: Sequence[ExecutedToolCall]) -> dict[str, AnswerCitation]:
    """Every code an answer may cite: the tool calls that succeeded plus the records the scope holds, limited to the kinds of code the scope accepts."""
    tool_citations = {
        call.citation_code: AnswerCitation(code=call.citation_code, title=call.tool_label, run_step_id=call.run_step_id)
        for call in executed_calls if call.status is ChatRunStepStatus.SUCCEEDED
    }
    return {code: citation for code, citation in {**tool_citations, **reference_citations}.items() if code[0] in accepted_prefixes}


def assemble_answer(model_text: str, citation_targets: Mapping[str, AnswerCitation], *, tool_call_count: int, follow_up_limit: int) -> AssembledAnswer:
    follow_up_split = split_follow_ups(model_text, follow_up_limit)
    markdown = sanitize_ai_markdown(separate_adjacent_citations(remove_invalid_citations(follow_up_split.answer_text, set(citation_targets))))
    cited_codes = sorted(find_citation_codes(markdown), key=_code_order)
    is_refusal = is_fixed_refusal(markdown)
    return AssembledAnswer(
        markdown=markdown, follow_ups=follow_up_split.follow_ups, citations=tuple(citation_targets[code] for code in cited_codes), is_refusal=is_refusal,
        is_unverified=not is_refusal and (tool_call_count == 0 or not cited_codes),
    )


def _code_order(code: str) -> tuple[int, int]:
    kind, number = _CODE_PARTS.fullmatch(code).groups()  # type: ignore[union-attr]
    return _KIND_ORDER.index(kind), int(number)

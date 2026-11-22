"""The text conventions of an Ask Keigan transcript and answer, shared by the engine, the prompts and the mock planner so they cannot drift apart."""

from __future__ import annotations

import re
from enum import StrEnum

from keigan.utils.string_table import SUPPORTED_LANGUAGE_CODES, find_string

QUESTION_SECTION_TITLE = "Question"
HISTORY_SECTION_TITLE = "Conversation so far"
# After the answer, a line with this marker and then the suggested follow-up questions, one per line.
FOLLOW_UP_MARKER = "<<follow-ups>>"
FOLLOW_UP_MAXIMUM_CHARACTERS = 160
_ANSWERS_TABLE = "ask_keigan_answers"
_ADJACENT_CITATIONS = re.compile(r"(\[[A-Z]\d{1,3}\])(?=\[[A-Z]\d{1,3}\])")


class FixedAnswer(StrEnum):
    """Answers Keigan words itself, in the person's language, instead of asking the model: the person has nothing to read, or the question is not about Keigan's data."""

    NO_ACCESS = "no_access"
    OUTSIDE_SCOPE = "outside_scope"


def fixed_answer(answer: FixedAnswer | str, language_code: str | None) -> str:
    return find_string(language_code, f"{_ANSWERS_TABLE}.{answer}") or ""


def separate_adjacent_citations(markdown_text: str) -> str:
    """``[T1][T2]`` becomes ``[T1] [T2]``: markdown reads two adjacent bracket pairs as a reference link and the sanitiser would escape the second, which loses that citation."""
    return _ADJACENT_CITATIONS.sub(r"\1 ", markdown_text)


def is_fixed_refusal(answer_text: str) -> bool:
    """True when the whole answer is one of the fixed answers (in any supported language). Such an answer is a refusal, never "unverified"."""
    stripped_text = answer_text.strip()
    return any(stripped_text == fixed_answer(answer, language_code) for answer in FixedAnswer for language_code in SUPPORTED_LANGUAGE_CODES)

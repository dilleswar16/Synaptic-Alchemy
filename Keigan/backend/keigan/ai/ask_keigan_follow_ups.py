"""Splits the follow-up questions off the end of a model answer (spec 23, 4.9)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER, FOLLOW_UP_MAXIMUM_CHARACTERS
from keigan.ai.output_sanitizer import sanitize_ai_line

_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


@dataclass(frozen=True)
class FollowUpSplit:
    answer_text: str
    follow_ups: tuple[str, ...]


def split_follow_ups(model_text: str, limit: int) -> FollowUpSplit:
    """The answer before the first line that is exactly the marker, and the questions after it: one per line, sanitised, without duplicates, at most ``limit``.

    A repeated marker line is dropped. Without a marker line there are no follow-ups and the text is unchanged.
    """
    lines = model_text.splitlines()
    marker_index = next((index for index, line in enumerate(lines) if line.strip() == FOLLOW_UP_MARKER), None)
    if marker_index is None:
        return FollowUpSplit(model_text, ())
    question_lines = (line for line in lines[marker_index + 1:] if line.strip() != FOLLOW_UP_MARKER)
    questions = (sanitize_ai_line(_LIST_MARKER.sub("", line), maximum_characters=FOLLOW_UP_MAXIMUM_CHARACTERS) for line in question_lines)
    unique_questions = dict.fromkeys(question for question in questions if question)
    return FollowUpSplit("\n".join(lines[:marker_index]).rstrip(), tuple(unique_questions)[:limit])

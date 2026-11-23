"""Turns the text a model streams into whole paragraphs that are safe to show (spec 23, 4.8).

A paragraph is released only when the blank line after it has arrived, so a citation or a link is never checked in pieces. Each paragraph has its
citations to tool calls that do not exist removed and goes through the markdown sanitiser, so nothing unsafe is shown, even briefly. The follow-up
section (after the marker line) is never released: the engine splits it off the finished answer.
"""

from __future__ import annotations

import re

from keigan.ai.ask_keigan_answer_cleaning import clean_answer_markdown
from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_FENCE_LINE = re.compile(r"^\s*(?:```|~~~)", re.MULTILINE)


class AnswerTextStreamer:
    def __init__(self, valid_citation_codes: frozenset[str]):
        self._valid_citation_codes = set(valid_citation_codes)
        self._pending_text = ""
        self._follow_up_section_started = False

    def feed(self, text_chunk: str) -> list[str]:
        """The paragraphs that this chunk completed (sanitised, never empty)."""
        if self._follow_up_section_started:
            return []
        self._pending_text += text_chunk
        released_paragraphs: list[str] = []
        while (paragraph_end := self._end_of_first_paragraph()) is not None:
            released_paragraphs.append(self._pending_text[:paragraph_end.start()])
            self._pending_text = self._pending_text[paragraph_end.end():]
        return self._clean(self._without_follow_ups(released_paragraphs))

    def finish(self) -> list[str]:
        """The text still waiting for its blank line, once the model has stopped."""
        released_text, self._pending_text = self._pending_text, ""
        return [] if self._follow_up_section_started else self._clean(self._without_follow_ups([released_text]))

    def _end_of_first_paragraph(self) -> re.Match[str] | None:
        """The first blank line that is not inside a code fence (a fence is open while the text before it holds an odd number of fence lines)."""
        for paragraph_break in _PARAGRAPH_BREAK.finditer(self._pending_text):
            if len(_FENCE_LINE.findall(self._pending_text[:paragraph_break.start()])) % 2 == 0:
                return paragraph_break
        return None

    def _without_follow_ups(self, paragraphs: list[str]) -> list[str]:
        """The paragraphs up to the follow-up marker line; from the marker on, nothing is released again."""
        kept_paragraphs: list[str] = []
        for paragraph in paragraphs:
            lines = paragraph.splitlines()
            marker_index = next((index for index, line in enumerate(lines) if line.strip() == FOLLOW_UP_MARKER), None)
            if marker_index is not None:
                self._follow_up_section_started = True
                kept_paragraphs.append("\n".join(lines[:marker_index]))
                break
            kept_paragraphs.append(paragraph)
        return kept_paragraphs

    def _clean(self, paragraphs: list[str]) -> list[str]:
        cleaned_paragraphs = (clean_answer_markdown(paragraph, self._valid_citation_codes) for paragraph in paragraphs)
        return [paragraph for paragraph in cleaned_paragraphs if paragraph.strip()]

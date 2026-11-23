"""The one place an Ask Keigan answer's Markdown is made safe to show, shared by the streamed paragraphs and the finished answer so what streams and what is stored agree (spec 23, 4.8; spec 36)."""

from __future__ import annotations

from collections.abc import Collection

from keigan.ai.ask_keigan_answer_format import separate_adjacent_citations
from keigan.ai.mermaid_diagram_check import withhold_unsafe_diagrams
from keigan.ai.output_sanitizer import sanitize_ai_markdown
from keigan.ai.prompt_safety import remove_invalid_citations
from keigan.config.settings import get_settings


def clean_answer_markdown(markdown_text: str, valid_citation_codes: Collection[str]) -> str:
    """Citations to calls that do not exist removed, adjacent citations separated, unsafe Markdown rewritten, and every Mermaid diagram that fails the server's check marked as withheld."""
    settings = get_settings()
    sanitized = sanitize_ai_markdown(separate_adjacent_citations(remove_invalid_citations(markdown_text, set(valid_citation_codes))))
    return withhold_unsafe_diagrams(sanitized, settings.ask_keigan_diagram_maximum_characters, settings.ask_keigan_diagram_maximum_lines)

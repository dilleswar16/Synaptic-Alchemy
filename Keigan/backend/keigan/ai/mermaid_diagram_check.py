"""Which Mermaid diagrams an Ask Keigan answer may carry (spec 36, D3 and D4).

The browser draws a ``mermaid`` block in Mermaid's strict mode, and this check runs first on the server: a diagram written under the influence of untrusted text must not be
able to change the drawing's configuration, make something clickable, link out or carry markup. A block that fails is not dropped: its language is rewritten to
``mermaid-withheld:<problem>`` so the screen shows the source as code with the reason. Pure functions, no model and no database.
"""

from __future__ import annotations

import re
from enum import StrEnum

MERMAID_LANGUAGE = "mermaid"
WITHHELD_LANGUAGE = "mermaid-withheld"

_ALLOWED_TYPE = re.compile(r"^(?:flowchart|graph|sequenceDiagram|stateDiagram-v2|stateDiagram|erDiagram|classDiagram|timeline)(?:\s|$)")
_INTERACTION = re.compile(r"^\s*(?:click|link|links|callback|call)\b|\bhref\b|javascript:", re.IGNORECASE | re.MULTILINE)
_HTML_TAG = re.compile(r"<(?!br\s*/?>)[A-Za-z/!]", re.IGNORECASE)
_CLASS_ANNOTATION = re.compile(r"<<[A-Za-z]+>>")  # classDiagram's <<interface>>: not markup
_FENCE = re.compile(r"^(?P<indent> {0,3})(?P<marker>`{3,}|~{3,})(?P<info>[^\n]*)$")


class DiagramProblem(StrEnum):
    EMPTY = "empty"
    TOO_LONG = "too_long"
    TOO_MANY_LINES = "too_many_lines"
    UNKNOWN_TYPE = "unknown_type"
    DIRECTIVE = "directive"
    INTERACTION = "interaction"
    LINK = "link"
    HTML = "html"
    MATH = "math"  # $$ formulas are drawn by KaTeX, which has an open advisory (low); Keigan answers have no use for them


def _first_statement(source: str) -> str | None:
    """The first line that is neither blank nor a ``%%`` comment (a ``%%{`` directive is not a comment: it configures the drawing)."""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and (not stripped.startswith("%%") or stripped.startswith("%%{")):
            return stripped
    return None


def check_diagram_source(source: str, maximum_characters: int, maximum_lines: int) -> DiagramProblem | None:
    """None when the diagram may be drawn, else the first problem found."""
    first_statement = _first_statement(source)
    if first_statement is None:
        return DiagramProblem.EMPTY
    if len(source) > maximum_characters:
        return DiagramProblem.TOO_LONG
    if len(source.splitlines()) > maximum_lines:
        return DiagramProblem.TOO_MANY_LINES
    if "%%{" in source or first_statement.startswith("---"):  # a directive, or YAML front matter (which can also set the configuration)
        return DiagramProblem.DIRECTIVE
    if not _ALLOWED_TYPE.match(first_statement):
        return DiagramProblem.UNKNOWN_TYPE
    if _INTERACTION.search(source):
        return DiagramProblem.INTERACTION
    if "://" in source:
        return DiagramProblem.LINK
    if "$$" in source:
        return DiagramProblem.MATH
    if _HTML_TAG.search(_CLASS_ANNOTATION.sub("", source)):
        return DiagramProblem.HTML
    return None


def withhold_unsafe_diagrams(markdown_text: str, maximum_characters: int, maximum_lines: int) -> str:
    """The same Markdown with every failing ``mermaid`` fence marked as withheld. Other fences are never touched.

    A fence that is never closed runs to the end of the text, as Markdown reads it, so it is judged the same way: an answer is released in whole paragraphs, so a fence is only
    ever unclosed at the very end.
    """
    lines = markdown_text.split("\n")

    def judge(opening_index: int, end_index: int) -> None:
        fence = _FENCE.match(lines[opening_index])
        if fence is None:
            return
        language = fence["info"].split(maxsplit=1)[0] if fence["info"].strip() else ""
        if language.lower() != MERMAID_LANGUAGE:
            return
        problem = check_diagram_source("\n".join(lines[opening_index + 1:end_index]), maximum_characters, maximum_lines)
        if problem is not None:
            lines[opening_index] = f"{fence['indent']}{fence['marker']}{WITHHELD_LANGUAGE}:{problem.value}"

    open_fence: tuple[int, str] | None = None  # (opening line index, marker)
    for index, line in enumerate(lines):
        fence = _FENCE.match(line)
        if open_fence is None:
            if fence:
                open_fence = (index, fence["marker"])
        elif fence and fence["marker"][0] == open_fence[1][0] and len(fence["marker"]) >= len(open_fence[1]) and not fence["info"].strip():
            judge(open_fence[0], index)
            open_fence = None
    if open_fence is not None:
        judge(open_fence[0], len(lines))
    return "\n".join(lines)

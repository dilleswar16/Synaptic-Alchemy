"""keigan/ai/mermaid_diagram_check.py: which Mermaid diagrams an answer may carry (spec 36, D3 and D4; AC-1, AC-2)."""

from __future__ import annotations

import pytest

from keigan.ai.mermaid_diagram_check import DiagramProblem, check_diagram_source, withhold_unsafe_diagrams

MAXIMUM_CHARACTERS, MAXIMUM_LINES = 400, 12


def check(source: str) -> DiagramProblem | None:
    return check_diagram_source(source, MAXIMUM_CHARACTERS, MAXIMUM_LINES)


@pytest.mark.parametrize("source", [
    "flowchart LR\n  A[API] --> B[(Database)]",
    "graph TD\n  A --> B",
    "sequenceDiagram\n  Alice->>Bob: Hello\n  Bob-->>Alice: Hi",
    "stateDiagram-v2\n  [*] --> Idle\n  Idle --> Busy",
    "erDiagram\n  CUSTOMER ||--o{ ORDER : places",
    "classDiagram\n  class Animal {\n    <<interface>>\n  }",
    "timeline\n  title History\n  2026 : Launch",
    "%% a comment first\nflowchart TB\n  A[Line one<br/>line two] <--> B",
])
def test_every_allowed_diagram_type_passes(source: str) -> None:
    assert check(source) is None


@pytest.mark.parametrize(("source", "problem"), [
    ("", DiagramProblem.EMPTY),
    ("   \n  \n", DiagramProblem.EMPTY),
    ("pie title Pets\n  \"Dogs\" : 3", DiagramProblem.UNKNOWN_TYPE),
    ("this is not a diagram", DiagramProblem.UNKNOWN_TYPE),
    ("flowchart-elk LR\n  A --> B", DiagramProblem.UNKNOWN_TYPE),
    ("%%{init: {'securityLevel': 'loose'}}%%\nflowchart LR\n  A --> B", DiagramProblem.DIRECTIVE),
    ("flowchart LR\n  %%{init: {\"theme\": \"base\"}}%%\n  A --> B", DiagramProblem.DIRECTIVE),
    ("---\nconfig:\n  theme: forest\n---\nflowchart LR\n  A --> B", DiagramProblem.DIRECTIVE),
    ("flowchart LR\n  A --> B\n  click A callback \"tooltip\"", DiagramProblem.INTERACTION),
    ("flowchart LR\n  A --> B\n  click A href \"x\"", DiagramProblem.INTERACTION),
    ("classDiagram\n  class A\n  link A \"page\"", DiagramProblem.INTERACTION),
    ("flowchart LR\n  A[open javascript:alert(1)] --> B", DiagramProblem.INTERACTION),
    ("flowchart LR\n  A[see https://example.com/x] --> B", DiagramProblem.LINK),
    ("flowchart LR\n  A[<img src=x onerror=alert(1)>] --> B", DiagramProblem.HTML),
    ("flowchart LR\n  A[<script>alert(1)</script>] --> B", DiagramProblem.HTML),
    ("flowchart LR\n  A[x] --> B\n  A[</div>] --> C", DiagramProblem.HTML),
    ("flowchart LR\n  A[\"$$x^2$$\"] --> B", DiagramProblem.MATH),
])
def test_each_refused_construct_is_refused_with_its_reason(source: str, problem: DiagramProblem) -> None:
    assert check(source) is problem


def test_the_size_limits_are_enforced() -> None:
    assert check("flowchart LR\n" + "  A --> B\n" * 40) is DiagramProblem.TOO_LONG  # over the character limit first
    assert check("flowchart LR\n" + "A-->B\n" * 13) is DiagramProblem.TOO_MANY_LINES
    assert check("flowchart LR\n" + "A-->B\n" * 11) is None


# ── Answers ──────────────────────────────────────────────────────────────────────────────────────


def withhold(markdown: str) -> str:
    return withhold_unsafe_diagrams(markdown, MAXIMUM_CHARACTERS, MAXIMUM_LINES)


def test_a_good_diagram_and_the_text_around_it_are_untouched() -> None:
    answer = "Here is the flow.\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\nThe API calls the database [T1]."
    assert withhold(answer) == answer


def test_a_bad_diagram_keeps_its_source_but_is_marked_withheld_with_the_reason() -> None:
    answer = "Before\n\n```mermaid\nflowchart LR\n  A --> B\n  click A href \"x\"\n```\n\nAfter"
    result = withhold(answer)
    assert result.startswith("Before\n\n```mermaid-withheld:interaction\nflowchart LR") and "click A href" in result and result.endswith("```\n\nAfter")
    assert "```mermaid\n" not in result


def test_only_mermaid_fences_are_looked_at() -> None:
    answer = "```python\nprint('click here ://')\n```\n\n```text\n%%{init}%%\n```\n\n~~~mermaid\nflowchart LR\n  A[<b>x</b>] --> B\n~~~"
    result = withhold(answer)
    assert result.startswith("```python\nprint('click here ://')\n```\n\n```text\n%%{init}%%\n```")
    assert result.endswith("~~~mermaid-withheld:html\nflowchart LR\n  A[<b>x</b>] --> B\n~~~")


def test_the_language_is_matched_whatever_its_case_and_with_trailing_words() -> None:
    assert "mermaid-withheld:directive" in withhold("```Mermaid title\n%%{init}%%\nflowchart LR\n```")


def test_an_unclosed_fence_runs_to_the_end_as_markdown_reads_it_and_is_judged_the_same_way() -> None:
    assert withhold("Text\n\n```mermaid\nflowchart LR\n  click A href \"x\"") == "Text\n\n```mermaid-withheld:interaction\nflowchart LR\n  click A href \"x\""
    good = "Text\n\n```mermaid\nflowchart LR\n  A --> B"
    assert withhold(good) == good


def test_a_longer_closing_fence_and_an_indented_fence_are_handled_and_each_diagram_is_judged_alone() -> None:
    answer = "  ```mermaid\n  flowchart LR\n    A --> B\n  ```\n\n````mermaid\nflowchart LR\n  A[<i>x</i>]\n````"
    result = withhold(answer)
    assert result.startswith("  ```mermaid\n  flowchart LR") and "````mermaid-withheld:html" in result

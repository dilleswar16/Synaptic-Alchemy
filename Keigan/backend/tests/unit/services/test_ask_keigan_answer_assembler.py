"""keigan/services/ask_keigan_answer_assembler.py: the finished answer, its sources and whether it can be trusted (spec 23, 4.8, AC-14 to AC-16)."""

from __future__ import annotations

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER, fixed_answer
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services.ask_keigan_answer_assembler import assemble_answer, build_citation_targets
from keigan.services.ask_keigan_run_state import AnswerCitation, ExecutedToolCall

EVIDENCE = AnswerCitation(code="E3", title="Error spike", evidence_code="E3")
RUNBOOK = AnswerCitation(code="R1", title="Restart the pool", runbook_id="runbook-1")


def call(number: int, status: ChatRunStepStatus = ChatRunStepStatus.SUCCEEDED, label: str = "Opened evidence") -> ExecutedToolCall:
    return ExecutedToolCall(citation_code=f"T{number}", run_step_id=f"step-{number}", tool_name="get_evidence", tool_label=label, status=status, summary="E2: Spike")


def assemble(raw_text: str, calls: list[ExecutedToolCall], *, references: dict[str, AnswerCitation] | None = None, prefixes: frozenset[str] = frozenset({"T", "E", "R"}), limit: int = 3):
    targets = build_citation_targets(references or {}, prefixes, calls)
    return assemble_answer(raw_text, targets, tool_call_count=len(calls), follow_up_limit=limit)


def test_only_citations_of_succeeded_tool_calls_and_known_references_survive() -> None:
    calls = [call(1), call(2, ChatRunStepStatus.FAILED), call(3, ChatRunStepStatus.REFUSED)]
    answer = assemble("Rose [T1], unknown [T2][T3][T9], evidence [E3], other [E7].", calls, references={"E3": EVIDENCE})
    assert answer.markdown == "Rose [T1], unknown , evidence [E3], other ."
    assert [citation.code for citation in answer.citations] == ["T1", "E3"]


def test_a_tool_citation_links_to_its_step_and_names_the_tool() -> None:
    answer = assemble("Rose [T1].", [call(1, label="Checked SLO status")])
    assert answer.citations[0].as_payload() == {"code": "T1", "runStepId": "step-1", "title": "Checked SLO status"}


def test_evidence_and_runbook_citations_carry_their_own_target_keys() -> None:
    answer = assemble("See [E3] and [R1].", [], references={"E3": EVIDENCE, "R1": RUNBOOK})
    assert [citation.as_payload() for citation in answer.citations] == [
        {"code": "E3", "evidenceCode": "E3", "title": "Error spike"}, {"code": "R1", "runbookId": "runbook-1", "title": "Restart the pool"},
    ]


def test_citations_are_listed_once_in_the_order_of_their_codes() -> None:
    answer = assemble("[T2] then [T1] then [T2] again and [E3].", [call(1), call(2)], references={"E3": EVIDENCE})
    assert [citation.code for citation in answer.citations] == ["T1", "T2", "E3"]


def test_a_kind_of_citation_the_scope_does_not_accept_is_removed_even_when_it_exists() -> None:
    answer = assemble("See [E3] and [T1].", [call(1)], references={"E3": EVIDENCE}, prefixes=frozenset({"T"}))
    assert answer.markdown == "See  and [T1]." and [citation.code for citation in answer.citations] == ["T1"]


def test_the_follow_up_section_is_split_off_limited_and_never_part_of_the_answer() -> None:
    answer = assemble(f"Rose [T1].\n\n{FOLLOW_UP_MARKER}\nQ1\nQ2\nQ3", [call(1)], limit=2)
    assert answer.markdown == "Rose [T1]." and answer.follow_ups == ("Q1", "Q2")
    assert FOLLOW_UP_MARKER not in answer.markdown


def test_a_valid_citation_makes_the_answer_verified() -> None:
    assert assemble("Rose [T1].", [call(1)]).is_unverified is False


def test_an_answer_after_tool_calls_that_cites_nothing_is_unverified() -> None:
    assert assemble("Errors rose.", [call(1)]).is_unverified is True


def test_an_answer_whose_only_citation_was_invalid_is_unverified() -> None:
    assert assemble("Errors rose [T5].", [call(1)]).is_unverified is True


def test_an_answer_without_any_tool_call_is_unverified_even_if_it_cites_a_reference_of_the_scope() -> None:
    assert assemble("See [E3].", [], references={"E3": EVIDENCE}).is_unverified is True


def test_the_fixed_refusals_are_refusals_and_never_unverified() -> None:
    for answer_text in (fixed_answer("no_access", "en"), fixed_answer("outside_scope", "ja")):
        answer = assemble(answer_text, [])
        assert answer.is_refusal is True and answer.is_unverified is False


def test_links_in_the_answer_are_defanged() -> None:
    answer = assemble("Open [the page](http://evil.example/x) [T1].", [call(1)])
    assert "http://evil.example" not in answer.markdown and "[T1]" in answer.markdown


def test_two_citations_in_a_row_both_survive_the_sanitiser() -> None:
    answer = assemble("Both agree [T1][T2].", [call(1), call(2)])
    assert answer.markdown == "Both agree [T1] [T2]." and [citation.code for citation in answer.citations] == ["T1", "T2"]


# ── Diagrams (spec 36, AC-3): the stored answer carries the same marker the streamed paragraphs did ──


def test_a_diagram_that_fails_the_check_is_withheld_in_the_finished_answer_and_a_good_one_is_kept() -> None:
    raw = "Calls [T1].\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n```mermaid\nflowchart LR\n  A[see https://example.com] --> B\n```\n<<follow-ups>>\nWhat next?"
    answer = assemble(raw, [call(1)])
    assert "```mermaid\nflowchart LR\n  A --> B\n```" in answer.markdown and "```mermaid-withheld:link\n" in answer.markdown
    assert answer.follow_ups == ("What next?",)


def test_the_diagram_limits_come_from_the_settings(monkeypatch) -> None:
    from keigan.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "ask_keigan_diagram_maximum_lines", 10)
    long_diagram = "```mermaid\nflowchart LR\n" + "  A --> B\n" * 11 + "```"
    assert "```mermaid-withheld:too_many_lines\n" in assemble(long_diagram, [call(1)]).markdown

"""keigan/services/ask_keigan_limit_summary.py: the answer Keigan writes itself when it ran out of tool calls or tokens before the model answered (spec 23, 4.8)."""

from __future__ import annotations

from keigan.entities.status_values import ChatAnswerStopReason, ChatRunStepStatus
from keigan.services.ask_keigan_limit_summary import limit_reached_answer
from keigan.services.ask_keigan_run_state import ExecutedToolCall


def call(number: int, status: ChatRunStepStatus, summary: str | None, label: str = "Checked SLO status") -> ExecutedToolCall:
    return ExecutedToolCall(citation_code=f"T{number}", run_step_id=f"s{number}", tool_name="get_slo_status", tool_label=label, status=status, summary=summary)


def test_the_summary_names_the_limit_and_lists_each_finding_with_its_citation() -> None:
    calls = [call(1, ChatRunStepStatus.SUCCEEDED, "6 SLOs: 1 breached"), call(2, ChatRunStepStatus.SUCCEEDED, "3 changes in the last 24 hours")]
    assert limit_reached_answer(ChatAnswerStopReason.TOOL_LIMIT_REACHED, 2, calls, "en") == (
        "I stopped at the limit of 2 tool calls before I could write a full answer. This is what the checks found:\n\n"
        "- 6 SLOs: 1 breached [T1]\n- 3 changes in the last 24 hours [T2]"
    )


def test_a_check_that_failed_is_listed_as_not_done_and_never_as_an_empty_result() -> None:
    calls = [call(1, ChatRunStepStatus.SUCCEEDED, "6 SLOs"), call(2, ChatRunStepStatus.FAILED, None, label="Checked recent changes"), call(3, ChatRunStepStatus.REFUSED, None, label="Queried the logs")]
    answer = limit_reached_answer(ChatAnswerStopReason.TOOL_LIMIT_REACHED, 3, calls, "en")
    assert "- 6 SLOs [T1]" in answer
    assert "- Checked recent changes could not be checked." in answer and "- Queried the logs could not be checked." in answer
    assert "[T2]" not in answer and "[T3]" not in answer


def test_calls_that_were_skipped_are_not_mentioned() -> None:
    calls = [call(1, ChatRunStepStatus.SUCCEEDED, "6 SLOs"), call(2, ChatRunStepStatus.SKIPPED, None, label="Read the timeline")]
    assert "timeline" not in limit_reached_answer(ChatAnswerStopReason.TOOL_LIMIT_REACHED, 1, calls, "en")


def test_the_token_budget_has_its_own_introduction() -> None:
    answer = limit_reached_answer(ChatAnswerStopReason.TOKEN_BUDGET_REACHED, 6, [call(1, ChatRunStepStatus.SUCCEEDED, "6 SLOs")], "en")
    assert answer.startswith("I stopped at the token budget for one answer")


def test_without_any_check_the_summary_says_so_instead_of_listing_nothing() -> None:
    answer = limit_reached_answer(ChatAnswerStopReason.TOOL_LIMIT_REACHED, 2, [], "en")
    assert answer.endswith("None of the checks returned anything I can report.")


def test_the_summary_is_written_in_the_persons_language() -> None:
    answer = limit_reached_answer(ChatAnswerStopReason.TOOL_LIMIT_REACHED, 4, [call(1, ChatRunStepStatus.SUCCEEDED, "6 SLO")], "ja")
    assert "4 回" in answer and "- 6 SLO [T1]" in answer

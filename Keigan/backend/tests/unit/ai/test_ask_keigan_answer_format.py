"""keigan/ai/ask_keigan_answer_format.py: the fixed answers Keigan writes itself, and how a refusal is recognised (spec 23, 4.8)."""

from __future__ import annotations

import pytest

from keigan.ai.ask_keigan_answer_format import fixed_answer, is_fixed_refusal, separate_adjacent_citations
from keigan.ai.ask_keigan_mock_planner import OUTSIDE_SCOPE_ANSWER


def test_the_fixed_answers_are_written_in_the_persons_language() -> None:
    assert fixed_answer("no_access", "en") == "You don't have access to any applications yet, so there is nothing for me to look at."
    assert "アクセス" in fixed_answer("no_access", "ja")


def test_an_unsupported_language_gets_english() -> None:
    assert fixed_answer("outside_scope", "fr") == fixed_answer("outside_scope", "en")


def test_the_offline_planner_and_the_prompt_use_the_same_out_of_scope_sentence() -> None:
    assert OUTSIDE_SCOPE_ANSWER == fixed_answer("outside_scope", "en")


@pytest.mark.parametrize("language", ["en", "ja"])
@pytest.mark.parametrize("key", ["no_access", "outside_scope"])
def test_each_fixed_answer_is_recognised_as_a_refusal_whatever_the_language_or_spacing(key: str, language: str) -> None:
    assert is_fixed_refusal(f"  {fixed_answer(key, language)}\n") is True


def test_an_ordinary_answer_or_a_sentence_that_only_contains_the_refusal_is_not_a_refusal() -> None:
    assert is_fixed_refusal("Errors rose [T1].") is False
    assert is_fixed_refusal(fixed_answer("outside_scope", "en") + " But here is something else.") is False


def test_adjacent_citations_are_separated_so_the_markdown_sanitiser_keeps_every_one() -> None:
    assert separate_adjacent_citations("Rose [T1][T2][E3] and fell [T4].") == "Rose [T1] [T2] [E3] and fell [T4]."
    assert separate_adjacent_citations("A list [x][y] stays.") == "A list [x][y] stays."

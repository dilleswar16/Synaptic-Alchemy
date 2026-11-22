"""keigan/ai/ask_keigan_follow_ups.py: the follow-up questions after an answer are split off, cleaned and limited (spec 23, 4.9, AC-16)."""

from __future__ import annotations

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER
from keigan.ai.ask_keigan_follow_ups import split_follow_ups


def test_the_questions_after_the_marker_become_follow_ups_and_the_marker_never_stays_in_the_answer() -> None:
    split = split_follow_ups(f"Errors rose [T1].\n\n{FOLLOW_UP_MARKER}\nWhich alerts fired?\nWhat changed?", limit=3)
    assert split.answer_text == "Errors rose [T1]."
    assert split.follow_ups == ("Which alerts fired?", "What changed?")


def test_a_text_without_the_marker_has_no_follow_ups() -> None:
    split = split_follow_ups("Just an answer.", limit=3)
    assert split.answer_text == "Just an answer." and split.follow_ups == ()


def test_only_the_first_marker_splits_and_a_repeated_marker_line_is_not_shown_as_a_question() -> None:
    split = split_follow_ups(f"A\n{FOLLOW_UP_MARKER}\nQ1\n{FOLLOW_UP_MARKER}\nQ2", limit=5)
    assert split.answer_text == "A"
    assert split.follow_ups == ("Q1", "Q2")


def test_at_most_the_limit_is_kept_in_order() -> None:
    split = split_follow_ups(f"A\n{FOLLOW_UP_MARKER}\nQ1\nQ2\nQ3\nQ4", limit=2)
    assert split.follow_ups == ("Q1", "Q2")


def test_a_limit_of_zero_keeps_none_but_still_removes_the_marker_section() -> None:
    split = split_follow_ups(f"A\n{FOLLOW_UP_MARKER}\nQ1", limit=0)
    assert split.answer_text == "A" and split.follow_ups == ()


def test_empty_and_duplicate_lines_are_dropped_and_list_markers_removed() -> None:
    split = split_follow_ups(f"A\n{FOLLOW_UP_MARKER}\n\n- Q1\n* Q1\n1. Q2\n   \n2) Q3", limit=5)
    assert split.follow_ups == ("Q1", "Q2", "Q3")


def test_a_follow_up_is_one_sanitised_short_line() -> None:
    long_question = "Why " + "x" * 400
    split = split_follow_ups(f"A\n{FOLLOW_UP_MARKER}\nSee [here](http://evil.example/x)\n{long_question}", limit=5)
    assert "http://" not in split.follow_ups[0] and "](" not in split.follow_ups[0]
    assert len(split.follow_ups[1]) <= 160


def test_the_marker_must_be_a_line_of_its_own() -> None:
    split = split_follow_ups(f"The text mentions {FOLLOW_UP_MARKER} inside a sentence.", limit=3)
    assert split.answer_text == f"The text mentions {FOLLOW_UP_MARKER} inside a sentence." and split.follow_ups == ()

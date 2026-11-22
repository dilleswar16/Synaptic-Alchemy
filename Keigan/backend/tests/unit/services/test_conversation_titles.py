"""keigan/services/conversation_titles.py: the first question names a conversation that still has the placeholder title."""

from __future__ import annotations

from keigan.services.conversation_titles import DEFAULT_CONVERSATION_TITLE, TITLE_MAXIMUM_CHARACTERS, title_after_question


def test_the_first_question_names_a_conversation_with_the_placeholder_title() -> None:
    assert title_after_question(DEFAULT_CONVERSATION_TITLE, "  How are the SLOs doing?  ") == "How are the SLOs doing?"


def test_a_long_question_is_cut_to_the_title_length_with_an_ellipsis() -> None:
    title = title_after_question(DEFAULT_CONVERSATION_TITLE, "x" * 200)
    assert len(title) == TITLE_MAXIMUM_CHARACTERS and title.endswith("…")


def test_a_conversation_that_has_a_real_title_keeps_it() -> None:
    assert title_after_question("Failed requests last week", "And yesterday?") == "Failed requests last week"


def test_an_empty_question_leaves_the_placeholder() -> None:
    assert title_after_question(DEFAULT_CONVERSATION_TITLE, "   ") == DEFAULT_CONVERSATION_TITLE

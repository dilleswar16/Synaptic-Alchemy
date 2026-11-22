"""The title of a conversation: it starts as a placeholder and takes the words of the first question asked in it."""

from __future__ import annotations

from keigan.utils.text_utils import truncate_text

DEFAULT_CONVERSATION_TITLE = "New conversation"
TITLE_MAXIMUM_CHARACTERS = 60


def title_after_question(current_title: str, masked_question: str) -> str:
    """The first question names a conversation that still has the placeholder title; a conversation that has a real title (a later question, a rename, an investigation chat) keeps it."""
    if current_title != DEFAULT_CONVERSATION_TITLE:
        return current_title
    return truncate_text(masked_question.strip(), TITLE_MAXIMUM_CHARACTERS) or current_title

"""keigan/ai/ask_keigan_answer_stream.py: streamed model text reaches the screen as whole, sanitised paragraphs only (spec 23, 4.8)."""

from __future__ import annotations

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER
from keigan.ai.ask_keigan_answer_stream import AnswerTextStreamer


def stream(chunks: list[str], valid_codes: frozenset[str] = frozenset()) -> list[str]:
    streamer = AnswerTextStreamer(valid_codes)
    paragraphs: list[str] = []
    for chunk in chunks:
        paragraphs += streamer.feed(chunk)
    return paragraphs + streamer.finish()


def test_a_paragraph_is_released_only_when_the_blank_line_after_it_arrives() -> None:
    streamer = AnswerTextStreamer(frozenset())
    assert streamer.feed("First para") == []
    assert streamer.feed("graph.\n") == []
    assert streamer.feed("\nSecond") == ["First paragraph."]
    assert streamer.finish() == ["Second"]


def test_text_split_in_the_middle_of_a_word_or_a_citation_is_joined_before_it_is_checked() -> None:
    assert stream(["Errors rose [T", "1] and fell.", "\n\nDone."], frozenset({"T1"})) == ["Errors rose [T1] and fell.", "Done."]


def test_a_citation_that_does_not_exist_is_removed_before_the_paragraph_is_released() -> None:
    assert stream(["Errors rose [T1][T2][E9].\n\n"], frozenset({"T1"})) == ["Errors rose [T1]."]


def test_links_to_unknown_hosts_are_defanged_before_the_paragraph_is_released() -> None:
    (paragraph,) = stream(["See [the page](http://evil.example/x) now."])
    assert "http://evil.example" not in paragraph and "](" not in paragraph


def test_more_than_one_blank_line_between_paragraphs_gives_no_empty_paragraph() -> None:
    assert stream(["One.\n\n\n\nTwo.\n\n"]) == ["One.", "Two."]


def test_a_blank_line_inside_a_code_fence_does_not_split_the_paragraph() -> None:
    paragraphs = stream(["Run this:\n\n```\nline one\n\nline two\n```\n\nThen wait."])
    assert len(paragraphs) == 3
    assert "line one" in paragraphs[1] and "line two" in paragraphs[1]


def test_the_follow_up_section_is_never_released() -> None:
    paragraphs = stream([f"The answer [T1].\n\n{FOLLOW_UP_MARKER}\nWhich alerts fired?\nWhat changed?"], frozenset({"T1"}))
    assert paragraphs == ["The answer [T1]."]


def test_a_marker_directly_after_the_last_line_without_a_blank_line_still_cuts_the_text_there() -> None:
    assert stream([f"The answer.\n{FOLLOW_UP_MARKER}\nQ1\n\nQ2"]) == ["The answer."]


def test_text_that_arrives_after_the_marker_is_ignored_even_in_later_chunks() -> None:
    streamer = AnswerTextStreamer(frozenset())
    streamer.feed(f"A.\n\n{FOLLOW_UP_MARKER}\nQ1")
    assert streamer.feed("\n\nmore questions\n\n") == []
    assert streamer.finish() == []


def test_an_empty_stream_gives_nothing() -> None:
    assert stream([]) == [] and stream(["", "  \n\n "]) == []


def test_adjacent_citations_survive_the_sanitiser_as_two_citations() -> None:
    assert stream(["Both agree [T1][T2]." + chr(10) * 2], frozenset({"T1", "T2"})) == ["Both agree [T1] [T2]."]

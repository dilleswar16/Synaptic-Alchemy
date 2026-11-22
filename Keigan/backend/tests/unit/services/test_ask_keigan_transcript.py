"""keigan/services/ask_keigan_transcript.py: everything the model is given as data before and between turns (spec 23, 4.8)."""

from __future__ import annotations

import pytest

from keigan.ai.ask_keigan_answer_format import HISTORY_SECTION_TITLE, QUESTION_SECTION_TITLE
from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.llm_gateway import AgentToolRequest, AgentTurnResult, PromptSection
from keigan.ai.ask_keigan_mock_planner import AskKeiganFeature
from keigan.ai.operating_notes_prompt import OPERATING_NOTES_TITLE
from keigan.ai.tool_registry import AskKeiganScope
from keigan.entities.status_values import ConversationScope, ToolCallingMode
from keigan.services.ask_keigan_scopes import ScopeProfile
from keigan.services.ask_keigan_transcript import ConversationTurn, assistant_turn_entry, build_initial_transcript, tool_result_entry
from keigan.utils.pii_masker import PiiMasker


def profile(*, notes: str | None = None, sections: tuple[PromptSection, ...] = ()) -> ScopeProfile:
    return ScopeProfile(
        scope=AskKeiganScope.INVESTIGATION, conversation_scope=ConversationScope.INVESTIGATION, prompt_key="ask_keigan_investigation", feature_name=AskKeiganFeature.INVESTIGATION,
        readable_applications=(), offered_tools=(), bound_arguments={}, context_sections=sections, operating_notes_text=notes, accepted_citation_prefixes=frozenset({"T"}),
        reference_citations={}, budget_application_id=None, maximum_tool_calls=6, prompt_variables={},
    )


def sections_of(transcript) -> list[PromptSection]:
    assert all(entry.kind == "data" for entry in transcript)
    return [entry.section for entry in transcript]


def test_the_transcript_is_the_scope_context_then_the_history_then_the_question_all_as_data() -> None:
    digest = PromptSection("Investigation context", "digest text", is_untrusted=True, source_label="investigation:i1")
    transcript = build_initial_transcript(profile(sections=(digest,)), PiiMasker(), [ConversationTurn("user", "Earlier question"), ConversationTurn("assistant", "Earlier answer")], "What changed?")
    titles = [section.title for section in sections_of(transcript)]
    assert titles == ["Investigation context", HISTORY_SECTION_TITLE, QUESTION_SECTION_TITLE]
    history, question = sections_of(transcript)[1:]
    assert history.content == "user: Earlier question\nassistant: Earlier answer" and history.is_untrusted and history.source_label == "chat:history"
    assert question.content == "What changed?" and question.is_untrusted and question.source_label == "chat:user-question"


def test_the_scope_context_is_masked_with_the_run_masker_like_everything_else_the_model_reads() -> None:
    masker = PiiMasker()
    digest = PromptSection("Investigation context", "Reported by rui.reader@keigan.local", is_untrusted=True, source_label="investigation:i1")
    (context, *_) = sections_of(build_initial_transcript(profile(sections=(digest,)), masker, [], "Mail rui.reader@keigan.local"))
    assert context.content == "Reported by <EMAIL_1>" and context.is_untrusted and context.source_label == "investigation:i1"
    assert masker.mask_text("rui.reader@keigan.local") == "<EMAIL_1>"


def test_without_earlier_turns_the_history_says_so() -> None:
    history = sections_of(build_initial_transcript(profile(), PiiMasker(), [], "Hello?"))[0]
    assert history.title == HISTORY_SECTION_TITLE and history.content == "(none)"


def test_only_the_last_turns_are_kept_and_each_is_cut_to_its_character_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    safety_settings = get_ai_safety_settings()
    monkeypatch.setattr(safety_settings, "chat_history_turn_limit", 2)
    monkeypatch.setattr(safety_settings, "chat_history_turn_characters", 10)
    turns = [ConversationTurn("user", "first"), ConversationTurn("assistant", "second"), ConversationTurn("user", "third turn is long enough to be cut")]
    history = sections_of(build_initial_transcript(profile(), PiiMasker(), turns, "Q?"))[0]
    lines = history.content.splitlines()
    assert len(lines) == 2 and lines[0] == "assistant: second" and lines[1].startswith("user: third tur") and "enough" not in lines[1]


def test_the_operating_notes_are_untrusted_masked_guidance_placed_before_the_conversation() -> None:
    masker = PiiMasker()
    transcript = build_initial_transcript(profile(notes="Page ops.lead@keigan.local first."), masker, [], "Q?")
    notes = sections_of(transcript)[0]
    assert notes.title == OPERATING_NOTES_TITLE and notes.is_untrusted is True
    assert notes.content == "Page <EMAIL_1> first."
    assert [section.title for section in sections_of(transcript)][1:] == [HISTORY_SECTION_TITLE, QUESTION_SECTION_TITLE]


def test_a_placeholder_means_the_same_person_in_the_notes_and_in_what_the_run_masker_sees_later() -> None:
    masker = PiiMasker()
    build_initial_transcript(profile(notes="Page ops.lead@keigan.local first."), masker, [], "Q?")
    assert masker.mask_text("mail ops.lead@keigan.local") == "mail <EMAIL_1>"


def test_without_notes_there_is_no_notes_section() -> None:
    assert OPERATING_NOTES_TITLE not in [section.title for section in sections_of(build_initial_transcript(profile(notes="  "), PiiMasker(), [], "Q?"))]


def test_an_earlier_model_turn_keeps_its_text_and_its_tool_requests() -> None:
    request = AgentToolRequest(request_id="c1", tool_name="get_evidence", arguments={"evidence_code": "E1"})
    result = AgentTurnResult(text="Checking.", tool_requests=(request,), finish="tool_requests", input_token_count=1, output_token_count=1, token_counts_estimated=True, model_name="m", tool_calling_mode=ToolCallingMode.NATIVE)
    entry = assistant_turn_entry(result)
    assert (entry.kind, entry.text, entry.tool_requests) == ("assistant", "Checking.", (request,))


def test_a_tool_result_is_matched_to_its_request_by_id_and_name() -> None:
    request = AgentToolRequest(request_id="c1", tool_name="get_evidence", arguments={})
    entry = tool_result_entry(request, "<untrusted_data>x</untrusted_data>")
    assert (entry.kind, entry.tool_request_id, entry.tool_name, entry.tool_result_text) == ("tool_result", "c1", "get_evidence", "<untrusted_data>x</untrusted_data>")

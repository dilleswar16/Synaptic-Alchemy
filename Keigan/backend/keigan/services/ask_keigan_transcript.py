"""The conversation the model is given in an Ask Keigan answer: prompt sections as data, earlier model turns and tool results (spec 23, 4.8).

Everything a person or a data source wrote (the investigation digest, the team's operating notes, earlier turns, the question) is an untrusted section, so
the gateway spotlights it and the model treats it as information, never as instructions. Earlier assistant turns are data too: they are not verified.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.ask_keigan_answer_format import HISTORY_SECTION_TITLE, QUESTION_SECTION_TITLE
from keigan.ai.llm_gateway import AgentToolRequest, AgentTranscriptEntry, AgentTurnResult, PromptSection
from keigan.ai.operating_notes_prompt import build_operating_notes_section
from keigan.services.ask_keigan_scopes import ScopeProfile
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.text_utils import truncate_text

NO_EARLIER_TURNS = "(none)"
HISTORY_SOURCE_LABEL = "chat:history"
QUESTION_SOURCE_LABEL = "chat:user-question"


@dataclass(frozen=True)
class ConversationTurn:
    """One earlier message of the conversation, already masked."""

    role: str
    content: str


def build_initial_transcript(profile: ScopeProfile, masker: PiiMasker, history: Sequence[ConversationTurn], question_text: str) -> list[AgentTranscriptEntry]:
    notes_section = build_operating_notes_section(profile.operating_notes_text, masker)  # masked with the run's masker, so a placeholder means one person in every step
    sections = [
        *(replace(section, content=masker.mask_text(section.content)) for section in profile.context_sections), *([notes_section] if notes_section else []),
        PromptSection(HISTORY_SECTION_TITLE, _history_text(history), is_untrusted=True, source_label=HISTORY_SOURCE_LABEL),
        PromptSection(QUESTION_SECTION_TITLE, question_text, is_untrusted=True, source_label=QUESTION_SOURCE_LABEL),
    ]
    return [AgentTranscriptEntry(kind="data", section=section) for section in sections]


def assistant_turn_entry(turn_result: AgentTurnResult) -> AgentTranscriptEntry:
    return AgentTranscriptEntry(kind="assistant", text=turn_result.text, tool_requests=turn_result.tool_requests)


def tool_result_entry(request: AgentToolRequest, result_text: str) -> AgentTranscriptEntry:
    return AgentTranscriptEntry(kind="tool_result", tool_request_id=request.request_id, tool_name=request.tool_name, tool_result_text=result_text)


def _history_text(history: Sequence[ConversationTurn]) -> str:
    safety_settings = get_ai_safety_settings()
    recent_turns = history[-safety_settings.chat_history_turn_limit:] if safety_settings.chat_history_turn_limit else []
    return "\n".join(f"{turn.role}: {truncate_text(turn.content, safety_settings.chat_history_turn_characters)}" for turn in recent_turns) or NO_EARLIER_TURNS

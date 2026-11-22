"""Chat DTOs (Keigan AI chat and investigation chat)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel


MESSAGE_TEXT_MAXIMUM_CHARACTERS = 4000  # the longest question a person can send, in every chat endpoint


class ConversationCreateRequest(ApiModel):
    conversation_scope: str = "keigan_ai_chat"  # keigan_ai_chat | investigation
    application_ids: list[str] | None = None
    investigation_id: str | None = None


class ConversationUpdateRequest(ApiModel):
    conversation_title: str | None = Field(default=None, max_length=300)
    application_ids: list[str] | None = None


class ChatMessageResponse(ApiModel):
    message_id: str
    conversation_id: str
    author_role: str
    author_display_name: str | None = None
    message_text: str
    message_payload: dict[str, Any] | None = None
    created_at: datetime


class ConversationResponse(ApiModel):
    conversation_id: str
    conversation_scope: str
    application_ids: list[str] = Field(default_factory=list)
    investigation_id: str | None = None
    conversation_title: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class SendMessageRequest(ApiModel):
    message_text: str = Field(min_length=1, max_length=MESSAGE_TEXT_MAXIMUM_CHARACTERS)


class SuggestedPromptResponse(ApiModel):
    prompt_text: str
    category: str

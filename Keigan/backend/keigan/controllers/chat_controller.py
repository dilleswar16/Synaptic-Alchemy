"""Chat endpoints: Keigan AI chat conversations and investigation chat."""

from fastapi import APIRouter, Depends, Query, Response, status

from keigan.config.database_config import provide
from keigan.dtos.chat_dtos import (
    ChatMessageResponse, ConversationCreateRequest, ConversationDetailResponse, ConversationResponse, ConversationUpdateRequest, SendMessageRequest, SuggestedPromptResponse,
)
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.chat_service import ChatService

router = APIRouter(prefix="/api", tags=["Chat"])


@router.get("/chat/conversations", response_model=list[ConversationResponse])
async def list_conversations(scope: str | None = Query(default=None), current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> list[ConversationResponse]:
    return await service.list_conversations(current_user, scope)


@router.post("/chat/conversations", response_model=ConversationDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(request: ConversationCreateRequest, current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> ConversationDetailResponse:
    return await service.create_conversation(current_user, request)


@router.get("/chat/suggested-prompts", response_model=list[SuggestedPromptResponse])
async def suggested_prompts(application_id: str | None = Query(default=None, alias="applicationId"), current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> list[SuggestedPromptResponse]:
    return await service.suggested_prompts(current_user, application_id)


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str, current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> ConversationDetailResponse:
    return await service.get_conversation(current_user, conversation_id)


@router.patch("/chat/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: str, request: ConversationUpdateRequest, current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> ConversationResponse:
    return await service.update_conversation(current_user, conversation_id, request)


@router.delete("/chat/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> Response:
    await service.delete_conversation(current_user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chat/conversations/{conversation_id}/messages", response_model=ChatMessageResponse)
async def send_message(conversation_id: str, request: SendMessageRequest, current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> ChatMessageResponse:
    return await service.send_message(current_user, conversation_id, request)

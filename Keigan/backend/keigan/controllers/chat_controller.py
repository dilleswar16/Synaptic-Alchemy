"""Chat endpoints: Keigan AI chat conversations and investigation chat."""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from keigan.config.database_config import provide
from keigan.dtos.ask_keigan_dtos import AnswerRequest, AnswerRunView, CancelAnswerResponse, StepOutputView
from keigan.dtos.chat_dtos import (
    ChatMessageResponse, ConversationCreateRequest, ConversationDetailResponse, ConversationResponse, ConversationUpdateRequest, SendMessageRequest, SuggestedPromptResponse,
)
from keigan.exceptions.keigan_exceptions import NotAcceptableException
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.ask_keigan_service import AskKeiganService
from keigan.services.chat_service import ChatService

router = APIRouter(prefix="/api", tags=["Chat"])
EVENT_STREAM_MEDIA_TYPE = "text/event-stream"
# nginx must not buffer this response (the other responses keep their buffering); the connection stays open for the length of the answer.
EVENT_STREAM_HEADERS = {"X-Accel-Buffering": "no", "Connection": "keep-alive"}


def require_event_stream_accepted(request: Request) -> None:
    if EVENT_STREAM_MEDIA_TYPE not in request.headers.get("accept", ""):
        raise NotAcceptableException(f"This endpoint answers with {EVENT_STREAM_MEDIA_TYPE}; send an Accept header that includes it.")


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
async def delete_conversation(conversation_id: str, current_user: CurrentUser = Depends(get_current_user), service: AskKeiganService = Depends(provide(AskKeiganService))) -> Response:
    await service.delete_conversation(current_user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chat/conversations/{conversation_id}/messages", response_model=ChatMessageResponse)
async def send_message(conversation_id: str, request: SendMessageRequest, current_user: CurrentUser = Depends(get_current_user), service: ChatService = Depends(provide(ChatService))) -> ChatMessageResponse:
    return await service.send_message(current_user, conversation_id, request)


@router.post("/chat/conversations/{conversation_id}/answers", response_class=StreamingResponse, dependencies=[Depends(require_event_stream_accepted)])
async def start_answer(
    conversation_id: str, request: AnswerRequest, current_user: CurrentUser = Depends(get_current_user), service: AskKeiganService = Depends(provide(AskKeiganService)),
) -> StreamingResponse:
    started = await service.start(current_user, conversation_id, request)
    return StreamingResponse(service.stream(started.channel), media_type=EVENT_STREAM_MEDIA_TYPE, headers=EVENT_STREAM_HEADERS)


@router.get("/chat/answer-runs/{answer_run_id}", response_model=AnswerRunView)
async def get_answer_run(answer_run_id: str, current_user: CurrentUser = Depends(get_current_user), service: AskKeiganService = Depends(provide(AskKeiganService))) -> AnswerRunView:
    return await service.snapshot(current_user, answer_run_id)


@router.get("/chat/answer-runs/{answer_run_id}/steps/{run_step_id}/output", response_model=StepOutputView)
async def get_step_output(
    answer_run_id: str, run_step_id: str, current_user: CurrentUser = Depends(get_current_user), service: AskKeiganService = Depends(provide(AskKeiganService)),
) -> StepOutputView:
    return await service.step_output(current_user, answer_run_id, run_step_id)


@router.post("/chat/answer-runs/{answer_run_id}/cancel", response_model=CancelAnswerResponse, status_code=status.HTTP_202_ACCEPTED)
async def cancel_answer_run(answer_run_id: str, current_user: CurrentUser = Depends(get_current_user), service: AskKeiganService = Depends(provide(AskKeiganService))) -> CancelAnswerResponse:
    return await service.cancel(current_user, answer_run_id)

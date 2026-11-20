"""Teams bot messaging endpoint (public: authenticated by the Bot Framework JWT, not by a Keigan user token)."""

from typing import Any

from fastapi import APIRouter, Depends, Header, status

from keigan.config import application_context
from keigan.config.database_config import provide
from keigan.config.settings import get_settings
from keigan.integrations.bot_framework_client import BotFrameworkClient
from keigan.services.teams_chat_service import TeamsChatService

router = APIRouter(prefix="/api", tags=["Teams bot"])


@router.post("/teams/messages", status_code=status.HTTP_200_OK)
async def receive_teams_activity(activity: dict[str, Any], authorization: str | None = Header(None), chat_service: TeamsChatService = Depends(provide(TeamsChatService))) -> dict[str, str]:
    await BotFrameworkClient(get_settings(), application_context.secret_store()).validate_inbound_request(authorization, activity.get("serviceUrl"))
    await chat_service.handle_bot_activity(activity)
    return {"status": "ok"}

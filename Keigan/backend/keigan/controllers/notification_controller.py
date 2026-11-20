"""Notification endpoints: stakeholders, directory search, outbox and the (simulated) Teams incident chat."""

from fastapi import APIRouter, Depends, Query, Response, status

from keigan.config.database_config import provide
from keigan.dtos.common_dtos import PagedResult
from keigan.dtos.notification_dtos import (
    DirectoryUserResponse, NotificationDeliveryDetail, NotificationDeliverySummary, StakeholderCreateRequest, StakeholderResponse, StakeholderTestResponse, StakeholderUpdateRequest, TeamsChatPostRequest,
    TeamsChatResponse,
)
from keigan.entities.incident_entities import Incident
from keigan.exceptions.keigan_exceptions import NotFoundException
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin, require_application_reader, require_keigan_admin
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.notification_service import NotificationService
from keigan.services.stakeholder_service import StakeholderService
from keigan.services.teams_chat_service import TeamsChatService

router = APIRouter(prefix="/api", tags=["Notifications"])


@router.get("/applications/{application_id}/stakeholders", response_model=list[StakeholderResponse])
async def list_stakeholders(application_id: str, _: CurrentUser = Depends(require_application_reader), service: StakeholderService = Depends(provide(StakeholderService))) -> list[StakeholderResponse]:
    return await service.list_stakeholders(application_id)


@router.post("/applications/{application_id}/stakeholders", response_model=StakeholderResponse, status_code=status.HTTP_201_CREATED)
async def create_stakeholder(application_id: str, request: StakeholderCreateRequest, current_user: CurrentUser = Depends(require_application_admin), service: StakeholderService = Depends(provide(StakeholderService))) -> StakeholderResponse:
    return await service.create_stakeholder(current_user, application_id, request)


@router.patch("/applications/{application_id}/stakeholders/{stakeholder_id}", response_model=StakeholderResponse)
async def update_stakeholder(application_id: str, stakeholder_id: str, request: StakeholderUpdateRequest, current_user: CurrentUser = Depends(require_application_admin), service: StakeholderService = Depends(provide(StakeholderService))) -> StakeholderResponse:
    return await service.update_stakeholder(current_user, application_id, stakeholder_id, request)


@router.delete("/applications/{application_id}/stakeholders/{stakeholder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stakeholder(application_id: str, stakeholder_id: str, current_user: CurrentUser = Depends(require_application_admin), service: StakeholderService = Depends(provide(StakeholderService))) -> Response:
    await service.delete_stakeholder(current_user, application_id, stakeholder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/applications/{application_id}/stakeholders/{stakeholder_id}/test", response_model=StakeholderTestResponse)
async def send_stakeholder_test(application_id: str, stakeholder_id: str, current_user: CurrentUser = Depends(require_application_admin), service: StakeholderService = Depends(provide(StakeholderService))) -> StakeholderTestResponse:
    return await service.send_test(current_user, application_id, stakeholder_id)


@router.get("/directory/users/search", response_model=list[DirectoryUserResponse])
async def search_directory_users(query: str = Query("", max_length=100), _: CurrentUser = Depends(get_current_user), service: StakeholderService = Depends(provide(StakeholderService))) -> list[DirectoryUserResponse]:
    return await service.search_directory(query)


@router.get("/outbox", response_model=PagedResult[NotificationDeliverySummary])
async def list_outbox(
    application_id: str | None = Query(None, alias="applicationId"), notification_type: str | None = Query(None, alias="notificationType"), delivery_status: str | None = Query(None, alias="deliveryStatus"),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200, alias="pageSize"), _: CurrentUser = Depends(require_keigan_admin), service: NotificationService = Depends(provide(NotificationService)),
) -> PagedResult[NotificationDeliverySummary]:
    return await service.list_outbox(application_id, notification_type, delivery_status, page, page_size)


@router.get("/outbox/{delivery_id}", response_model=NotificationDeliveryDetail)
async def get_outbox_delivery(delivery_id: str, _: CurrentUser = Depends(require_keigan_admin), service: NotificationService = Depends(provide(NotificationService))) -> NotificationDeliveryDetail:
    return await service.get_outbox_delivery(delivery_id)


async def _readable_incident(incident_id: str, current_user: CurrentUser, authorization_service: AuthorizationService, chat_service: TeamsChatService) -> Incident:
    incident = await chat_service.session.get(Incident, incident_id)
    if incident is None:
        raise NotFoundException("Incident not found.")
    await authorization_service.ensure_application_reader(current_user, incident.application_id)
    return incident


@router.get("/incidents/{incident_id}/teams-chat", response_model=TeamsChatResponse)
async def get_teams_chat(incident_id: str, current_user: CurrentUser = Depends(get_current_user), chat_service: TeamsChatService = Depends(provide(TeamsChatService))) -> TeamsChatResponse:
    await _readable_incident(incident_id, current_user, AuthorizationService(chat_service.session), chat_service)
    return await chat_service.get_chat_view(incident_id)


@router.post("/incidents/{incident_id}/teams-chat/messages", response_model=TeamsChatResponse)
async def post_teams_chat_message(incident_id: str, request: TeamsChatPostRequest, current_user: CurrentUser = Depends(get_current_user), chat_service: TeamsChatService = Depends(provide(TeamsChatService))) -> TeamsChatResponse:
    incident = await _readable_incident(incident_id, current_user, AuthorizationService(chat_service.session), chat_service)
    response = await chat_service.post_user_message(incident_id, current_user, request.message_text)
    await AuditService(chat_service.session).record(current_user, "teams_chat.post", target_entity_type="incident", target_entity_id=incident_id, application_id=incident.application_id)
    return response

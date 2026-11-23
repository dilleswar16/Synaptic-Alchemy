"""Action item endpoints: the follow-ups after incidents, tracked to done (spec 29)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from keigan.config.database_config import provide
from keigan.controllers.incident_controller import split_values
from keigan.dtos.action_item_dtos import ActionItemCreateRequest, ActionItemDto, ActionItemOverviewResponse, ActionItemStatusRequest, ActionItemUpdateRequest
from keigan.dtos.common_dtos import PagedResult
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin
from keigan.services.action_item_overview_service import ActionItemOverviewService
from keigan.services.action_item_service import ActionItemService

router = APIRouter(prefix="/api", tags=["Action items"])


@router.get("/action-items", response_model=PagedResult[ActionItemDto], response_model_by_alias=True)
async def list_action_items(
    application_ids: str | None = Query(default=None, alias="applicationIds"),
    statuses: str | None = Query(default=None, description="Comma separated; the default is the unfinished tracked items (open, in progress, blocked)."),
    priorities: str | None = Query(default=None),
    sources: str | None = Query(default=None),
    owner: str | None = Query(default=None, max_length=36, description="'me', 'unassigned' or a team member id."),
    overdue_only: bool = Query(default=False, alias="overdueOnly"),
    incident_id: str | None = Query(default=None, alias="incidentId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    current_user: CurrentUser = Depends(get_current_user),
    action_item_service: ActionItemService = Depends(provide(ActionItemService)),
) -> PagedResult[ActionItemDto]:
    return await action_item_service.list_items(
        current_user, application_ids=split_values(application_ids), statuses=split_values(statuses), priorities=split_values(priorities), source_kinds=split_values(sources),
        owner=owner, overdue_only=overdue_only, incident_id=incident_id, page=page, page_size=page_size,
    )


@router.get("/action-items/overview", response_model=ActionItemOverviewResponse, response_model_by_alias=True)
async def get_action_items_overview(
    application_ids: str | None = Query(default=None, alias="applicationIds"),
    days: int | None = Query(default=None, ge=1, description="Look-back period in days; the default and the longest period are settings."),
    current_user: CurrentUser = Depends(get_current_user),
    overview_service: ActionItemOverviewService = Depends(provide(ActionItemOverviewService)),
) -> ActionItemOverviewResponse:
    """Completion figures, what needs attention and which incidents came back, for the applications the caller may read. Counts per application, never a ranking of people."""
    return await overview_service.overview(current_user, split_values(application_ids), days)


@router.get("/postmortems/{postmortem_id}/action-items", response_model=list[ActionItemDto], response_model_by_alias=True)
async def list_postmortem_action_items(
    postmortem_id: str, current_user: CurrentUser = Depends(get_current_user), action_item_service: ActionItemService = Depends(provide(ActionItemService)),
) -> list[ActionItemDto]:
    return await action_item_service.list_for_postmortem(current_user, postmortem_id)


@router.get("/action-items/{action_item_id}", response_model=ActionItemDto, response_model_by_alias=True)
async def get_action_item(action_item_id: str, current_user: CurrentUser = Depends(get_current_user), action_item_service: ActionItemService = Depends(provide(ActionItemService))) -> ActionItemDto:
    return await action_item_service.get(current_user, action_item_id)


@router.post("/applications/{application_id}/action-items", response_model=ActionItemDto, response_model_by_alias=True, status_code=201)
async def create_action_item(
    application_id: str, request: ActionItemCreateRequest, current_user: CurrentUser = Depends(require_application_admin),
    action_item_service: ActionItemService = Depends(provide(ActionItemService)),
) -> ActionItemDto:
    """A manual item starts open (a person wrote it, so it is already accepted). Application admins only."""
    return await action_item_service.create(current_user, application_id, request)


@router.patch("/action-items/{action_item_id}", response_model=ActionItemDto, response_model_by_alias=True)
async def update_action_item(
    action_item_id: str, request: ActionItemUpdateRequest, current_user: CurrentUser = Depends(get_current_user), action_item_service: ActionItemService = Depends(provide(ActionItemService)),
) -> ActionItemDto:
    """Application admins change any field; the owner may edit the details. Moving a tracked item's due date is counted and shown."""
    return await action_item_service.update(current_user, action_item_id, request)


@router.post("/action-items/{action_item_id}/accept", response_model=ActionItemDto, response_model_by_alias=True)
async def accept_action_item(
    action_item_id: str, request: ActionItemUpdateRequest | None = None, current_user: CurrentUser = Depends(get_current_user),
    action_item_service: ActionItemService = Depends(provide(ActionItemService)),
) -> ActionItemDto:
    """Accepts an AI suggestion (optionally with edits made in the same step): it becomes open and tracked. Application admins only."""
    return await action_item_service.accept(current_user, action_item_id, request)


@router.post("/action-items/{action_item_id}/status", response_model=ActionItemDto, response_model_by_alias=True)
async def change_action_item_status(
    action_item_id: str, request: ActionItemStatusRequest, current_user: CurrentUser = Depends(get_current_user), action_item_service: ActionItemService = Depends(provide(ActionItemService)),
) -> ActionItemDto:
    """Moves the item to another status. Blocked and won't do need a reason; 422 says what is not allowed."""
    return await action_item_service.change_status(current_user, action_item_id, request)


@router.delete("/action-items/{action_item_id}", status_code=204, response_class=Response)
async def discard_action_item(action_item_id: str, current_user: CurrentUser = Depends(get_current_user), action_item_service: ActionItemService = Depends(provide(ActionItemService))) -> Response:
    """Discards an AI suggestion nobody accepted. A tracked item is never deleted: close it as won't do."""
    await action_item_service.discard(current_user, action_item_id)
    return Response(status_code=204)

"""Dashboard endpoints."""

from fastapi import APIRouter, Depends, Query

from keigan.config.database_config import provide
from keigan.dtos.dashboard_dtos import HomeDashboardResponse
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/dashboard/home", response_model=HomeDashboardResponse)
async def get_home_dashboard(
    application_ids: str | None = Query(default=None, alias="applicationIds"), current_user: CurrentUser = Depends(get_current_user), service: DashboardService = Depends(provide(DashboardService))
) -> HomeDashboardResponse:
    requested = [item for item in (application_ids or "").split(",") if item] or None
    return await service.get_home(current_user, requested)

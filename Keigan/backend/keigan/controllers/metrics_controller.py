"""Reliability metrics endpoint: incident and AI numbers for the applications the caller can read."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from keigan.config.database_config import provide
from keigan.dtos.metrics_dtos import MetricsOverviewResponse
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.reliability_metrics_service import ReliabilityMetricsService

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("/overview", response_model=MetricsOverviewResponse)
async def get_metrics_overview(
    application_id: str | None = Query(default=None, alias="applicationId"), days: int | None = Query(default=None), period_start: datetime | None = Query(default=None, alias="from"),
    period_end: datetime | None = Query(default=None, alias="to"), current_user: CurrentUser = Depends(get_current_user), service: ReliabilityMetricsService = Depends(provide(ReliabilityMetricsService)),
) -> MetricsOverviewResponse:
    """Every figure of the page in one answer. The period is ``days`` back from now, or ``from`` (and ``to``); the longest allowed is a setting."""
    return await service.overview(current_user, application_id, days, period_start, period_end)

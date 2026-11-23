"""Error budget policy endpoints: what an incident cost the SLOs' budgets, and (later steps) the policy and its breaches (spec 30)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from keigan.config.database_config import provide
from keigan.dtos.error_budget_dtos import IncidentBudgetImpactResponse
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.error_budget_service import ErrorBudgetService

router = APIRouter(prefix="/api", tags=["Error budget"])


@router.get("/incidents/{incident_id}/budget-impact", response_model=IncidentBudgetImpactResponse, response_model_by_alias=True)
async def get_incident_budget_impact(
    incident_id: str, current_user: CurrentUser = Depends(get_current_user), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> IncidentBudgetImpactResponse:
    """Per SLO the share of its error budget the incident used, with the inputs. Provisional while the incident is open and for a day after; information even when the policy is off."""
    return await error_budget_service.incident_budget_impact(current_user, incident_id)

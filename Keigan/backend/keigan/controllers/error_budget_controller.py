"""Error budget policy endpoints: the team's policy, what an incident cost the SLOs' budgets, and the breaches of the policy (spec 30)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from keigan.config.database_config import provide
from keigan.controllers.incident_controller import split_values
from keigan.dtos.action_item_dtos import ActionItemCreateRequest, ActionItemDto
from keigan.dtos.error_budget_dtos import ErrorBudgetBreachDto, ErrorBudgetPolicyRequest, ErrorBudgetPolicyResponse, IncidentBudgetImpactResponse, WaiveBreachRequest
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin, require_application_reader
from keigan.services.error_budget_service import ErrorBudgetService

router = APIRouter(prefix="/api", tags=["Error budget"])


@router.get("/applications/{application_id}/error-budget-policy", response_model=ErrorBudgetPolicyResponse, response_model_by_alias=True)
async def get_error_budget_policy(
    application_id: str, current_user: CurrentUser = Depends(require_application_reader), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> ErrorBudgetPolicyResponse:
    """The policy in force. A team that never saved one gets 'off' with the default thresholds; reading writes nothing."""
    return await error_budget_service.get_policy(current_user, application_id)


@router.put("/applications/{application_id}/error-budget-policy", response_model=ErrorBudgetPolicyResponse, response_model_by_alias=True)
async def save_error_budget_policy(
    application_id: str, request: ErrorBudgetPolicyRequest, current_user: CurrentUser = Depends(require_application_admin), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> ErrorBudgetPolicyResponse:
    """Application admins. A null threshold or window means the default; out-of-range numbers answer 422 with the field."""
    return await error_budget_service.save_policy(current_user, application_id, request)


@router.get("/incidents/{incident_id}/budget-impact", response_model=IncidentBudgetImpactResponse, response_model_by_alias=True)
async def get_incident_budget_impact(
    incident_id: str, current_user: CurrentUser = Depends(get_current_user), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> IncidentBudgetImpactResponse:
    """Per SLO the share of its error budget the incident used, with the inputs, and the policy breach when there is one. Information even when the policy is off."""
    return await error_budget_service.incident_budget_impact(current_user, incident_id)


@router.get("/error-budget-breaches", response_model=list[ErrorBudgetBreachDto], response_model_by_alias=True)
async def list_error_budget_breaches(
    application_ids: str | None = Query(default=None, alias="applicationIds"), statuses: str | None = Query(default=None, description="Comma separated; the default is open."),
    kinds: str | None = Query(default=None), current_user: CurrentUser = Depends(get_current_user), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> list[ErrorBudgetBreachDto]:
    return await error_budget_service.list_breaches(current_user, split_values(application_ids), split_values(statuses), split_values(kinds))


@router.post("/error-budget-breaches/{breach_id}/waive", response_model=ErrorBudgetBreachDto, response_model_by_alias=True)
async def waive_error_budget_breach(
    breach_id: str, request: WaiveBreachRequest, current_user: CurrentUser = Depends(get_current_user), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> ErrorBudgetBreachDto:
    """Application admins, with a written reason. The requirement is waived, the change is audited and shown on the postmortem."""
    return await error_budget_service.waive(current_user, breach_id, request.reason_text)


@router.post("/error-budget-breaches/{breach_id}/action-items", response_model=ActionItemDto, response_model_by_alias=True, status_code=201)
async def add_action_item_for_breach(
    breach_id: str, request: ActionItemCreateRequest, current_user: CurrentUser = Depends(get_current_user), error_budget_service: ErrorBudgetService = Depends(provide(ErrorBudgetService)),
) -> ActionItemDto:
    """Outage class breaches only: creates the top-priority item the policy asks for (the priority is forced to top)."""
    return await error_budget_service.create_class_item(current_user, breach_id, request)

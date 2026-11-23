"""What the API shows of the error budget policy: reading, access checks and the response shapes (spec 30). The evaluation itself lives in ``error_budget_policy_service``."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.dtos.error_budget_dtos import BudgetPolicySummaryDto, IncidentBudgetImpactResponse
from keigan.entities.incident_entities import Incident
from keigan.exceptions.keigan_exceptions import NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.authorization_service import AuthorizationService
from keigan.services.error_budget_policy_service import effective_policy
from keigan.services.incident_budget_impact_service import IncidentBudgetImpactService, impact_dto


class ErrorBudgetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def incident_budget_impact(self, current_user: CurrentUser, incident_id: str) -> IncidentBudgetImpactResponse:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundException("The incident was not found.")
        await AuthorizationService(self.session).ensure_application_reader(current_user, incident.application_id)
        policy = await effective_policy(self.session, incident.application_id)
        rows = await IncidentBudgetImpactService(self.session).impacts_of(incident_id)
        return IncidentBudgetImpactResponse(
            incident_id=incident_id,
            policy=BudgetPolicySummaryDto(
                is_enabled=policy.is_enabled, single_incident_threshold_percent=policy.single_incident_threshold_percent,
                minimum_data_coverage_percent=self.settings.error_budget_policy_minimum_data_coverage_percent,
            ),
            impacts=[impact_dto(row) for row in rows],
        )

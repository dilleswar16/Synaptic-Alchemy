"""What the API does with the error budget policy: reading, saving, waiving, listing breaches and the access checks (spec 30). The evaluation itself lives in ``error_budget_policy_service``.

Readers see the policy, the impacts and the breaches of their applications. Application admins change the policy, waive a requirement (with a written reason) and add the action item an
outage-class breach asks for.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.config.settings import get_settings
from keigan.dtos.action_item_dtos import ActionItemCreateRequest, ActionItemDto
from keigan.dtos.error_budget_dtos import (
    BudgetPolicySummaryDto, ErrorBudgetBreachDto, ErrorBudgetPolicyRequest, ErrorBudgetPolicyResponse, IncidentBudgetImpactResponse, PolicyDefaultsDto, PolicyUsesDefaultDto,
)
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicy, ErrorBudgetPolicyBreach
from keigan.entities.incident_entities import Incident
from keigan.entities.status_values import ActionItemPriority, ActionItemSource, ErrorBudgetBreachKind, ErrorBudgetRequirementStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_service import ActionItemService
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.error_budget_policy_service import ErrorBudgetPolicyService, effective_policy
from keigan.services.incident_budget_impact_service import IncidentBudgetImpactService, impact_dto
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now



class ErrorBudgetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.authorization = AuthorizationService(session)

    # ── Impacts ────────────────────────────────────────────────────────────────
    async def incident_budget_impact(self, current_user: CurrentUser, incident_id: str) -> IncidentBudgetImpactResponse:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundException("The incident was not found.")
        await self.authorization.ensure_application_reader(current_user, incident.application_id)
        policy = await effective_policy(self.session, incident.application_id)
        rows = await IncidentBudgetImpactService(self.session).impacts_of(incident_id)
        breach = await self.session.scalar(select(ErrorBudgetPolicyBreach).where(ErrorBudgetPolicyBreach.incident_id == incident_id, ErrorBudgetPolicyBreach.breach_kind == ErrorBudgetBreachKind.SINGLE_INCIDENT))
        return IncidentBudgetImpactResponse(
            incident_id=incident_id,
            policy=BudgetPolicySummaryDto(
                is_enabled=policy.is_enabled, single_incident_threshold_percent=policy.single_incident_threshold_percent,
                minimum_data_coverage_percent=self.settings.error_budget_policy_minimum_data_coverage_percent,
            ),
            impacts=[impact_dto(row) for row in rows],
            breach=(await self._breach_dtos(current_user, [breach]))[0] if breach else None,
        )

    # ── The policy ─────────────────────────────────────────────────────────────
    async def get_policy(self, current_user: CurrentUser, application_id: str) -> ErrorBudgetPolicyResponse:
        await self.authorization.ensure_application_reader(current_user, application_id)
        return await self._policy_response(current_user, application_id)

    async def save_policy(self, current_user: CurrentUser, application_id: str, request: ErrorBudgetPolicyRequest) -> ErrorBudgetPolicyResponse:
        await self.authorization.ensure_application_admin(current_user, application_id)
        errors = self._range_errors(request)
        if errors:
            raise BusinessValidationException("The policy has values outside their range.", field_errors=errors)
        row = await self.session.scalar(select(ErrorBudgetPolicy).where(ErrorBudgetPolicy.application_id == application_id))
        if row is None:  # created on the first save only: a read never writes
            row = ErrorBudgetPolicy(application_id=application_id, created_by_user_principal_name=current_user.user_principal_name)
            self.session.add(row)
        changed = [
            name for name, old, new in (
                ("isEnabled", row.is_enabled, request.is_enabled), ("singleIncidentThresholdPercent", row.single_incident_threshold_percent, request.single_incident_threshold_percent),
                ("outageClassThresholdPercent", row.outage_class_threshold_percent, request.outage_class_threshold_percent), ("outageClassWindowDays", row.outage_class_window_days, request.outage_class_window_days),
            ) if old != new
        ]
        guidance = self._clean_guidance(request.exhausted_budget_guidance_text)
        if guidance != row.exhausted_budget_guidance_text:
            changed.append("exhaustedBudgetGuidanceText")
        row.is_enabled = request.is_enabled
        row.single_incident_threshold_percent, row.outage_class_threshold_percent, row.outage_class_window_days = (
            request.single_incident_threshold_percent, request.outage_class_threshold_percent, request.outage_class_window_days,
        )
        row.exhausted_budget_guidance_text = guidance
        row.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await AuditService(self.session).record(current_user, "error_budget_policy.update", target_entity_type="error_budget_policy", target_entity_id=row.error_budget_policy_id, application_id=application_id, action_details={"changed": changed})
        return await self._policy_response(current_user, application_id)

    def _range_errors(self, request: ErrorBudgetPolicyRequest) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        for field, value in (("singleIncidentThresholdPercent", request.single_incident_threshold_percent), ("outageClassThresholdPercent", request.outage_class_threshold_percent)):
            if value is not None and not 1 <= value <= 100:
                errors.append({"field": field, "message": "Must be between 1 and 100 percent."})
        maximum_window = self.settings.sli_raw_retention_days
        if request.outage_class_window_days is not None and not 7 <= request.outage_class_window_days <= maximum_window:
            errors.append({"field": "outageClassWindowDays", "message": f"Must be between 7 and {maximum_window} days, the SLI history Keigan keeps."})
        if request.exhausted_budget_guidance_text and len(request.exhausted_budget_guidance_text) > self.settings.error_budget_policy_guidance_maximum_characters:
            errors.append({"field": "exhaustedBudgetGuidanceText", "message": f"At most {self.settings.error_budget_policy_guidance_maximum_characters} characters."})
        return errors

    @staticmethod
    def _clean_guidance(text: str | None) -> str | None:
        cleaned = sanitize_ai_markdown(PiiMasker().mask_text(text.strip())) if text and text.strip() else None
        return cleaned or None

    async def _policy_response(self, current_user: CurrentUser, application_id: str) -> ErrorBudgetPolicyResponse:
        row = await self.session.scalar(select(ErrorBudgetPolicy).where(ErrorBudgetPolicy.application_id == application_id))
        policy = await effective_policy(self.session, application_id)
        settings = self.settings
        return ErrorBudgetPolicyResponse(
            application_id=application_id, is_enabled=policy.is_enabled, single_incident_threshold_percent=policy.single_incident_threshold_percent,
            outage_class_threshold_percent=policy.outage_class_threshold_percent, outage_class_window_days=policy.outage_class_window_days,
            uses_default=PolicyUsesDefaultDto(
                single_incident_threshold=row is None or row.single_incident_threshold_percent is None, outage_class_threshold=row is None or row.outage_class_threshold_percent is None,
                outage_class_window=row is None or row.outage_class_window_days is None,
            ),
            defaults=PolicyDefaultsDto(
                single_incident_threshold_percent=settings.error_budget_policy_single_incident_threshold_percent, outage_class_threshold_percent=settings.error_budget_policy_outage_class_threshold_percent,
                outage_class_window_days=settings.error_budget_policy_outage_class_window_days,
            ),
            maximum_outage_class_window_days=settings.sli_raw_retention_days, exhausted_budget_guidance_text=policy.exhausted_budget_guidance_text,
            guidance_maximum_characters=settings.error_budget_policy_guidance_maximum_characters, can_edit=await self.authorization.can_edit_application(current_user, application_id),
            updated_at=row.updated_at if row else None, updated_by=row.updated_by_user_principal_name if row else None,
        )

    # ── Breaches ───────────────────────────────────────────────────────────────
    async def list_breaches(self, current_user: CurrentUser, application_ids: list[str] | None, statuses: list[str] | None, kinds: list[str] | None) -> list[ErrorBudgetBreachDto]:
        scope = await self.authorization.scoped_application_ids(current_user, application_ids)
        if not scope:
            return []
        conditions = [ErrorBudgetPolicyBreach.application_id.in_(scope), ErrorBudgetPolicyBreach.requirement_status.in_(statuses or [ErrorBudgetRequirementStatus.OPEN.value])]
        if kinds:
            conditions.append(ErrorBudgetPolicyBreach.breach_kind.in_(kinds))
        breaches = list((await self.session.scalars(select(ErrorBudgetPolicyBreach).where(*conditions).order_by(ErrorBudgetPolicyBreach.detected_at.desc()))).all())
        return await self._breach_dtos(current_user, breaches)

    async def waive(self, current_user: CurrentUser, breach_id: str, reason_text: str) -> ErrorBudgetBreachDto:
        breach = await self._breach(breach_id)
        await self.authorization.ensure_application_admin(current_user, breach.application_id)
        if breach.requirement_status != ErrorBudgetRequirementStatus.OPEN:
            raise BusinessValidationException("Only an open requirement can be waived.")
        minimum = self.settings.error_budget_policy_waiver_minimum_characters
        reason = sanitize_ai_line(PiiMasker().mask_text(reason_text or ""), maximum_characters=1000)
        if len(reason.strip()) < minimum:
            raise BusinessValidationException(f"Say why in a reason of at least {minimum} characters.", field_errors=[{"field": "reasonText", "message": f"At least {minimum} characters."}])
        now = utc_now()
        breach.requirement_status, breach.waived_by_user_principal_name, breach.waiver_reason_text, breach.requirement_changed_at = ErrorBudgetRequirementStatus.WAIVED, current_user.user_principal_name, reason.strip(), now
        breach.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await AuditService(self.session).record(
            current_user, "error_budget_breach.waive", target_entity_type="error_budget_policy_breach", target_entity_id=breach_id, application_id=breach.application_id,
            action_details={"breachKind": breach.breach_kind, "incidentId": breach.incident_id},
        )
        return (await self._breach_dtos(current_user, [breach]))[0]

    async def create_class_item(self, current_user: CurrentUser, breach_id: str, request: ActionItemCreateRequest) -> ActionItemDto:
        """The top-priority item an outage-class breach asks for (priority is forced to top); it meets the requirement once accepted, which creating it does."""
        breach = await self._breach(breach_id)
        await self.authorization.ensure_application_admin(current_user, breach.application_id)
        if breach.breach_kind != ErrorBudgetBreachKind.OUTAGE_CLASS:
            raise BusinessValidationException("Only an outage class breach is met by adding an action item here. A single incident's item belongs to its postmortem.")
        item = await ActionItemService(self.session).create(
            current_user, breach.application_id, request.model_copy(update={"action_priority": ActionItemPriority.TOP, "incident_id": None, "postmortem_id": None}),
            source_kind=ActionItemSource.ERROR_BUDGET_POLICY, source_record_id=breach_id,
        )
        await ErrorBudgetPolicyService(self.session).refresh_class_requirement(breach)
        await self.session.flush()
        return item

    async def _breach(self, breach_id: str) -> ErrorBudgetPolicyBreach:
        breach = await self.session.get(ErrorBudgetPolicyBreach, breach_id)
        if breach is None:
            raise NotFoundException("The breach was not found.")
        return breach

    async def _breach_dtos(self, current_user: CurrentUser, breaches: list[ErrorBudgetPolicyBreach]) -> list[ErrorBudgetBreachDto]:
        applications = {row.application_id: row for row in (await self.session.scalars(select(Application).where(Application.application_id.in_({breach.application_id for breach in breaches})))).all()} if breaches else {}
        dtos: list[ErrorBudgetBreachDto] = []
        for breach in breaches:
            can_edit = await self.authorization.can_edit_application(current_user, breach.application_id)
            is_open = breach.requirement_status == ErrorBudgetRequirementStatus.OPEN
            guidance = (await effective_policy(self.session, breach.application_id)).exhausted_budget_guidance_text if breach.breach_kind == ErrorBudgetBreachKind.BUDGET_EXHAUSTED else None
            dtos.append(ErrorBudgetBreachDto(
                breach_id=breach.error_budget_policy_breach_id, application_id=breach.application_id, application_name=applications[breach.application_id].application_name, breach_kind=breach.breach_kind,
                incident_id=breach.incident_id, incident_reference=breach.incident_reference_text, slo_id=breach.slo_id, sli_name=breach.sli_name_text, recurrence_category=breach.recurrence_category,
                recurrence_service_name=breach.recurrence_service_name_text, measured_share_percent=breach.measured_share_percent, threshold_percent=breach.threshold_percent, window_days=breach.window_days,
                detected_at=breach.detected_at, requirement_status=breach.requirement_status, is_provisional=breach.is_provisional, qualifying_action_item_id=breach.qualifying_action_item_id,
                waived_by=breach.waived_by_user_principal_name, waiver_reason_text=breach.waiver_reason_text, guidance_text=guidance,
                can_waive=can_edit and is_open and breach.breach_kind != ErrorBudgetBreachKind.BUDGET_EXHAUSTED,
                can_add_action_item=can_edit and is_open and breach.breach_kind == ErrorBudgetBreachKind.OUTAGE_CLASS,
            ))
        return dtos

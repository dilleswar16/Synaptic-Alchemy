"""The messages about policy breaches (spec 30, 4.6): members who subscribed to them, plus the people whose team role is in ERROR_BUDGET_POLICY_NOTIFICATION_ROLES, one email each in their language.

The text is built from facts Keigan computed (names, shares, thresholds, dates). For an exhausted budget the email also quotes the team's own agreed response, sanitised.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicyBreach
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ErrorBudgetBreachKind, StakeholderRecipientType
from keigan.services.error_budget_policy_service import effective_policy
from keigan.services.notification_service import NotificationService
from keigan.utils.string_table import translate

NOTIFICATION_TYPE = "error_budget_policy"
_KIND_KEYS = {
    ErrorBudgetBreachKind.SINGLE_INCIDENT: "error_budget_policy_single",
    ErrorBudgetBreachKind.OUTAGE_CLASS: "error_budget_policy_class",
    ErrorBudgetBreachKind.BUDGET_EXHAUSTED: "error_budget_policy_exhausted",
}


class ErrorBudgetPolicyNotifier:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.notifications = NotificationService(session)

    async def recipients(self, application_id: str) -> list[Stakeholder]:
        subscribed = await self.notifications.matching_stakeholders(application_id, NOTIFICATION_TYPE, "email")
        roles = set(self.settings.error_budget_policy_notification_role_list)
        by_address: dict[str, Stakeholder] = {}
        candidates = [*subscribed, *(await self._people_in_roles(application_id, roles))]
        for stakeholder in candidates:
            address = self.notifications.recipient_address_for(stakeholder, "email")
            if address and address.lower() not in by_address:
                by_address[address.lower()] = stakeholder
        return list(by_address.values())

    async def _people_in_roles(self, application_id: str, roles: set[str]) -> list[Stakeholder]:
        from sqlalchemy import select

        people = (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id == application_id, Stakeholder.is_active.is_(True), Stakeholder.recipient_type == StakeholderRecipientType.PERSON))).all()
        return [person for person in people if person.stakeholder_role in roles]

    async def notify(self, breach: ErrorBudgetPolicyBreach, application: Application) -> int:
        """Queues one email per recipient. Returns how many were queued."""
        key = _KIND_KEYS[ErrorBudgetBreachKind(breach.breach_kind)]
        guidance = (await effective_policy(self.session, application.application_id)).exhausted_budget_guidance_text if breach.breach_kind == ErrorBudgetBreachKind.BUDGET_EXHAUSTED else None
        action_path = {ErrorBudgetBreachKind.SINGLE_INCIDENT: f"/incidents/{breach.incident_id}" if breach.incident_id else "/incidents", ErrorBudgetBreachKind.OUTAGE_CLASS: "/action-items", ErrorBudgetBreachKind.BUDGET_EXHAUSTED: "/slo"}[ErrorBudgetBreachKind(breach.breach_kind)]
        queued = 0
        for recipient in await self.recipients(application.application_id):
            language = recipient.preferred_language_code
            address = self.notifications.recipient_address_for(recipient, "email")
            assert address is not None
            share = f"{breach.measured_share_percent:g} %" if breach.measured_share_percent is not None else ""
            facts = [
                (translate(language, "labels.application"), application.application_name), (translate(language, "labels.slo"), breach.sli_name_text or ""),
                (translate(language, "labels.budget_share"), share), (translate(language, "labels.threshold"), f"{breach.threshold_percent:g} %" if breach.threshold_percent is not None else ""),
                (translate(language, "labels.window"), f"{breach.window_days}"), (translate(language, "labels.incident"), breach.incident_reference_text or ""),
            ]
            rendered = self.notifications.renderer.render_email(
                key, language, application.application_name, breach.sli_name_text or application.application_name, facts=facts, body_markdown=guidance, action_path=action_path,
                severity=breach.recurrence_category or "",
            )
            if await self.notifications.queue_email(application.application_id, NOTIFICATION_TYPE, address, rendered, incident_id=None):
                queued += 1
        if breach.breach_kind == ErrorBudgetBreachKind.SINGLE_INCIDENT and breach.incident_id:
            share_text = f"{breach.measured_share_percent:g} %" if breach.measured_share_percent is not None else ""
            await self.notifications.post_to_incident_chat(
                breach.incident_id, translate("en", "types.error_budget_policy_single.chat", share=share_text, slo=breach.sli_name_text or "", threshold=f"{breach.threshold_percent:g}" if breach.threshold_percent is not None else ""),
            )
        return queued

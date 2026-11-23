"""Action items tracked as tasks in ServiceNow (spec 29, 4.7; roadmap D1).

An application admin sends a tracked item to ServiceNow, which creates a task for it. From then on ServiceNow owns the item's status: a sync, on the ServiceNow poll schedule, reads each linked
task and moves the item to match (finished, not done, or reopened), and Keigan stops its own reminders for the item. Keigan never closes or changes a ServiceNow task after creating it.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import Settings, get_settings
from keigan.dtos.action_item_dtos import ActionItemDto
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.status_values import ActionItemStatus, ExternalSyncStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, IntegrationException, NotFoundException
from keigan.integrations.action_item_tracker import ActionItemSnapshot, ExternalTaskTracker
from keigan.integrations.servicenow_client import ServiceNowClient
from keigan.integrations.servicenow_task_tracker import ServiceNowTaskTracker
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_external_rules import ExternalTaskOutcome, status_after_sync
from keigan.services.action_item_rules import CLOSED_STATUSES, TRACKED_STATUSES
from keigan.services.action_item_service import ActionItemService
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.error_budget_policy_service import on_action_items_changed
from keigan.utils.time_utils import utc_now
from keigan.config import application_context

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = "servicenow"  # who a status change that came from the task is attributed to
NOT_FOUND_TEXT = "Not found in ServiceNow"
CLOSED_WITHOUT_BEING_DONE_REASON = "The task was closed in ServiceNow without being completed."
MAXIMUM_ITEMS_PER_SYNC = 200  # one run reads at most this many tasks; the rest wait for the next run


class ActionItemTrackingService:
    def __init__(self, session: AsyncSession, tracker: ExternalTaskTracker | None = None):
        self.session = session
        self.settings: Settings = get_settings()
        self.authorization = AuthorizationService(session)
        self.tracker: ExternalTaskTracker = tracker or ServiceNowTaskTracker(self.settings, ServiceNowClient(self.settings, application_context.secret_store()))

    # ── Sending ────────────────────────────────────────────────────────────────
    async def send(self, current_user: CurrentUser, action_item_id: str) -> ActionItemDto:
        """Creates the task for a tracked item. A failure is recorded on the item (and can be tried again) instead of being raised: the person sees "could not be sent"."""
        if not self.settings.action_items_external_tracking_enabled:
            raise BusinessValidationException("Sending action items to ServiceNow is switched off.")
        item = await self.session.get(ActionItem, action_item_id)
        if item is None:
            raise NotFoundException("The action item was not found.")
        await self.authorization.ensure_application_admin(current_user, item.application_id)
        if item.item_status not in TRACKED_STATUSES:
            raise BusinessValidationException("Only a tracked action item (open, in progress or blocked) can be sent to ServiceNow.")
        if item.external_sync_status == ExternalSyncStatus.LINKED:
            raise BusinessValidationException("This action item is already tracked in ServiceNow.")
        incident_reference = item.incident_reference_text
        snapshot = ActionItemSnapshot(
            title=item.item_title, details=item.item_details_markdown, action_type=item.action_type, priority=item.action_priority, due_on=item.due_on, incident_reference=incident_reference,
        )
        try:
            reference = await self.tracker.create_task(snapshot)
        except IntegrationException:
            logger.warning("ServiceNow did not accept the task for action item %s", item.action_item_id, exc_info=True)
            item.external_system, item.external_sync_status, item.external_synced_at = self.tracker.system_name, ExternalSyncStatus.FAILED, utc_now()
            await self.session.flush()
            await self._audit(current_user.user_principal_name, "action_item.external_send_failed", item, {})
        else:
            item.external_system, item.external_sync_status = self.tracker.system_name, ExternalSyncStatus.LINKED
            item.external_record_identifier, item.external_reference_text = reference.record_identifier, reference.number
            item.external_status_text, item.external_synced_at = "Open", utc_now()
            item.updated_by_user_principal_name = current_user.user_principal_name
            await self.session.flush()
            await self._audit(current_user.user_principal_name, "action_item.external_send", item, {"number": reference.number})
        return (await ActionItemService(self.session).dtos_for(current_user, [item]))[0]

    # ── Reading back (job: sync_action_item_tasks) ─────────────────────────────
    async def sync_application(self, application_id: str) -> dict[str, int]:
        items = list((await self.session.scalars(select(ActionItem).where(
            ActionItem.application_id == application_id, ActionItem.external_sync_status == ExternalSyncStatus.LINKED, ActionItem.external_record_identifier.is_not(None),
        ).order_by(ActionItem.external_synced_at).limit(MAXIMUM_ITEMS_PER_SYNC))).all())
        if not items:
            return {"checked": 0, "changed": 0, "missing": 0}
        states = await self.tracker.read_task_states([item.external_record_identifier for item in items if item.external_record_identifier])
        now = utc_now()
        changed = missing = 0
        for item in items:
            state = states.get(item.external_record_identifier or "")
            item.external_synced_at = now
            if state is None:
                item.external_status_text = NOT_FOUND_TEXT
                missing += 1
                continue
            item.external_status_text = state.status_text[:100]
            if await self._apply_outcome(item, state.outcome):
                changed += 1
        await self.session.flush()
        return {"checked": len(items), "changed": changed, "missing": missing}

    async def _apply_outcome(self, item: ActionItem, outcome: ExternalTaskOutcome) -> bool:
        new_status = status_after_sync(item.item_status, outcome)
        if new_status is None:
            return False
        previous = item.item_status
        item.item_status = new_status
        if new_status in CLOSED_STATUSES:
            item.completed_at, item.completed_by_user_principal_name = utc_now(), SYSTEM_ACTOR
            item.status_reason_text = CLOSED_WITHOUT_BEING_DONE_REASON if new_status == ActionItemStatus.WONT_DO else None
            item.completion_note_text = None
        else:
            item.completed_at = item.completed_by_user_principal_name = item.completion_note_text = item.status_reason_text = None
        item.updated_by_user_principal_name = SYSTEM_ACTOR
        await self._audit(SYSTEM_ACTOR, "action_item.external_sync", item, {"from": previous, "to": new_status.value})
        await on_action_items_changed(self.session, item.incident_id)
        return True

    async def _audit(self, actor: str, action_name: str, item: ActionItem, details: dict[str, Any]) -> None:
        await AuditService(self.session).record(
            actor, action_name, target_entity_type="action_item", target_entity_id=item.action_item_id, application_id=item.application_id, action_details=details or None,
        )

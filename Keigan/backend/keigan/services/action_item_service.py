"""Action items: create, read, change and close them, with the access rules of spec 29 (6.1).

Anyone who can read the application reads its items. Application admins change them. The owner (a team member the item is assigned to) may also move it between open, in progress,
blocked and done, and edit its details, with read access only: whoever does the work closes it, but dropping or moving work is a team decision. Every change is audited. Tracked
items are never deleted: they close as done or won't do. Only a suggestion nobody accepted can be discarded.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.config.settings import Settings, get_settings
from keigan.dtos.action_item_dtos import ActionItemCreateRequest, ActionItemDto, ActionItemOwnerDto, ActionItemStatusRequest, ActionItemUpdateRequest
from keigan.dtos.common_dtos import PagedResult
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ActionItemPriority, ActionItemSource, ActionItemStatus, StakeholderRecipientType
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_rules import (
    CLOSED_STATUSES, ActionItemRuleError, Actor, can_transition, days_overdue, is_overdue, local_today, validate_due_date, validate_reason,
)
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.error_budget_policy_service import on_action_items_changed
from keigan.services.postmortem_action_items import incident_reference_of
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now

TRACKED_BY_DEFAULT = (ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS, ActionItemStatus.BLOCKED)
_OWNER_MAY_EDIT_ONLY = {"item_details_markdown"}


def _rule_error_as_validation(error: ActionItemRuleError) -> BusinessValidationException:
    return BusinessValidationException(str(error))


class ActionItemService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings: Settings = get_settings()
        self.authorization = AuthorizationService(session)

    # ── Reading ────────────────────────────────────────────────────────────────
    async def get(self, current_user: CurrentUser, action_item_id: str) -> ActionItemDto:
        item = await self._load(action_item_id)
        await self.authorization.ensure_application_reader(current_user, item.application_id)
        return (await self._dtos(current_user, [item]))[0]

    async def list_for_postmortem(self, current_user: CurrentUser, postmortem_id: str) -> list[ActionItemDto]:
        postmortem = await self.session.get(PostmortemReport, postmortem_id)
        incident = await self.session.get(Incident, postmortem.incident_id) if postmortem else None
        if postmortem is None or incident is None:
            raise NotFoundException("The postmortem was not found.")
        await self.authorization.ensure_application_reader(current_user, incident.application_id)
        items = list((await self.session.scalars(select(ActionItem).where(ActionItem.postmortem_id == postmortem_id).order_by(ActionItem.display_order, ActionItem.created_at))).all())
        return await self._dtos(current_user, items)

    async def list_items(
        self, current_user: CurrentUser, *, application_ids: list[str] | None, statuses: list[str] | None, priorities: list[str] | None, source_kinds: list[str] | None,
        owner: str | None, overdue_only: bool, incident_id: str | None, page: int, page_size: int,
    ) -> PagedResult[ActionItemDto]:
        scope = await self.authorization.scoped_application_ids(current_user, application_ids)
        if not scope:
            return PagedResult[ActionItemDto](items=[], total_count=0, page=page, page_size=page_size)
        conditions = [ActionItem.application_id.in_(scope), ActionItem.item_status.in_(statuses or [status.value for status in TRACKED_BY_DEFAULT])]
        if priorities:
            conditions.append(ActionItem.action_priority.in_(priorities))
        if source_kinds:
            conditions.append(ActionItem.item_source_kind.in_(source_kinds))
        if incident_id:
            conditions.append(ActionItem.incident_id == incident_id)
        if owner == "unassigned":
            conditions.append(ActionItem.owner_stakeholder_id.is_(None))
        elif owner == "me":
            conditions.append(ActionItem.owner_stakeholder_id.in_(await self._stakeholder_ids_of(current_user, scope)))
        elif owner:
            conditions.append(ActionItem.owner_stakeholder_id == owner)
        items = list((await self.session.scalars(select(ActionItem).where(*conditions).order_by(ActionItem.due_on.is_(None), ActionItem.due_on, ActionItem.created_at))).all())
        dtos = await self._dtos(current_user, items)
        if overdue_only:
            dtos = [dto for dto in dtos if dto.is_overdue]
        start = (page - 1) * page_size
        return PagedResult[ActionItemDto](items=dtos[start:start + page_size], total_count=len(dtos), page=page, page_size=page_size)

    # ── Changing ───────────────────────────────────────────────────────────────
    async def create(
        self, current_user: CurrentUser, application_id: str, request: ActionItemCreateRequest, *, source_kind: ActionItemSource = ActionItemSource.MANUAL, source_record_id: str | None = None,
    ) -> ActionItemDto:
        await self.authorization.ensure_application_admin(current_user, application_id)
        application = await self._application(application_id)
        incident, postmortem = await self._linked_records(application_id, request.incident_id, request.postmortem_id)
        today = local_today(application.time_zone_name, utc_now())
        due_on = self._valid_due_date(request.due_on, today)
        item = ActionItem(
            application_id=application_id, incident_id=incident.incident_id if incident else None, postmortem_id=postmortem.postmortem_id if postmortem else None,
            incident_reference_text=incident_reference_of(incident) if incident else None, item_source_kind=source_kind, source_record_id=source_record_id, item_title=self._clean_line(request.item_title, 300),
            item_details_markdown=self._clean_markdown(request.item_details_markdown), action_type=request.action_type, action_priority=request.action_priority, item_status=ActionItemStatus.OPEN,
            owner_stakeholder_id=await self._validated_owner(application_id, request.owner_stakeholder_id), due_on=due_on, original_due_on=due_on,
            external_reference_text=self._valid_external_reference(request.external_reference_text), accepted_at=utc_now(), accepted_by_user_principal_name=current_user.user_principal_name,
            created_by_user_principal_name=current_user.user_principal_name,
        )
        self.session.add(item)
        await self.session.flush()
        await self._audit(current_user, "action_item.create", item, {"status": item.item_status})
        await on_action_items_changed(self.session, item.incident_id)
        return (await self._dtos(current_user, [item]))[0]

    async def update(self, current_user: CurrentUser, action_item_id: str, request: ActionItemUpdateRequest) -> ActionItemDto:
        item = await self._load(action_item_id)
        actor = await self._actor(current_user, item)
        sent = request.model_fields_set
        if actor == Actor.READER or (actor == Actor.OWNER and not sent <= _OWNER_MAY_EDIT_ONLY):
            raise ForbiddenException("Only this application's admins can change that. The owner may edit the details.")
        changed = await self._apply_changes(item, request, sent, current_user)
        await self.session.flush()
        await self._audit(current_user, "action_item.update", item, changed)
        await on_action_items_changed(self.session, item.incident_id)
        return (await self._dtos(current_user, [item]))[0]

    async def accept(self, current_user: CurrentUser, action_item_id: str, request: ActionItemUpdateRequest | None = None) -> ActionItemDto:
        item = await self._load(action_item_id)
        await self.authorization.ensure_application_admin(current_user, item.application_id)
        if item.item_status != ActionItemStatus.PROPOSED:
            raise BusinessValidationException("Only a suggested action item can be accepted.")
        if request is not None:
            await self._apply_changes(item, request, request.model_fields_set, current_user)
        application = await self._application(item.application_id)
        if item.due_on is None:
            raise BusinessValidationException("Choose a due date before accepting this action item.")
        item.due_on = self._valid_due_date(item.due_on, local_today(application.time_zone_name, utc_now()))
        item.original_due_on, item.item_status = item.due_on, ActionItemStatus.OPEN
        item.accepted_at, item.accepted_by_user_principal_name = utc_now(), current_user.user_principal_name
        await self.session.flush()
        await self._audit(current_user, "action_item.accept", item, {"dueOn": item.due_on.isoformat()})
        await on_action_items_changed(self.session, item.incident_id)
        return (await self._dtos(current_user, [item]))[0]

    async def change_status(self, current_user: CurrentUser, action_item_id: str, request: ActionItemStatusRequest) -> ActionItemDto:
        item = await self._load(action_item_id)
        actor = await self._actor(current_user, item)
        previous = ActionItemStatus(item.item_status)
        if not can_transition(actor, previous, request.status):
            raise BusinessValidationException(f"You cannot move this item from {previous.value} to {request.status.value}." if actor != Actor.READER else "Only the owner or an application admin can change this item.")
        try:
            reason = validate_reason(request.status, request.reason_text, minimum_characters=self.settings.action_items_reason_minimum_characters)
        except ActionItemRuleError as error:
            raise _rule_error_as_validation(error) from error
        now = utc_now()
        item.item_status = request.status
        item.status_reason_text = self._clean_line(reason, 1000) if reason else None
        if request.status in CLOSED_STATUSES:
            item.completed_at, item.completed_by_user_principal_name = now, current_user.user_principal_name
            item.completion_note_text = self._clean_line(request.completion_note_text, 2000) if request.status == ActionItemStatus.DONE and request.completion_note_text else None
        else:
            item.completed_at = item.completed_by_user_principal_name = item.completion_note_text = None
        item.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self._audit(current_user, "action_item.status", item, {"from": previous.value, "to": request.status.value})
        await on_action_items_changed(self.session, item.incident_id)  # turning the qualifying item to won't do reopens the policy requirement at once
        return (await self._dtos(current_user, [item]))[0]

    async def discard(self, current_user: CurrentUser, action_item_id: str) -> None:
        item = await self._load(action_item_id)
        await self.authorization.ensure_application_admin(current_user, item.application_id)
        if item.item_status != ActionItemStatus.PROPOSED:
            raise BusinessValidationException("A tracked action item is not deleted: close it as won't do, with a reason.")
        await self._audit(current_user, "action_item.discard", item, {})
        await self.session.delete(item)

    # ── Internals ──────────────────────────────────────────────────────────────
    async def _load(self, action_item_id: str) -> ActionItem:
        item = await self.session.get(ActionItem, action_item_id)
        if item is None:
            raise NotFoundException("The action item was not found.")
        return item

    async def _application(self, application_id: str) -> Application:
        application = await self.session.get(Application, application_id)
        if application is None:
            raise NotFoundException("The application was not found.")
        return application

    async def _actor(self, current_user: CurrentUser, item: ActionItem) -> Actor:
        await self.authorization.ensure_application_reader(current_user, item.application_id)
        if await self.authorization.can_edit_application(current_user, item.application_id):
            return Actor.ADMIN
        return Actor.OWNER if await self._is_owner(current_user, item) else Actor.READER

    async def _is_owner(self, current_user: CurrentUser, item: ActionItem) -> bool:
        """The owner is an active team member whose user principal name or email address is the caller's (a member added before invitations may have an email only)."""
        if not item.owner_stakeholder_id:
            return False
        owner = await self.session.get(Stakeholder, item.owner_stakeholder_id)
        return owner is not None and owner.is_active and self._matches(owner, current_user)

    @staticmethod
    def _matches(stakeholder: Stakeholder, current_user: CurrentUser) -> bool:
        identities = {value.lower() for value in (current_user.user_principal_name, current_user.email_address) if value}
        return any(value and value.lower() in identities for value in (stakeholder.user_principal_name, stakeholder.email_address))

    async def _stakeholder_ids_of(self, current_user: CurrentUser, application_ids: list[str]) -> list[str]:
        rows = (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id.in_(application_ids), Stakeholder.is_active.is_(True)))).all()
        return [stakeholder.stakeholder_id for stakeholder in rows if self._matches(stakeholder, current_user)] or [""]

    async def _validated_owner(self, application_id: str, owner_stakeholder_id: str | None) -> str | None:
        if owner_stakeholder_id is None:
            return None
        owner = await self.session.get(Stakeholder, owner_stakeholder_id)
        if owner is None or owner.application_id != application_id or owner.recipient_type != StakeholderRecipientType.PERSON or not owner.is_active:
            raise BusinessValidationException("The owner must be an active team member of this application (a person, not a channel or a list).")
        return owner.stakeholder_id

    async def _linked_records(self, application_id: str, incident_id: str | None, postmortem_id: str | None) -> tuple[Incident | None, PostmortemReport | None]:
        incident = await self.session.get(Incident, incident_id) if incident_id else None
        if incident_id and (incident is None or incident.application_id != application_id):
            raise NotFoundException("That incident does not belong to this application.")
        postmortem = await self.session.get(PostmortemReport, postmortem_id) if postmortem_id else None
        if postmortem_id and (postmortem is None or incident is None or postmortem.incident_id != incident.incident_id):
            raise NotFoundException("That postmortem does not belong to that incident.")
        return incident, postmortem

    def _valid_due_date(self, due_on: date, today: date) -> date:
        try:
            return validate_due_date(due_on, today, maximum_days=self.settings.action_items_maximum_due_days)
        except ActionItemRuleError as error:
            raise _rule_error_as_validation(error) from error

    def _valid_external_reference(self, reference: str | None) -> str | None:
        cleaned = (reference or "").strip().upper() or None
        if cleaned and not re.fullmatch(self.settings.action_items_external_reference_pattern, cleaned):
            raise BusinessValidationException("That is not a valid task number.")
        return cleaned

    @staticmethod
    def _clean_line(text: str | None, maximum_characters: int) -> str:
        return sanitize_ai_line(PiiMasker().mask_text(text or ""), maximum_characters=maximum_characters)

    def _clean_markdown(self, text: str | None) -> str | None:
        if not text or not text.strip():
            return None
        cleaned = sanitize_ai_markdown(PiiMasker().mask_text(text.strip()))
        if len(cleaned) > self.settings.action_items_details_maximum_characters:
            raise BusinessValidationException(f"The details can be at most {self.settings.action_items_details_maximum_characters} characters.")
        return cleaned

    async def _apply_changes(self, item: ActionItem, request: ActionItemUpdateRequest, sent: set[str], current_user: CurrentUser) -> dict[str, Any]:
        changed: dict[str, Any] = {}
        if "item_title" in sent and request.item_title is not None:
            item.item_title = self._clean_line(request.item_title, 300)
            changed["title"] = True
        if "item_details_markdown" in sent:
            item.item_details_markdown = self._clean_markdown(request.item_details_markdown)
            changed["details"] = True
        if "action_type" in sent and request.action_type is not None:
            item.action_type = request.action_type
            changed["type"] = True
        if "action_priority" in sent and request.action_priority is not None:
            item.action_priority = request.action_priority
            changed["priority"] = True
        if "owner_stakeholder_id" in sent:
            item.owner_stakeholder_id = await self._validated_owner(item.application_id, request.owner_stakeholder_id)
            changed["owner"] = True
        if "external_reference_text" in sent:
            item.external_reference_text = self._valid_external_reference(request.external_reference_text)
            changed["externalReference"] = True
        if "due_on" in sent and request.due_on is not None and request.due_on != item.due_on:
            application = await self._application(item.application_id)
            new_due_on = self._valid_due_date(request.due_on, local_today(application.time_zone_name, utc_now()))
            changed["dueOn"] = {"from": item.due_on.isoformat() if item.due_on else None, "to": new_due_on.isoformat()}
            if item.item_status != ActionItemStatus.PROPOSED:  # moving a suggestion's date is part of accepting it; moving a tracked item's date is counted and shown
                item.due_on_change_count += 1
            item.due_on = new_due_on
        item.updated_by_user_principal_name = current_user.user_principal_name
        return changed

    async def _audit(self, current_user: CurrentUser, action_name: str, item: ActionItem, details: dict[str, Any]) -> None:
        await AuditService(self.session).record(
            current_user, action_name, target_entity_type="action_item", target_entity_id=item.action_item_id, application_id=item.application_id, action_details=details or None,
        )

    async def _dtos(self, current_user: CurrentUser, items: list[ActionItem]) -> list[ActionItemDto]:
        if not items:
            return []
        applications = {row.application_id: row for row in (await self.session.scalars(select(Application).where(Application.application_id.in_({item.application_id for item in items})))).all()}
        owner_ids = {item.owner_stakeholder_id for item in items if item.owner_stakeholder_id}
        owners = {row.stakeholder_id: row for row in (await self.session.scalars(select(Stakeholder).where(Stakeholder.stakeholder_id.in_(owner_ids)))).all()} if owner_ids else {}
        admin_application_ids = {application_id for application_id in applications if await self.authorization.can_edit_application(current_user, application_id)}
        now = utc_now()
        dtos: list[ActionItemDto] = []
        for item in items:
            application, owner = applications[item.application_id], owners.get(item.owner_stakeholder_id or "")
            actor = Actor.ADMIN if item.application_id in admin_application_ids else Actor.OWNER if owner is not None and owner.is_active and self._matches(owner, current_user) else Actor.READER
            today = local_today(application.time_zone_name, now)
            current = ActionItemStatus(item.item_status)
            allowed = [status.value for status in ActionItemStatus if can_transition(actor, current, status)]
            dtos.append(ActionItemDto(
                action_item_id=item.action_item_id, application_id=item.application_id, application_name=application.application_name, incident_id=item.incident_id,
                incident_reference=item.incident_reference_text, postmortem_id=item.postmortem_id, source_kind=item.item_source_kind, item_title=item.item_title,
                item_details_markdown=item.item_details_markdown, action_type=item.action_type, action_priority=item.action_priority, item_status=item.item_status,
                suggested_owner_role_text=item.suggested_owner_role_text,
                owner=ActionItemOwnerDto(stakeholder_id=owner.stakeholder_id, display_name=owner.display_name, stakeholder_role=owner.stakeholder_role) if owner else None,
                due_on=item.due_on, original_due_on=item.original_due_on, due_on_change_count=item.due_on_change_count, is_overdue=is_overdue(item.item_status, item.due_on, today),
                days_overdue=days_overdue(item.item_status, item.due_on, today), status_reason_text=item.status_reason_text, completion_note_text=item.completion_note_text,
                completed_at=item.completed_at, completed_by=item.completed_by_user_principal_name, accepted_at=item.accepted_at, external_reference_text=item.external_reference_text,
                can_edit=actor == Actor.ADMIN, can_change_status=bool(allowed), allowed_statuses=allowed, created_at=item.created_at, updated_at=item.updated_at,
            ))
        return dtos

"""The team and recipients of an application: who is told what, when and where, who was invited, test sends and the people directory search."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import AuthenticationMode, get_settings
from keigan.dtos.notification_dtos import (
    NOTIFICATION_CHANNEL_VALUES, NOTIFICATION_TYPE_VALUES, DirectoryUserResponse, StakeholderCreateRequest, StakeholderInvitationResponse, StakeholderResponse, StakeholderTestResponse,
    StakeholderUpdateRequest, TeamMemberRequest,
)
from keigan.entities.application_entities import Application
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import StakeholderRecipientType, StakeholderRole
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.notification_renderer import translate
from keigan.services.notification_service import NotificationService
from keigan.services.reference_release import release_references
from keigan.services.service_scope import unknown_service_ids
from keigan.services.team_invitation_service import TeamInvitationService, describe_invitation
from keigan.utils.time_utils import utc_now

FIELD_NAMES_WITH_JSON_LISTS = {"notification_channels": "notification_channels_json", "subscribed_notification_types": "subscribed_notification_types_json"}


class StakeholderService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── CRUD ───────────────────────────────────────────────────────────────────
    async def list_stakeholders(self, application_id: str) -> list[StakeholderResponse]:
        rows = (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id == application_id).order_by(Stakeholder.display_name))).all()
        return [self._to_response(row) for row in rows]

    async def create_stakeholder(self, current_user: CurrentUser, application_id: str, request: StakeholderCreateRequest) -> StakeholderResponse:
        application = await self._ensure_application(application_id)
        values = request.model_dump(exclude={"send_invitation"})
        await self._validate(application_id, values)
        stakeholder = Stakeholder(application_id=application_id, created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name)
        self._apply(stakeholder, values)
        invitation_service = TeamInvitationService(self.session)
        if request.send_invitation:
            invitation_service.ensure_can_invite(stakeholder, utc_now())  # before anything is saved: a refused invitation must not leave the member half added
        await self._add_or_report_duplicate(stakeholder)
        if request.send_invitation:
            await invitation_service.queue_invitation(current_user, stakeholder, application)
        await AuditService(self.session).record(current_user, "stakeholder.create", target_entity_type="stakeholder", target_entity_id=stakeholder.stakeholder_id, application_id=application_id, action_details={"displayName": stakeholder.display_name, "invited": request.send_invitation})
        return self._to_response(stakeholder)

    async def add_team_members(self, current_user: CurrentUser, application_id: str, team_members: list[TeamMemberRequest], *, send_invitations: bool) -> None:
        """The people entered while an application is created. All or nothing: one refused person fails the whole request, so no half-built team is saved."""
        for team_member in team_members:
            await self.create_stakeholder(
                current_user, application_id,
                StakeholderCreateRequest(display_name=team_member.display_name, email_address=team_member.email_address, stakeholder_role=team_member.stakeholder_role, send_invitation=send_invitations),
            )

    async def send_invitation(self, current_user: CurrentUser, application_id: str, stakeholder_id: str) -> StakeholderInvitationResponse:
        stakeholder = await self._load(application_id, stakeholder_id)
        application = await self._ensure_application(application_id)
        delivery_id, message = await TeamInvitationService(self.session).queue_invitation(current_user, stakeholder, application)
        return StakeholderInvitationResponse(team_member=self._to_response(stakeholder), delivery_id=delivery_id, message=message)

    async def update_stakeholder(self, current_user: CurrentUser, application_id: str, stakeholder_id: str, request: StakeholderUpdateRequest) -> StakeholderResponse:
        stakeholder = await self._load(application_id, stakeholder_id)
        values = request.model_dump(exclude_unset=True)
        await self._validate(application_id, values, partial=True, existing=stakeholder)
        if (
            values.get("stakeholder_role", stakeholder.stakeholder_role) != StakeholderRole.LEAD or values.get("is_active") is False
            or values.get("recipient_type", stakeholder.recipient_type) != StakeholderRecipientType.PERSON
        ):
            await self._ensure_not_the_only_lead(stakeholder)
        if values.get("email_address") and values["email_address"] != stakeholder.email_address:
            self._start_new_history_for_another_address(stakeholder, values["email_address"])
        self._apply(stakeholder, values)
        stakeholder.updated_by_user_principal_name = current_user.user_principal_name
        await self._add_or_report_duplicate(None)
        await AuditService(self.session).record(current_user, "stakeholder.update", target_entity_type="stakeholder", target_entity_id=stakeholder_id, application_id=application_id, action_details={"fields": sorted(values)})
        return self._to_response(stakeholder)

    async def delete_stakeholder(self, current_user: CurrentUser, application_id: str, stakeholder_id: str) -> None:
        stakeholder = await self._load(application_id, stakeholder_id)
        await self._ensure_not_the_only_lead(stakeholder)
        await release_references(self.session, Stakeholder.stakeholder_id, [stakeholder_id])  # their action items stay, unassigned
        await self.session.delete(stakeholder)
        await AuditService(self.session).record(current_user, "stakeholder.delete", target_entity_type="stakeholder", target_entity_id=stakeholder_id, application_id=application_id, action_details={"displayName": stakeholder.display_name})

    async def send_test(self, current_user: CurrentUser, application_id: str, stakeholder_id: str) -> StakeholderTestResponse:
        stakeholder = await self._load(application_id, stakeholder_id)
        application = await self._ensure_application(application_id)
        notification_service = NotificationService(self.session)
        recipient_address = notification_service.recipient_address_for(stakeholder, "email")
        delivery_ids: list[str] = []
        if recipient_address and "email" in (stakeholder.notification_channels_json or []):
            language = stakeholder.preferred_language_code
            rendered = notification_service.renderer.render_email(
                "test", language, application.application_name, application.application_name,
                facts=[(translate(language, "labels.application"), application.application_name), (translate(language, "labels.priority"), stakeholder.minimum_priority)], action_path=f"/applications/{application_id}",
            )
            delivery_id = await notification_service.queue_email(application_id, "test", recipient_address, rendered)
            if delivery_id:
                delivery_ids.append(delivery_id)
        await AuditService(self.session).record(current_user, "stakeholder.test", target_entity_type="stakeholder", target_entity_id=stakeholder_id, application_id=application_id, action_details={"queued": len(delivery_ids)})
        message = "A test email was queued." if delivery_ids else "No test could be sent: the stakeholder needs an email address and the email channel."
        return StakeholderTestResponse(deliveries_queued=len(delivery_ids), delivery_ids=delivery_ids, message=message)

    # ── Directory ──────────────────────────────────────────────────────────────
    async def search_directory(self, query_text: str) -> list[DirectoryUserResponse]:
        query_text = query_text.strip()
        if len(query_text) < 2:
            return []
        settings = get_settings()
        if settings.auth_mode == AuthenticationMode.ENTRA and application_context.azure_credential_provider().is_configured:
            people = await MicrosoftGraphClient(application_context.azure_credential_provider()).search_people(query_text)
            return [
                DirectoryUserResponse(display_name=person.get("displayName") or "", email_address=person.get("mail"), user_principal_name=person.get("userPrincipalName"), entra_object_id=person.get("id"), job_title=person.get("jobTitle"), source="entra")
                for person in people
            ]
        from keigan.services.authentication_service import load_local_users

        lowered_query = query_text.lower()
        results: dict[str, DirectoryUserResponse] = {}
        for user in load_local_users():
            if lowered_query in user.display_name.lower() or lowered_query in user.email_address.lower():
                results[user.email_address.lower()] = DirectoryUserResponse(display_name=user.display_name, email_address=user.email_address, user_principal_name=user.user_principal_name, job_title=user.role_description or None, source="local")
        for stakeholder in (await self.session.scalars(select(Stakeholder).where(Stakeholder.recipient_type == StakeholderRecipientType.PERSON))).all():
            address = (stakeholder.email_address or "").lower()
            if address and address not in results and (lowered_query in stakeholder.display_name.lower() or lowered_query in address):
                results[address] = DirectoryUserResponse(display_name=stakeholder.display_name, email_address=stakeholder.email_address, user_principal_name=stakeholder.user_principal_name, entra_object_id=stakeholder.entra_object_id, source="stakeholder")
        return sorted(results.values(), key=lambda user: user.display_name)[:15]

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _ensure_application(self, application_id: str) -> Application:
        application = await self.session.get(Application, application_id)
        if application is None:
            raise NotFoundException("Application not found.")
        return application

    async def _load(self, application_id: str, stakeholder_id: str) -> Stakeholder:
        stakeholder = await self.session.get(Stakeholder, stakeholder_id)
        if stakeholder is None or stakeholder.application_id != application_id:
            raise NotFoundException("Stakeholder not found.")
        return stakeholder

    async def _add_or_report_duplicate(self, new_stakeholder: Stakeholder | None) -> None:
        """Save the change. Two requests can both pass the duplicate check; the unique index then rejects the second, which must read as the same
        message the check gives, not as a server error. A savepoint keeps the rest of the request's work."""
        try:
            async with self.session.begin_nested():
                if new_stakeholder is not None:
                    self.session.add(new_stakeholder)
                await self.session.flush()
        except IntegrityError as conflict:
            address = new_stakeholder.email_address if new_stakeholder is not None else None
            raise BusinessValidationException(
                "The team member is not valid.", field_errors=[{"field": "emailAddress", "message": f"{address or 'This address'} is already on this team."}]
            ) from conflict

    @staticmethod
    def _start_new_history_for_another_address(stakeholder: Stakeholder, new_address: str) -> None:
        """The new address belongs to someone else: they have not been invited and have not signed in, and the old sign-in name must stop claiming this member."""
        if not stakeholder.user_principal_name or stakeholder.user_principal_name.lower() == (stakeholder.email_address or "").lower():
            stakeholder.user_principal_name = new_address
        stakeholder.invited_at = stakeholder.invited_by_user_principal_name = stakeholder.last_invitation_sent_at = stakeholder.joined_at = None

    async def _ensure_not_the_only_lead(self, stakeholder: Stakeholder) -> None:
        """An application whose team has a lead keeps one: the last active lead cannot be removed, switched off or given another role.
        An application with no lead is not affected, so teams that never named one are not blocked."""
        if stakeholder.stakeholder_role != StakeholderRole.LEAD or not stakeholder.is_active or stakeholder.recipient_type != StakeholderRecipientType.PERSON:
            return
        other_active_leads = await self.session.scalar(
            select(func.count()).select_from(Stakeholder).where(
                Stakeholder.application_id == stakeholder.application_id, Stakeholder.stakeholder_id != stakeholder.stakeholder_id, Stakeholder.stakeholder_role == StakeholderRole.LEAD,
                Stakeholder.recipient_type == StakeholderRecipientType.PERSON, Stakeholder.is_active.is_(True),
            )
        )
        if not other_active_leads:
            raise BusinessValidationException(f"{stakeholder.display_name} is the only team lead. Add another lead before removing or changing them.")

    async def _validate_team_membership(self, application_id: str, values: dict[str, Any], existing: Stakeholder | None, errors: list[dict[str, str]]) -> None:
        """One person per address per application, and a limit on the size of the team."""
        recipient_type = values.get("recipient_type") or (existing.recipient_type if existing else StakeholderRecipientType.PERSON)
        email_address = values.get("email_address") if "email_address" in values else (existing.email_address if existing else None)
        if recipient_type != StakeholderRecipientType.PERSON:
            return
        people = select(func.count()).select_from(Stakeholder).where(Stakeholder.application_id == application_id, Stakeholder.recipient_type == StakeholderRecipientType.PERSON)
        if email_address:
            same_address = people.where(func.lower(Stakeholder.email_address) == email_address.lower())
            if existing is not None:
                same_address = same_address.where(Stakeholder.stakeholder_id != existing.stakeholder_id)
            if await self.session.scalar(same_address):
                errors.append({"field": "emailAddress", "message": f"{email_address} is already on this team."})
        maximum_people = get_settings().team_members_maximum_per_application
        if existing is None and (await self.session.scalar(people) or 0) >= maximum_people:
            errors.append({"field": "emailAddress", "message": f"A team can have at most {maximum_people} people."})

    async def _validate(self, application_id: str, values: dict[str, Any], partial: bool = False, existing: Stakeholder | None = None) -> None:
        errors: list[dict[str, str]] = []
        await self._validate_team_membership(application_id, values, existing, errors)
        for channel in values.get("notification_channels") or []:
            if channel not in NOTIFICATION_CHANNEL_VALUES:
                errors.append({"field": "notificationChannels", "message": f"Unknown channel {channel}."})
        for notification_type in values.get("subscribed_notification_types") or []:
            if notification_type not in NOTIFICATION_TYPE_VALUES:
                errors.append({"field": "subscribedNotificationTypes", "message": f"Unknown notification type {notification_type}."})
        if await unknown_service_ids(self.session, application_id, values.get("subscribed_service_ids")):
            errors.append({"field": "subscribedServiceIds", "message": "A selected service does not belong to this application."})
        recipient_type = values.get("recipient_type")
        if not partial and recipient_type in (None, StakeholderRecipientType.PERSON, StakeholderRecipientType.DISTRIBUTION_LIST) and not (values.get("email_address") or values.get("user_principal_name")):
            errors.append({"field": "emailAddress", "message": "An email address is required for people and distribution lists."})
        if not partial and recipient_type == StakeholderRecipientType.TEAMS_CHANNEL and not (values.get("teams_team_id") and values.get("teams_channel_id")):
            errors.append({"field": "teamsChannelId", "message": "A Teams team id and channel id are required for channel destinations."})
        if errors:
            raise BusinessValidationException("The team member is not valid.", field_errors=errors)

    @staticmethod
    def _apply(stakeholder: Stakeholder, values: dict[str, Any]) -> None:
        for field_name, value in values.items():
            if field_name == "subscribed_service_ids":
                stakeholder.replace_linked_ids("subscribed_service_links", value)
            else:
                setattr(stakeholder, FIELD_NAMES_WITH_JSON_LISTS.get(field_name, field_name), value)
        if "email_address" in values and values["email_address"] and not stakeholder.user_principal_name:
            stakeholder.user_principal_name = values["email_address"]

    @staticmethod
    def _to_response(stakeholder: Stakeholder) -> StakeholderResponse:
        return StakeholderResponse(
            **describe_invitation(stakeholder, utc_now()),
            stakeholder_id=stakeholder.stakeholder_id, application_id=stakeholder.application_id, recipient_type=stakeholder.recipient_type, display_name=stakeholder.display_name,
            email_address=stakeholder.email_address, user_principal_name=stakeholder.user_principal_name, entra_object_id=stakeholder.entra_object_id, teams_team_id=stakeholder.teams_team_id,
            teams_channel_id=stakeholder.teams_channel_id, stakeholder_role=stakeholder.stakeholder_role, subscribed_service_ids=stakeholder.subscribed_service_ids,
            notification_channels=stakeholder.notification_channels_json or [], minimum_priority=stakeholder.minimum_priority, subscribed_notification_types=stakeholder.subscribed_notification_types_json or [],
            preferred_language_code=stakeholder.preferred_language_code, is_active=stakeholder.is_active, updated_at=getattr(stakeholder, "updated_at", None),
        )

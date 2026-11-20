"""Team invitations: who may be invited, the invitation email, and the first sign-in that turns "invited" into "active".

Keigan does not grant access. Access to an application comes from two AD groups that SailPoint fills, so an invitation only tells the
person they were added, which group to request, and where to open the application. See My Plans/20_TEAM_MEMBERS_DESIGN.md.
A member's status is worked out from facts on the stakeholder row, never stored, so it cannot disagree with them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import EmailMode, get_settings
from keigan.entities.application_entities import Application
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import StakeholderRecipientType, TeamMemberStatus
from keigan.exceptions.keigan_exceptions import BusinessValidationException, RateLimitedException
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.notification_renderer import translate
from keigan.services.notification_service import NotificationService
from keigan.utils.time_utils import ensure_utc, utc_now

INVITATION_NOTIFICATION_TYPE = "team_invitation"


def team_member_status(stakeholder: Stakeholder) -> TeamMemberStatus:
    if not stakeholder.is_active:
        return TeamMemberStatus.INACTIVE
    if stakeholder.joined_at is not None:
        return TeamMemberStatus.ACTIVE
    if stakeholder.invited_at is not None:
        return TeamMemberStatus.INVITED
    return TeamMemberStatus.LISTED


def describe_invitation(stakeholder: Stakeholder, now: datetime) -> dict[str, Any]:
    """The invitation fields of a stakeholder response: status, dates, whether the invitation is stale and whether another may be sent now."""
    settings = get_settings()
    status = team_member_status(stakeholder)
    invited_at, last_sent_at = ensure_utc(stakeholder.invited_at), ensure_utc(stakeholder.last_invitation_sent_at)
    next_allowed_at = last_sent_at + timedelta(minutes=settings.team_invitation_resend_cooldown_minutes) if last_sent_at else None
    can_send = (
        stakeholder.recipient_type == StakeholderRecipientType.PERSON and bool(stakeholder.email_address)
        and status in (TeamMemberStatus.LISTED, TeamMemberStatus.INVITED) and (next_allowed_at is None or now >= next_allowed_at)
    )
    return {
        "team_member_status": status, "invited_at": invited_at, "invited_by_user_principal_name": stakeholder.invited_by_user_principal_name,
        "last_invitation_sent_at": last_sent_at, "joined_at": ensure_utc(stakeholder.joined_at), "next_invitation_allowed_at": next_allowed_at, "can_send_invitation": can_send,
        "invitation_is_stale": status == TeamMemberStatus.INVITED and invited_at is not None and now - invited_at > timedelta(days=settings.team_invitation_stale_after_days),
    }


class TeamInvitationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    def ensure_can_invite(self, stakeholder: Stakeholder, now: datetime) -> None:
        """Raises the reason, in words for the admin who clicked, when this member cannot be invited right now."""
        if stakeholder.recipient_type != StakeholderRecipientType.PERSON:
            raise BusinessValidationException("Only people can be invited, not distribution lists or Teams channels.")
        if not stakeholder.email_address:
            raise BusinessValidationException(f"{stakeholder.display_name} has no email address. Add one before sending an invitation.")
        if not stakeholder.is_active:
            raise BusinessValidationException(f"{stakeholder.display_name} is switched off. Switch them on before sending an invitation.")
        if stakeholder.joined_at is not None:
            raise BusinessValidationException(f"{stakeholder.display_name} has already signed in to Keigan, so no invitation is needed.")
        last_sent_at = ensure_utc(stakeholder.last_invitation_sent_at)
        if last_sent_at is not None:
            wait_seconds = (last_sent_at + timedelta(minutes=self.settings.team_invitation_resend_cooldown_minutes) - now).total_seconds()
            if wait_seconds > 0:
                minutes_ago = max(0, int((now - last_sent_at).total_seconds() // 60))
                raise RateLimitedException(f"An invitation was sent {minutes_ago} minute(s) ago. You can send another in {int(wait_seconds // 60) + 1} minute(s).")

    async def queue_invitation(self, current_user: CurrentUser, stakeholder: Stakeholder, application: Application) -> tuple[str | None, str]:
        """Queue the invitation email and record that it was sent. Returns the outbox id and a message for the admin."""
        now = utc_now()
        self.ensure_can_invite(stakeholder, now)
        language = stakeholder.preferred_language_code
        notification_service = NotificationService(self.session)
        rendered = notification_service.renderer.render_email(
            INVITATION_NOTIFICATION_TYPE, language, application.application_name, application.application_name,
            facts=[
                (translate(language, "labels.application"), application.application_name),
                (translate(language, "labels.role"), translate(language, f"roles.{stakeholder.stakeholder_role}")),
                (translate(language, "labels.invited_by"), current_user.display_name),
            ],
            body_markdown=translate(language, f"types.{INVITATION_NOTIFICATION_TYPE}.access_note", reader_group=application.reader_group_name, admin_group=application.admin_group_name),
            action_path=f"/applications/{application.application_id}",
        )
        delivery_id = await notification_service.queue_email(application.application_id, INVITATION_NOTIFICATION_TYPE, str(stakeholder.email_address), rendered)
        is_resend = stakeholder.invited_at is not None
        stakeholder.invited_at = stakeholder.invited_at or now
        stakeholder.invited_by_user_principal_name = stakeholder.invited_by_user_principal_name or current_user.user_principal_name
        stakeholder.last_invitation_sent_at = now
        await AuditService(self.session).record(
            current_user, "team_member.resend_invitation" if is_resend else "team_member.invite", target_entity_type="stakeholder", target_entity_id=stakeholder.stakeholder_id,
            application_id=application.application_id, action_details={"displayName": stakeholder.display_name},
        )
        message = f"An invitation was queued for {stakeholder.email_address}."
        if self.settings.email_mode == EmailMode.SIMULATED:
            message += " Email is in simulated mode, so nothing leaves Keigan."
        return delivery_id, message

    async def record_sign_in(self, current_user: CurrentUser) -> int:
        """A person signed in: every active team member of any application who matches their sign-in name or email becomes active. Returns how many."""
        addresses = {address.lower() for address in (current_user.user_principal_name, current_user.email_address) if address}
        if not addresses:
            return 0
        waiting_members = (
            await self.session.scalars(
                select(Stakeholder).where(
                    Stakeholder.recipient_type == StakeholderRecipientType.PERSON, Stakeholder.is_active.is_(True), Stakeholder.joined_at.is_(None),
                    or_(func.lower(Stakeholder.user_principal_name).in_(addresses), func.lower(Stakeholder.email_address).in_(addresses)),
                )
            )
        ).all()
        now = utc_now()
        for member in waiting_members:
            member.joined_at = now
        await self.session.flush()  # so a second call in the same transaction no longer finds them waiting
        return len(waiting_members)

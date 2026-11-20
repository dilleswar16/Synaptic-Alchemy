"""Who may talk to Keigan in an incident's Teams chat (V13).

Everyone in the chat can write a message, but Keigan answers, digests and acts only for people who may read the incident's
application in Keigan. The sender's Entra group memberships are looked up through the same Microsoft Graph lookup that sign-in
uses (read-only); in local development mode the sender is matched to a demo user instead. Anyone who cannot be resolved is treated
as having no access (fail closed).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import AuthenticationMode, get_settings
from keigan.security.current_user import CurrentUser
from keigan.services.authentication_service import AuthenticationService, LocalUserDefinition, load_local_users
from keigan.services.authorization_service import AuthorizationService

logger = logging.getLogger(__name__)
_ENTRA_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class TeamsSenderAccess:
    can_read: bool = False
    is_application_admin: bool = False


NO_ACCESS = TeamsSenderAccess()


class TeamsSenderAuthorizer:
    def __init__(self, session: AsyncSession):
        self.authorization_service = AuthorizationService(session)

    async def access_for(self, application_id: str, sender_identity: str | None, sender_display_name: str | None, authenticated_user: CurrentUser | None = None) -> TeamsSenderAccess:
        """``sender_identity`` is an Entra object id (live Teams) or a user principal name (simulated chat). ``authenticated_user`` is set when
        Keigan itself already authenticated the sender (a message posted from the Keigan UI)."""
        user = authenticated_user or await self._resolve_user(sender_identity, sender_display_name)
        if user is None:
            return NO_ACCESS
        if not await self.authorization_service.can_read_application(user, application_id):
            return NO_ACCESS
        return TeamsSenderAccess(can_read=True, is_application_admin=await self.authorization_service.can_edit_application(user, application_id))

    async def _resolve_user(self, sender_identity: str | None, sender_display_name: str | None) -> CurrentUser | None:
        if get_settings().auth_mode == AuthenticationMode.ENTRA:
            return await self._user_from_entra_groups(sender_identity, sender_display_name)
        local_user = self._find_local_user(sender_identity, sender_display_name)
        if local_user is None:
            return None
        return AuthenticationService._build_current_user(
            local_user.user_principal_name, local_user.display_name, local_user.email_address, frozenset(local_user.group_names), frozenset(), preferred_locale=local_user.preferred_locale
        )

    @staticmethod
    async def _user_from_entra_groups(sender_identity: str | None, sender_display_name: str | None) -> CurrentUser | None:
        if not sender_identity or not _ENTRA_OBJECT_ID_PATTERN.match(sender_identity):
            return None
        memberships = await AuthenticationService._resolve_group_memberships(sender_identity)
        if memberships is None:  # Graph unavailable: no answer rather than a guess
            logger.warning("Could not resolve the groups of a Teams sender; treating the sender as having no access")
            return None
        return AuthenticationService._build_current_user(sender_identity, sender_display_name or sender_identity, None, memberships[0], memberships[1], entra_object_id=sender_identity)

    @staticmethod
    def _find_local_user(sender_identity: str | None, sender_display_name: str | None) -> LocalUserDefinition | None:
        identity, display_name = (sender_identity or "").lower(), (sender_display_name or "").lower()
        for local_user in load_local_users():
            if identity in (local_user.user_principal_name.lower(), local_user.email_address.lower()) or (display_name and display_name == local_user.display_name.lower()):
                return local_user
        return None

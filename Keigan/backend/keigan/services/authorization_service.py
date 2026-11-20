"""Role-based access control: Keigan admin, application admin, application reader (from Entra / SailPoint groups)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import AuthenticationMode, get_settings
from keigan.entities.application_entities import Application
from keigan.entities.status_values import ApplicationLifecycleStatus
from keigan.exceptions.keigan_exceptions import ForbiddenException, NotFoundException
from keigan.security.current_user import CurrentUser

ROLE_ADMIN = "admin"
ROLE_READER = "reader"
DRAFT_LIFECYCLE_STATUSES = (ApplicationLifecycleStatus.REQUESTED, ApplicationLifecycleStatus.DRAFT)
# An onboarding request stays "requested" until a Keigan admin accepts it (it then becomes "draft"). Telemetry is never read before that.
UNAPPROVED_LIFECYCLE_STATUSES = ("requested",)
GROUPS_NOT_LINKED_MESSAGE = (
    "This application's access groups are not linked to Entra yet, so Keigan cannot tell who is a member. "
    "Ask a Keigan admin to run 'Check in Entra' on the application's Access step."
)


@dataclass(frozen=True)
class ApplicationRole:
    application_id: str
    application_code: str
    application_name: str
    role: str
    lifecycle_status: str


class AuthorizationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    @staticmethod
    def ensure_keigan_admin(current_user: CurrentUser) -> None:
        if not current_user.is_keigan_admin:
            raise ForbiddenException("Only Keigan admins can do this.")

    def _group_membership_check(self, current_user: CurrentUser) -> Callable[[str | None, str | None], bool]:
        """Entra display names are neither unique nor fixed, so with Entra sign-in only the group object id counts.
        Local sign-in tokens carry group names only, so there (and only there) the name counts."""
        if self.settings.auth_mode == AuthenticationMode.ENTRA:
            user_group_object_ids = {object_id.lower() for object_id in current_user.group_object_ids}
            return lambda _group_name, group_object_id: bool(group_object_id) and group_object_id.lower() in user_group_object_ids
        user_group_names = {group_name.lower() for group_name in current_user.group_names}
        return lambda group_name, _group_object_id: bool(group_name) and group_name.lower() in user_group_names

    async def application_roles(self, current_user: CurrentUser) -> dict[str, ApplicationRole]:
        """Every application the user can access with their strongest role. Cached on the user for the request."""
        if current_user.application_roles_by_application_id is not None:
            return current_user.application_roles_by_application_id

        is_member_of = self._group_membership_check(current_user)
        application_rows = (
            await self.session.execute(
                select(
                    Application.application_id,
                    Application.application_code,
                    Application.application_name,
                    Application.lifecycle_status,
                    Application.admin_group_name,
                    Application.admin_group_object_id,
                    Application.reader_group_name,
                    Application.reader_group_object_id,
                    Application.created_by_user_principal_name,
                )
            )
        ).all()

        roles_by_application_id: dict[str, ApplicationRole] = {}
        for application_row in application_rows:
            is_admin_member = current_user.is_keigan_admin or is_member_of(application_row.admin_group_name, application_row.admin_group_object_id)
            is_draft_owner = (
                application_row.lifecycle_status in DRAFT_LIFECYCLE_STATUSES
                and application_row.created_by_user_principal_name == current_user.user_principal_name
            )
            is_reader_member = is_member_of(application_row.reader_group_name, application_row.reader_group_object_id)
            granted_role = ROLE_ADMIN if (is_admin_member or is_draft_owner) else ROLE_READER if is_reader_member else None
            if granted_role:
                roles_by_application_id[application_row.application_id] = ApplicationRole(
                    application_id=application_row.application_id,
                    application_code=application_row.application_code,
                    application_name=application_row.application_name,
                    role=granted_role,
                    lifecycle_status=application_row.lifecycle_status,
                )
        current_user.application_roles_by_application_id = roles_by_application_id
        return roles_by_application_id

    async def readable_application_ids(self, current_user: CurrentUser) -> set[str]:
        return set((await self.application_roles(current_user)).keys())

    async def editable_application_ids(self, current_user: CurrentUser) -> set[str]:
        return {
            application_id for application_id, role in (await self.application_roles(current_user)).items() if role.role == ROLE_ADMIN
        }

    async def scoped_application_ids(self, current_user: CurrentUser, requested_application_ids: list[str] | None) -> list[str]:
        """Intersect the requested scope with what the user may read (empty request = everything readable)."""
        readable_ids = await self.readable_application_ids(current_user)
        if not requested_application_ids:
            return sorted(readable_ids)
        return [application_id for application_id in requested_application_ids if application_id in readable_ids]

    async def can_read_application(self, current_user: CurrentUser, application_id: str) -> bool:
        return application_id in await self.readable_application_ids(current_user)

    async def can_edit_application(self, current_user: CurrentUser, application_id: str) -> bool:
        return application_id in await self.editable_application_ids(current_user)

    async def ensure_application_reader(self, current_user: CurrentUser, application_id: str) -> None:
        if current_user.is_system_actor:
            return
        if not await self.can_read_application(current_user, application_id):
            application = await self.session.get(Application, application_id)
            if application is None:
                raise NotFoundException("The application was not found.")
            if self.settings.auth_mode == AuthenticationMode.ENTRA and not (application.admin_group_object_id and application.reader_group_object_id):
                raise ForbiddenException(GROUPS_NOT_LINKED_MESSAGE)
            raise ForbiddenException("You are not a member of this application's reader or admin group.")

    async def ensure_application_admin(self, current_user: CurrentUser, application_id: str) -> None:
        if current_user.is_system_actor:
            return
        await self.ensure_application_reader(current_user, application_id)
        if not await self.can_edit_application(current_user, application_id):
            raise ForbiddenException("Only this application's admins can change it.")

"""The authenticated user bean and the FastAPI dependencies that resolve and authorize it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.database_config import DatabaseSession
from keigan.exceptions.keigan_exceptions import AuthenticationException

if TYPE_CHECKING:
    from keigan.services.authorization_service import ApplicationRole


@dataclass
class CurrentUser:
    user_principal_name: str
    display_name: str
    email_address: str | None
    group_names: frozenset[str]
    group_object_ids: frozenset[str]
    is_keigan_admin: bool
    entra_object_id: str | None = None
    preferred_locale: str | None = None
    # Filled lazily by AuthorizationService once per request.
    application_roles_by_application_id: dict[str, "ApplicationRole"] | None = field(default=None, repr=False)

    @property
    def is_system_actor(self) -> bool:
        return self.user_principal_name.startswith("system:")


SYSTEM_WORKER_USER = CurrentUser(
    user_principal_name="system:worker",
    display_name="Keigan",
    email_address=None,
    group_names=frozenset(),
    group_object_ids=frozenset(),
    is_keigan_admin=True,
)


def _extract_bearer_token(request: Request) -> str:
    authorization_header = request.headers.get("authorization", "")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationException("Sign in to use Keigan.")
    return token.strip()


async def get_current_user(request: Request) -> CurrentUser:
    """Validate the bearer token (local or Entra) and return the user. Cached per request."""
    cached_user = getattr(request.state, "current_user", None)
    if cached_user is not None:
        return cached_user
    from keigan.services.authentication_service import AuthenticationService

    current_user = await AuthenticationService.authenticate_bearer_token(_extract_bearer_token(request))
    request.state.current_user = current_user
    return current_user


async def require_keigan_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    from keigan.services.authorization_service import AuthorizationService

    AuthorizationService.ensure_keigan_admin(current_user)
    return current_user


async def require_application_reader(
    application_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = DatabaseSession,
) -> CurrentUser:
    """Dependency for routes with an ``{application_id}`` path parameter that need read access."""
    from keigan.services.authorization_service import AuthorizationService

    await AuthorizationService(session).ensure_application_reader(current_user, application_id)
    return current_user


async def require_application_admin(
    application_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = DatabaseSession,
) -> CurrentUser:
    """Dependency for routes with an ``{application_id}`` path parameter that need edit access."""
    from keigan.services.authorization_service import AuthorizationService

    await AuthorizationService(session).ensure_application_admin(current_user, application_id)
    return current_user

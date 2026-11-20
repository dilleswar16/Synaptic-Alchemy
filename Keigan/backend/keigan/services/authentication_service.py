"""Authentication: local dummy users (development) and Microsoft Entra ID access tokens (production)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import httpx
import jwt
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import RESOURCES_DIRECTORY, AuthenticationMode, get_settings
from keigan.entities.platform_entities import PlatformUser
from keigan.exceptions.keigan_exceptions import (
    AuthenticationException,
    BusinessValidationException,
    ForbiddenException,
    NotFoundException,
)
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser

logger = logging.getLogger(__name__)

LOCAL_TOKEN_ISSUER = "keigan-local"
LOCAL_TOKEN_AUDIENCE = "keigan-api"
GROUP_MEMBERSHIP_CACHE_SECONDS = 600


@dataclass(frozen=True)
class LocalUserDefinition:
    user_principal_name: str
    display_name: str
    email_address: str
    role_description: str
    group_names: tuple[str, ...]
    preferred_locale: str


@lru_cache
def load_local_users() -> tuple[LocalUserDefinition, ...]:
    local_users_document = yaml.safe_load((RESOURCES_DIRECTORY / "local_users.yaml").read_text(encoding="utf-8"))
    return tuple(
        LocalUserDefinition(
            user_principal_name=user_entry["user_principal_name"],
            display_name=user_entry["display_name"],
            email_address=user_entry["email_address"],
            role_description=user_entry.get("role_description", ""),
            group_names=tuple(user_entry.get("group_names") or []),
            preferred_locale=user_entry.get("preferred_locale", "en"),
        )
        for user_entry in local_users_document["local_users"]
    )


@lru_cache
def _entra_signing_key_client() -> jwt.PyJWKClient:
    settings = get_settings()
    return jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys", cache_keys=True, lifespan=3600
    )


class _GroupMembershipCache:
    """Caches Entra group memberships resolved through Microsoft Graph (handles group overage and id→name)."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, frozenset[str], frozenset[str]]] = {}

    def read(self, entra_object_id: str) -> tuple[frozenset[str], frozenset[str]] | None:
        cache_entry = self._entries.get(entra_object_id)
        if cache_entry and time.monotonic() - cache_entry[0] < GROUP_MEMBERSHIP_CACHE_SECONDS:
            return cache_entry[1], cache_entry[2]
        return None

    def write(self, entra_object_id: str, group_names: frozenset[str], group_object_ids: frozenset[str]) -> None:
        self._entries[entra_object_id] = (time.monotonic(), group_names, group_object_ids)


_group_membership_cache = _GroupMembershipCache()


class AuthenticationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repository = BaseRepository(session, PlatformUser)

    # ── Token validation (no database needed) ─────────────────────────────────
    @classmethod
    async def authenticate_bearer_token(cls, bearer_token: str) -> CurrentUser:
        settings = get_settings()
        if settings.auth_mode == AuthenticationMode.LOCAL:
            return cls._authenticate_local_token(bearer_token)
        return await cls._authenticate_entra_token(bearer_token)

    @staticmethod
    def _build_current_user(
        user_principal_name: str,
        display_name: str,
        email_address: str | None,
        group_names: frozenset[str],
        group_object_ids: frozenset[str],
        entra_object_id: str | None = None,
        preferred_locale: str | None = None,
    ) -> CurrentUser:
        settings = get_settings()
        lowercase_group_names = {group_name.lower() for group_name in group_names}
        is_keigan_admin = settings.keigan_admin_group_name.lower() in lowercase_group_names or (
            bool(settings.keigan_admin_group_object_id) and settings.keigan_admin_group_object_id in group_object_ids
        )
        return CurrentUser(
            user_principal_name=user_principal_name,
            display_name=display_name,
            email_address=email_address,
            group_names=group_names,
            group_object_ids=group_object_ids,
            is_keigan_admin=is_keigan_admin,
            entra_object_id=entra_object_id,
            preferred_locale=preferred_locale,
        )

    @classmethod
    def _authenticate_local_token(cls, bearer_token: str) -> CurrentUser:
        settings = get_settings()
        try:
            token_claims = jwt.decode(
                bearer_token,
                settings.local_token_signing_secret,
                algorithms=["HS256"],
                audience=LOCAL_TOKEN_AUDIENCE,
                issuer=LOCAL_TOKEN_ISSUER,
            )
        except jwt.PyJWTError as token_error:
            raise AuthenticationException("Your session has expired. Sign in again.") from token_error
        return cls._build_current_user(
            user_principal_name=token_claims["sub"],
            display_name=token_claims.get("name", token_claims["sub"]),
            email_address=token_claims.get("email"),
            group_names=frozenset(token_claims.get("groups", [])),
            group_object_ids=frozenset(),
            preferred_locale=token_claims.get("locale"),
        )

    @classmethod
    async def _authenticate_entra_token(cls, bearer_token: str) -> CurrentUser:
        settings = get_settings()
        accepted_audiences = [
            audience
            for audience in (settings.entra_api_audience, f"api://{settings.entra_api_client_id}", settings.entra_api_client_id)
            if audience
        ]
        accepted_issuers = [
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
            f"https://sts.windows.net/{settings.entra_tenant_id}/",
        ]
        try:
            signing_key = await asyncio.to_thread(_entra_signing_key_client().get_signing_key_from_jwt, bearer_token)
            token_claims: dict[str, Any] = jwt.decode(
                bearer_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=accepted_audiences,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.PyJWTError as token_error:
            raise AuthenticationException("Your Microsoft sign-in is not valid for Keigan. Sign in again.") from token_error
        if token_claims.get("iss") not in accepted_issuers or token_claims.get("tid") != settings.entra_tenant_id:
            logger.warning("Rejected an Entra token from tenant %s (issuer %s).", token_claims.get("tid"), token_claims.get("iss"))
            raise AuthenticationException("The token was issued by an unexpected tenant.")
        cls._require_delegated_scope_or_allowed_app_role(token_claims)

        entra_object_id = token_claims.get("oid")
        token_group_object_ids = frozenset(token_claims.get("groups", []))
        group_names, group_object_ids = frozenset(), token_group_object_ids
        if entra_object_id:
            resolved_memberships = await cls._resolve_group_memberships(entra_object_id)
            if resolved_memberships is not None:
                group_names, group_object_ids = resolved_memberships[0], resolved_memberships[1] | token_group_object_ids
        user_principal_name = token_claims.get("preferred_username") or token_claims.get("upn") or entra_object_id or "unknown"
        return cls._build_current_user(
            user_principal_name=user_principal_name,
            display_name=token_claims.get("name", user_principal_name),
            email_address=token_claims.get("email") or token_claims.get("preferred_username"),
            group_names=group_names,
            group_object_ids=group_object_ids,
            entra_object_id=entra_object_id,
        )

    @staticmethod
    def _require_delegated_scope_or_allowed_app_role(token_claims: dict[str, Any]) -> None:
        """A token for the Keigan API must be a user token with Keigan's scope, or come from an explicitly allowed app role.

        Without this, any service principal in the tenant that can obtain a token for the API would act as a user with no groups.
        """
        settings = get_settings()
        granted_scopes = str(token_claims.get("scp", "")).split()
        granted_app_roles = set(token_claims.get("roles") or [])
        if settings.entra_delegated_scope_name in granted_scopes or granted_app_roles & set(settings.entra_allowed_app_role_list):
            return
        logger.warning(
            "Rejected an Entra token without the %s scope or an allowed app role (scopes: %s, roles: %s).",
            settings.entra_delegated_scope_name,
            granted_scopes,
            sorted(granted_app_roles),
        )
        raise ForbiddenException(
            "Your Microsoft sign-in does not include permission to use Keigan. Sign in again, and ask a Keigan admin if it keeps happening."
        )

    @staticmethod
    async def _resolve_group_memberships(entra_object_id: str) -> tuple[frozenset[str], frozenset[str]] | None:
        """Read the user's transitive group memberships (names and ids) from Microsoft Graph, cached for 10 minutes."""
        cached_memberships = _group_membership_cache.read(entra_object_id)
        if cached_memberships is not None:
            return cached_memberships
        from keigan.config import application_context

        try:
            graph_access_token = await application_context.azure_credential_provider().get_access_token(
                "https://graph.microsoft.com/.default"
            )
            group_names: set[str] = set()
            group_object_ids: set[str] = set()
            next_page_url: str | None = (
                f"https://graph.microsoft.com/v1.0/users/{entra_object_id}/transitiveMemberOf/microsoft.graph.group"
                "?$select=id,displayName&$top=999"
            )
            async with httpx.AsyncClient(timeout=15) as http_client:
                while next_page_url:
                    graph_response = await http_client.get(next_page_url, headers={"Authorization": f"Bearer {graph_access_token}"})
                    graph_response.raise_for_status()
                    response_body = graph_response.json()
                    for group_entry in response_body.get("value", []):
                        group_object_ids.add(group_entry["id"])
                        if group_entry.get("displayName"):
                            group_names.add(group_entry["displayName"])
                    next_page_url = response_body.get("@odata.nextLink")
        except Exception as graph_error:  # noqa: BLE001 — fall back to token group ids only
            logger.warning("Could not resolve group memberships from Microsoft Graph: %s", graph_error)
            return None
        resolved_memberships = (frozenset(group_names), frozenset(group_object_ids))
        _group_membership_cache.write(entra_object_id, *resolved_memberships)
        return resolved_memberships

    # ── Local sign-in ──────────────────────────────────────────────────────────
    @staticmethod
    def list_local_users() -> list[LocalUserDefinition]:
        if get_settings().auth_mode != AuthenticationMode.LOCAL:
            raise NotFoundException("Local users are only available in local authentication mode.")
        return list(load_local_users())

    async def sign_in_local_user(self, user_principal_name: str) -> tuple[str, datetime, CurrentUser]:
        settings = get_settings()
        if settings.auth_mode != AuthenticationMode.LOCAL:
            raise BusinessValidationException("Local sign-in is disabled. Use Microsoft sign-in.")
        local_user = next(
            (user for user in load_local_users() if user.user_principal_name.lower() == user_principal_name.lower()), None
        )
        if local_user is None:
            raise AuthenticationException("Unknown local user.")
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.local_token_lifetime_minutes)
        access_token = jwt.encode(
            {
                "sub": local_user.user_principal_name,
                "name": local_user.display_name,
                "email": local_user.email_address,
                "groups": list(local_user.group_names),
                "locale": local_user.preferred_locale,
                "iss": LOCAL_TOKEN_ISSUER,
                "aud": LOCAL_TOKEN_AUDIENCE,
                "iat": datetime.now(UTC),
                "exp": expires_at,
            },
            settings.local_token_signing_secret,
            algorithm="HS256",
        )
        current_user = self._build_current_user(
            user_principal_name=local_user.user_principal_name,
            display_name=local_user.display_name,
            email_address=local_user.email_address,
            group_names=frozenset(local_user.group_names),
            group_object_ids=frozenset(),
            preferred_locale=local_user.preferred_locale,
        )
        await self.record_sign_in(current_user)
        return access_token, expires_at, current_user

    # ── Profile ────────────────────────────────────────────────────────────────
    async def record_sign_in(self, current_user: CurrentUser) -> PlatformUser:
        platform_user = await self.get_or_create_profile(current_user)
        platform_user.last_sign_in_at = datetime.now(UTC)
        platform_user.last_known_group_names_json = sorted(current_user.group_names)
        return platform_user

    async def get_or_create_profile(self, current_user: CurrentUser) -> PlatformUser:
        platform_user = await self.user_repository.find_one(PlatformUser.user_principal_name == current_user.user_principal_name)
        if platform_user is None:
            platform_user = await self.user_repository.add(
                PlatformUser(
                    user_principal_name=current_user.user_principal_name,
                    display_name=current_user.display_name,
                    email_address=current_user.email_address,
                    entra_object_id=current_user.entra_object_id,
                    preferred_locale=current_user.preferred_locale,
                    preferred_theme="system",
                    created_by_user_principal_name=current_user.user_principal_name,
                )
            )
        return platform_user

    async def update_preferences(self, current_user: CurrentUser, preferred_locale: str | None, preferred_theme: str | None) -> PlatformUser:
        platform_user = await self.get_or_create_profile(current_user)
        if preferred_locale is not None:
            platform_user.preferred_locale = preferred_locale
        if preferred_theme is not None:
            platform_user.preferred_theme = preferred_theme
        platform_user.updated_by_user_principal_name = current_user.user_principal_name
        return platform_user

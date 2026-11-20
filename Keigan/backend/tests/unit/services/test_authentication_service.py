"""keigan/services/authentication_service.py: Entra access token checks (H8 tenant, S5 delegated scope or allowed app role).

Tokens are real RS256 JWTs signed with a throw-away key; only the download of Microsoft's public keys and the Graph group lookup
(network calls) are replaced.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from keigan.config.settings import Settings
from keigan.exceptions.keigan_exceptions import AuthenticationException, ForbiddenException
from keigan.services import authentication_service
from keigan.services.authentication_service import AuthenticationService

TENANT_ID = "11111111-1111-1111-1111-111111111111"
API_CLIENT_ID = "22222222-2222-2222-2222-222222222222"
STRONG_SECRET = "a-long-random-value-that-is-not-the-default-0123456789"
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def entra_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        environment="dev",
        auth_mode="entra",
        entra_tenant_id=TENANT_ID,
        entra_api_client_id=API_CLIENT_ID,
        entra_api_scope=f"api://{API_CLIENT_ID}/access_as_user",
        local_token_signing_secret=STRONG_SECRET,
        local_secret_encryption_key=STRONG_SECRET,
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture
def use_settings(monkeypatch: pytest.MonkeyPatch) -> Callable[[Settings], None]:
    """Point the service at a Settings object, and replace Microsoft's key download and the Graph lookup."""

    async def no_group_lookup(entra_object_id: str) -> None:
        return None

    monkeypatch.setattr(
        authentication_service,
        "_entra_signing_key_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=SIGNING_KEY.public_key())),
    )
    monkeypatch.setattr(AuthenticationService, "_resolve_group_memberships", staticmethod(no_group_lookup))
    return lambda settings: monkeypatch.setattr(authentication_service, "get_settings", lambda: settings)


def build_token(**claim_overrides: Any) -> str:
    """A delegated user token for the Keigan API; pass ``name=None`` to drop a claim."""
    claims: dict[str, Any] = {
        "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "aud": API_CLIENT_ID,
        "tid": TENANT_ID,
        "oid": "33333333-3333-3333-3333-333333333333",
        "preferred_username": "aiko@example.com",
        "scp": "access_as_user",
        "iat": int(time.time()) - 10,
        "exp": int(time.time()) + 600,
    }
    claims.update(claim_overrides)
    return jwt.encode({name: value for name, value in claims.items() if value is not None}, SIGNING_KEY, algorithm="RS256")


async def test_delegated_user_token_with_the_required_scope_is_accepted(use_settings) -> None:
    use_settings(entra_settings())
    current_user = await AuthenticationService.authenticate_bearer_token(build_token())
    assert current_user.user_principal_name == "aiko@example.com"


async def test_required_scope_may_be_one_of_several_scopes(use_settings) -> None:
    use_settings(entra_settings())
    current_user = await AuthenticationService.authenticate_bearer_token(build_token(scp="openid access_as_user profile"))
    assert current_user.user_principal_name == "aiko@example.com"


async def test_token_without_a_tenant_claim_is_rejected(use_settings) -> None:
    use_settings(entra_settings())
    with pytest.raises(AuthenticationException, match="unexpected tenant"):
        await AuthenticationService.authenticate_bearer_token(build_token(tid=None))


async def test_token_from_another_tenant_is_rejected(use_settings) -> None:
    use_settings(entra_settings())
    with pytest.raises(AuthenticationException, match="unexpected tenant"):
        await AuthenticationService.authenticate_bearer_token(build_token(tid="99999999-9999-9999-9999-999999999999"))


async def test_token_issued_for_another_tenant_issuer_is_rejected(use_settings) -> None:
    use_settings(entra_settings())
    with pytest.raises(AuthenticationException, match="unexpected tenant"):
        await AuthenticationService.authenticate_bearer_token(
            build_token(iss="https://login.microsoftonline.com/99999999-9999-9999-9999-999999999999/v2.0")
        )


async def test_user_token_without_the_required_scope_is_rejected(use_settings) -> None:
    use_settings(entra_settings())
    with pytest.raises(ForbiddenException, match="does not include permission to use Keigan"):
        await AuthenticationService.authenticate_bearer_token(build_token(scp="User.Read"))


async def test_scope_name_comes_from_configuration(use_settings) -> None:
    use_settings(entra_settings(entra_required_delegated_scope="keigan.use"))
    with pytest.raises(ForbiddenException):
        await AuthenticationService.authenticate_bearer_token(build_token(scp="access_as_user"))
    current_user = await AuthenticationService.authenticate_bearer_token(build_token(scp="keigan.use"))
    assert current_user.user_principal_name == "aiko@example.com"


async def test_app_only_token_without_scope_or_roles_is_rejected(use_settings) -> None:
    use_settings(entra_settings())
    with pytest.raises(ForbiddenException, match="does not include permission to use Keigan"):
        await AuthenticationService.authenticate_bearer_token(build_token(scp=None, preferred_username=None))


async def test_app_only_token_with_an_app_role_that_is_not_allowed_is_rejected(use_settings) -> None:
    use_settings(entra_settings(entra_allowed_app_roles="Keigan.Service"))
    with pytest.raises(ForbiddenException):
        await AuthenticationService.authenticate_bearer_token(build_token(scp=None, roles=["Other.Role"]))


async def test_app_only_token_is_rejected_when_no_app_role_is_configured(use_settings) -> None:
    use_settings(entra_settings())
    with pytest.raises(ForbiddenException):
        await AuthenticationService.authenticate_bearer_token(build_token(scp=None, roles=["Keigan.Service"]))


async def test_app_only_token_with_an_allowed_app_role_is_accepted(use_settings) -> None:
    use_settings(entra_settings(entra_allowed_app_roles="Keigan.Service"))
    current_user = await AuthenticationService.authenticate_bearer_token(
        build_token(scp=None, preferred_username=None, roles=["Keigan.Service"])
    )
    assert current_user.user_principal_name == "33333333-3333-3333-3333-333333333333"
    assert current_user.is_keigan_admin is False

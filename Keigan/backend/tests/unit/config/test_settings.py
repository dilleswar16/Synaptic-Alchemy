"""keigan/config/settings.py: start-up refusal of unsafe authentication and secret configuration (V15, H6, S5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from keigan.config.settings import DEFAULT_LOCAL_TOKEN_SIGNING_SECRET, Settings

STRONG_SECRET = "a-long-random-value-that-is-not-the-default-0123456789"
ENTRA_SETTINGS = {
    "auth_mode": "entra",
    "entra_tenant_id": "11111111-1111-1111-1111-111111111111",
    "entra_api_client_id": "22222222-2222-2222-2222-222222222222",
    "entra_api_scope": "api://22222222-2222-2222-2222-222222222222/access_as_user",
}


def build_settings(**overrides: object) -> Settings:
    """Settings that ignore ``backend/.env``; a production-like Entra configuration unless overridden."""
    base_values: dict[str, object] = {
        "environment": "prod",
        "llm_provider": "openai_compatible",
        "llm_api_key": "not-a-real-key",
        "local_token_signing_secret": STRONG_SECRET,
        "local_secret_encryption_key": STRONG_SECRET,
        **ENTRA_SETTINGS,
    }
    return Settings(_env_file=None, **{**base_values, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize("environment_name", ["dev", "prod"])
def test_local_authentication_is_refused_outside_local_and_test_environments(environment_name: str) -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=local is only allowed when ENVIRONMENT is local or test"):
        build_settings(environment=environment_name, auth_mode="local")


@pytest.mark.parametrize("environment_name", ["local", "test"])
def test_local_authentication_is_allowed_in_local_and_test_environments(environment_name: str) -> None:
    settings = build_settings(environment=environment_name, auth_mode="local")
    assert settings.auth_mode == "local"


@pytest.mark.parametrize("environment_name", ["dev", "prod"])
def test_default_signing_secret_is_refused_outside_local_and_test_environments(environment_name: str) -> None:
    with pytest.raises(ValidationError, match="LOCAL_TOKEN_SIGNING_SECRET"):
        build_settings(environment=environment_name, local_token_signing_secret=DEFAULT_LOCAL_TOKEN_SIGNING_SECRET)


def test_default_signing_secret_is_allowed_in_the_local_environment() -> None:
    settings = build_settings(
        environment="local", auth_mode="local", llm_provider="mock", local_token_signing_secret=DEFAULT_LOCAL_TOKEN_SIGNING_SECRET
    )
    assert settings.local_token_signing_secret == DEFAULT_LOCAL_TOKEN_SIGNING_SECRET


def test_short_signing_secret_is_refused_outside_local_and_test_environments() -> None:
    with pytest.raises(ValidationError, match="LOCAL_TOKEN_SIGNING_SECRET must be at least 32 characters"):
        build_settings(environment="dev", local_token_signing_secret="too-short")


def test_missing_encryption_key_is_refused_for_the_local_secret_store_outside_local_and_test_environments() -> None:
    with pytest.raises(ValidationError, match="LOCAL_SECRET_ENCRYPTION_KEY"):
        build_settings(environment="dev", secret_store_mode="local_encrypted", local_secret_encryption_key="")


def test_short_encryption_key_is_refused_for_the_local_secret_store_outside_local_and_test_environments() -> None:
    with pytest.raises(ValidationError, match="LOCAL_SECRET_ENCRYPTION_KEY must be at least 32 characters"):
        build_settings(environment="dev", secret_store_mode="local_encrypted", local_secret_encryption_key="short")


def test_encryption_key_is_not_needed_when_key_vault_holds_the_secrets() -> None:
    settings = build_settings(
        environment="prod", secret_store_mode="key_vault", azure_key_vault_url="https://vault.example", local_secret_encryption_key=""
    )
    assert settings.secret_store_mode == "key_vault"


def test_minimum_secret_length_comes_from_configuration() -> None:
    settings = build_settings(
        environment="dev", secret_minimum_length=8, local_token_signing_secret="12345678", local_secret_encryption_key="12345678"
    )
    assert settings.secret_minimum_length == 8


def test_entra_mode_requires_a_delegated_scope_name_to_check() -> None:
    with pytest.raises(ValidationError, match="ENTRA_API_SCOPE"):
        build_settings(entra_api_scope="", entra_required_delegated_scope="")


def test_required_delegated_scope_defaults_to_the_last_part_of_the_api_scope() -> None:
    assert build_settings().entra_delegated_scope_name == "access_as_user"


def test_required_delegated_scope_can_be_set_explicitly() -> None:
    assert build_settings(entra_required_delegated_scope="keigan.use").entra_delegated_scope_name == "keigan.use"


def test_allowed_app_roles_are_read_from_a_comma_separated_list() -> None:
    assert build_settings(entra_allowed_app_roles="Keigan.Service, Keigan.Reporting").entra_allowed_app_role_list == [
        "Keigan.Service",
        "Keigan.Reporting",
    ]


def test_no_app_roles_are_allowed_by_default() -> None:
    assert build_settings().entra_allowed_app_role_list == []

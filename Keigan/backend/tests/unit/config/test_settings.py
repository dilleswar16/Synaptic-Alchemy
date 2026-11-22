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


@pytest.mark.parametrize("invalid_limit", [0, -1])
def test_the_investigation_limit_must_allow_at_least_one_investigation(invalid_limit: int) -> None:
    """A limit of 0 would leave every investigation queued for ever, with no error to explain it."""
    with pytest.raises(ValidationError, match="investigation_max_concurrent"):
        build_settings(investigation_max_concurrent=invalid_limit)


def test_prompt_text_logging_is_only_allowed_on_a_developer_machine() -> None:
    assert build_settings(environment="local", auth_mode="local", log_prompts_for_debugging=True).log_prompts_for_debugging is True
    for environment_name in ("test", "dev", "prod"):
        overrides = {"auth_mode": "local"} if environment_name == "test" else {}
        with pytest.raises(ValidationError, match="LOG_PROMPTS_FOR_DEBUGGING"):
            build_settings(environment=environment_name, log_prompts_for_debugging=True, **overrides)


# ── The honest-outcomes thresholds (spec 27, 4.6) ────────────────────────────────────────────────


def test_the_state_thresholds_and_the_checks_per_service_have_documented_defaults() -> None:
    settings = build_settings()
    assert (settings.investigation_supported_minimum_confidence, settings.investigation_ruled_out_maximum_confidence, settings.investigation_max_checks_per_service) == (0.5, 0.2, 7)


@pytest.mark.parametrize(("supported_minimum", "ruled_out_maximum"), [(0.3, 0.3), (0.2, 0.5)])
def test_a_ruled_out_ceiling_at_or_above_the_supported_floor_is_refused(supported_minimum: float, ruled_out_maximum: float) -> None:
    with pytest.raises(ValidationError, match="INVESTIGATION_RULED_OUT_MAXIMUM_CONFIDENCE.*INVESTIGATION_SUPPORTED_MINIMUM_CONFIDENCE"):
        build_settings(investigation_supported_minimum_confidence=supported_minimum, investigation_ruled_out_maximum_confidence=ruled_out_maximum)


@pytest.mark.parametrize("field_name, value", [("investigation_supported_minimum_confidence", 1.1), ("investigation_ruled_out_maximum_confidence", -0.1), ("investigation_max_checks_per_service", 0), ("investigation_max_checks_per_service", 31)])
def test_the_honest_outcomes_settings_refuse_values_out_of_range(field_name: str, value: float) -> None:
    with pytest.raises(ValidationError):
        build_settings(**{field_name: value})


# ── The settings shown to administrators never carry a credential ────────────────────────────────


def test_a_password_inside_a_connection_url_is_not_shown() -> None:
    from keigan.config.settings import safe_settings_for_display

    displayed = safe_settings_for_display(build_settings(database_url="mssql+aioodbc://keigan_user:S3cret!pass@sql.example.net:1433/keigan?driver=ODBC+Driver+18+for+SQL+Server"))
    assert "S3cret" not in str(displayed["database_url"]) and "keigan_user" not in str(displayed["database_url"])
    assert "sql.example.net:1433/keigan" in str(displayed["database_url"]), "the host and database stay visible: an admin needs them"


def test_a_password_written_as_a_key_value_pair_is_not_shown() -> None:
    from keigan.config.settings import redact_credentials

    assert redact_credentials("Server=tcp:sql.example.net;Database=keigan;User Id=app;Password=Hunter2;Encrypt=yes") == "Server=tcp:sql.example.net;Database=keigan;User Id=app;Password=••••;Encrypt=yes"
    assert redact_credentials("DefaultEndpointsProtocol=https;AccountName=a;AccountKey=abc123==;EndpointSuffix=core.windows.net").count("abc123") == 0


def test_headers_and_tokens_are_masked_by_name() -> None:
    from keigan.config.settings import safe_settings_for_display

    displayed = safe_settings_for_display(build_settings(llm_extra_headers_json='{"Ocp-Apim-Subscription-Key":"abc"}'))
    assert displayed["llm_extra_headers_json"] == "•••• set"


def test_a_number_is_shown_even_when_its_name_contains_a_secret_word() -> None:
    from keigan.config.settings import safe_settings_for_display

    displayed = safe_settings_for_display(build_settings(ask_keigan_answer_token_budget=70_000, llm_daily_token_budget_per_application=123_456))
    assert displayed["ask_keigan_answer_token_budget"] == 70_000, "a token budget is a number, not a credential"
    assert displayed["llm_daily_token_budget_per_application"] == 123_456
    assert displayed["local_token_signing_secret"] != build_settings().local_token_signing_secret, "a real secret stays masked"


def test_a_plain_value_is_shown_as_it_is() -> None:
    from keigan.config.settings import redact_credentials

    assert redact_credentials("https://login.microsoftonline.com/tenant") == "https://login.microsoftonline.com/tenant"

"""Typed application settings (the Python equivalent of Spring's application.properties).

Every value is read from environment variables or ``backend/.env``. Nothing else in the code base reads
``os.environ`` directly: inject ``get_settings()`` instead.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT_DIRECTORY = Path(__file__).resolve().parents[2]
RESOURCES_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
# Published in the repository, so it is a known value: it may only be used on a developer machine or in the test suite.
DEFAULT_LOCAL_TOKEN_SIGNING_SECRET = "local-development-only-change-me-0123456789abcdef"


class EnvironmentName(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


LOCAL_AUTHENTICATION_ENVIRONMENTS = frozenset({EnvironmentName.LOCAL, EnvironmentName.TEST})


class AuthenticationMode(StrEnum):
    LOCAL = "local"
    ENTRA = "entra"


class IntegrationMode(StrEnum):
    LIVE = "live"
    SIMULATED = "simulated"
    DISABLED = "disabled"


class EmailMode(StrEnum):
    GRAPH = "graph"
    SMTP = "smtp"
    SIMULATED = "simulated"
    DISABLED = "disabled"


class LlmProviderName(StrEnum):
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class AzureIdentityMode(StrEnum):
    MANAGED_IDENTITY = "managed_identity"
    WORKLOAD_IDENTITY = "workload_identity"
    CLIENT_SECRET = "client_secret"
    AZURE_CLI = "azure_cli"
    NONE = "none"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT_DIRECTORY / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Runtime ────────────────────────────────────────────────────────────────
    environment: EnvironmentName = EnvironmentName.LOCAL
    log_level: str = "INFO"
    product_version: str = "0.1.0"
    run_workers_in_process: bool = True
    worker_name: str = "keigan-worker-local"
    worker_concurrency: int = 4
    worker_poll_interval_seconds: float = 2.0
    auto_create_schema: bool = True
    public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    cors_allowed_origins: str = "http://localhost:5173"
    enable_api_docs: bool = True
    data_directory: Path = BACKEND_ROOT_DIRECTORY / "data"

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = f"sqlite+aiosqlite:///{(BACKEND_ROOT_DIRECTORY / 'data' / 'keigan.db').as_posix()}"
    database_pool_size: int = 10
    database_echo_statements: bool = False
    # Azure SQL / PostgreSQL schema that holds Keigan's tables (ignored by SQLite). The DDL scripts create "keigan".
    database_schema: str = ""
    # connection_string: credentials are in DATABASE_URL · managed_identity: Entra access token of Keigan's identity (Azure SQL)
    database_authentication: str = "connection_string"

    # ── Authentication and authorization ───────────────────────────────────────
    auth_mode: AuthenticationMode = AuthenticationMode.LOCAL
    local_token_signing_secret: str = DEFAULT_LOCAL_TOKEN_SIGNING_SECRET
    # Shortest accepted LOCAL_TOKEN_SIGNING_SECRET and LOCAL_SECRET_ENCRYPTION_KEY outside the local and test environments.
    secret_minimum_length: int = 32
    local_token_lifetime_minutes: int = 480
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_api_audience: str = ""
    entra_spa_client_id: str = ""
    entra_api_scope: str = ""
    # Delegated scope a user token must carry in its "scp" claim. Empty: the last part of ENTRA_API_SCOPE (access_as_user).
    entra_required_delegated_scope: str = ""
    # Comma-separated app roles ("roles" claim) that may call the API without a user (service principals). Empty: none.
    entra_allowed_app_roles: str = ""
    keigan_admin_group_name: str = "KEIGAN_admin"
    keigan_admin_group_object_id: str = ""
    application_admin_group_pattern: str = "{application_code}_admin"
    application_reader_group_pattern: str = "{application_code}_reader"

    # ── Keigan's own Azure identity (shown to application teams for role grants) ──
    azure_identity_mode: AzureIdentityMode = AzureIdentityMode.NONE
    # Empty values are discovered from Keigan's own Azure token at runtime (tid, appid, oid); never ship placeholder GUIDs.
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    keigan_managed_identity_object_id: str = ""
    keigan_managed_identity_client_id: str = ""
    keigan_managed_identity_display_name: str = ""
    keigan_multi_tenant_app_client_id: str = ""

    # ── Integration modes ──────────────────────────────────────────────────────
    telemetry_mode: IntegrationMode = IntegrationMode.SIMULATED
    servicenow_mode: IntegrationMode = IntegrationMode.SIMULATED
    teams_mode: IntegrationMode = IntegrationMode.SIMULATED
    email_mode: EmailMode = EmailMode.SIMULATED

    # ── ServiceNow ─────────────────────────────────────────────────────────────
    servicenow_instance_url: str = ""
    servicenow_auth_method: str = "oauth"
    servicenow_client_id: str = ""
    servicenow_username: str = ""
    servicenow_credential_secret_name: str = "servicenow-credential"
    servicenow_poll_interval_seconds: int = 60

    # ── Microsoft Graph, Teams and email ───────────────────────────────────────
    graph_sender_mailbox: str = "keigan@metlife.example"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password_secret_name: str = "smtp-password"
    email_from_address: str = "keigan@metlife.example"
    teams_bot_app_id: str = ""
    teams_bot_app_secret_name: str = "teams-bot-secret"
    teams_app_catalog_id: str = ""
    # Comma-separated host patterns (* wildcard) a Teams activity "serviceUrl" must match before Keigan sends its bot token there.
    bot_framework_service_url_host_patterns: str = "*.botframework.com,smba.trafficmanager.net"
    teams_chat_poll_interval_minutes: int = 5
    teams_milestone_phrases: str = "keigan, this is finished|keigan this is finished|keigan, resolved|keigan resolved|keigan, incident closed|keigan, we are done"
    teams_unprompted_comment_minimum_interval_minutes: int = 15

    # ── AI / LLM ───────────────────────────────────────────────────────────────
    llm_provider: LlmProviderName = LlmProviderName.MOCK
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_api_version: str = "2024-10-21"
    llm_extra_headers_json: str = "{}"
    llm_use_managed_identity: bool = False
    llm_fast_model: str = "gemini-2.5-flash"
    llm_deep_model: str = "gemini-2.5-pro"
    llm_vision_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.1  # set to -1 for models that reject a temperature parameter
    llm_structured_output_method: str = "function_calling"  # function_calling | json_schema | json_mode
    llm_request_timeout_seconds: int = 120
    llm_maximum_retries: int = 3
    llm_max_concurrent_requests: int = 8
    llm_daily_token_budget_per_application: int = 3_000_000
    llm_price_per_million_input_tokens: float = 1.25
    llm_price_per_million_output_tokens: float = 10.0
    log_prompts_for_debugging: bool = False

    # ── Investigations ─────────────────────────────────────────────────────────
    investigation_lookback_minutes: int = 60
    investigation_max_window_minutes: int = 240
    investigation_max_concurrent: int = 3
    investigation_max_services: int = 6
    investigation_evidence_token_budget: int = 8_000
    investigation_knowledge_token_budget: int = 6_000
    auto_send_preliminary_report: bool = True

    # ── SLO and intelligence ───────────────────────────────────────────────────
    sli_collection_interval_minutes: int = 5
    slo_backfill_days: int = 30
    predictive_analysis_interval_minutes: int = 60
    intelligence_weekly_report_weekday: int = 0  # Monday
    intelligence_weekly_report_hour: int = 8

    # ── Storage and secrets ────────────────────────────────────────────────────
    file_storage_mode: str = "local"  # local | azure_blob
    azure_blob_account_url: str = ""
    azure_blob_container: str = "knowledge"
    secret_store_mode: str = "local_encrypted"  # local_encrypted | key_vault
    azure_key_vault_url: str = ""
    local_secret_encryption_key: str = ""
    max_upload_bytes: int = 15 * 1024 * 1024

    # ── Security ───────────────────────────────────────────────────────────────
    pii_masking_enabled: bool = True
    pii_mask_ip_addresses: str = "partial"  # none | partial | full
    alert_intake_max_payload_bytes: int = 256 * 1024
    alert_intake_rate_limit_per_minute: int = 3000
    chat_rate_limit_per_minute: int = 30
    max_request_body_bytes: int = 20 * 1024 * 1024

    # ── Retention ──────────────────────────────────────────────────────────────
    raw_alert_retention_days: int = 30
    incident_retention_days: int = 395
    sli_raw_retention_days: int = 90

    # ── Derived helpers ────────────────────────────────────────────────────────
    @field_validator("data_directory", mode="after")
    @classmethod
    def ensure_data_directory_exists(cls, data_directory: Path) -> Path:
        data_directory.mkdir(parents=True, exist_ok=True)
        (data_directory / "uploads").mkdir(parents=True, exist_ok=True)
        return data_directory

    @model_validator(mode="after")
    def validate_safe_combinations(self) -> "Settings":
        if self.environment == EnvironmentName.PROD:
            if not self.pii_masking_enabled:
                raise ValueError("PII_MASKING_ENABLED must be true when ENVIRONMENT=prod.")
            if self.llm_provider == LlmProviderName.MOCK:
                raise ValueError("LLM_PROVIDER=mock is not allowed when ENVIRONMENT=prod.")
        self._validate_authentication_and_secrets()
        if self.llm_provider in (LlmProviderName.GEMINI, LlmProviderName.OPENAI_COMPATIBLE) and not self.llm_api_key:
            if not (self.llm_provider == LlmProviderName.OPENAI_COMPATIBLE and self.llm_use_managed_identity):
                raise ValueError(f"LLM_PROVIDER={self.llm_provider} requires LLM_API_KEY.")
        return self

    def _validate_authentication_and_secrets(self) -> None:
        """Refuse to start with passwordless sign-in or publicly known secrets on a shared (dev, prod) deployment."""
        if self.auth_mode == AuthenticationMode.ENTRA:
            if not (self.entra_tenant_id and self.entra_api_client_id):
                raise ValueError("AUTH_MODE=entra requires ENTRA_TENANT_ID and ENTRA_API_CLIENT_ID.")
            if not self.entra_delegated_scope_name:
                raise ValueError("AUTH_MODE=entra requires ENTRA_API_SCOPE (for example api://<api-client-id>/access_as_user) or ENTRA_REQUIRED_DELEGATED_SCOPE.")
        if self.allows_local_authentication:
            return
        if self.auth_mode == AuthenticationMode.LOCAL:
            raise ValueError(
                "AUTH_MODE=local is only allowed when ENVIRONMENT is local or test, because anyone can sign in as any user. "
                f"Set AUTH_MODE=entra for ENVIRONMENT={self.environment}."
            )
        self._require_strong_secret("LOCAL_TOKEN_SIGNING_SECRET", self.local_token_signing_secret, DEFAULT_LOCAL_TOKEN_SIGNING_SECRET)
        if self.secret_store_mode == "local_encrypted":
            self._require_strong_secret("LOCAL_SECRET_ENCRYPTION_KEY", self.local_secret_encryption_key, "")

    def _require_strong_secret(self, variable_name: str, secret_value: str, known_default_value: str) -> None:
        if not secret_value or secret_value == known_default_value:
            raise ValueError(
                f"{variable_name} is not set or still has its default value, which is public. "
                f"Set {variable_name} to a random value of at least {self.secret_minimum_length} characters for ENVIRONMENT={self.environment}."
            )
        if len(secret_value) < self.secret_minimum_length:
            raise ValueError(f"{variable_name} must be at least {self.secret_minimum_length} characters long for ENVIRONMENT={self.environment}.")

    @property
    def allows_local_authentication(self) -> bool:
        """Local sign-in and default development secrets are for a developer machine and the test suite only."""
        return self.environment in LOCAL_AUTHENTICATION_ENVIRONMENTS

    @property
    def entra_delegated_scope_name(self) -> str:
        return self.entra_required_delegated_scope or self.entra_api_scope.rstrip("/").rsplit("/", 1)[-1]

    @property
    def entra_allowed_app_role_list(self) -> list[str]:
        return [role.strip() for role in self.entra_allowed_app_roles.split(",") if role.strip()]

    @property
    def bot_framework_service_url_host_pattern_list(self) -> list[str]:
        return [pattern.strip().lower() for pattern in self.bot_framework_service_url_host_patterns.split(",") if pattern.strip()]

    @property
    def is_local_environment(self) -> bool:
        return self.environment in (EnvironmentName.LOCAL, EnvironmentName.DEV)

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def llm_extra_headers(self) -> dict[str, str]:
        try:
            parsed_headers = json.loads(self.llm_extra_headers_json or "{}")
        except json.JSONDecodeError as decode_error:
            raise ValueError("LLM_EXTRA_HEADERS_JSON must be a JSON object.") from decode_error
        return {str(header_name): str(header_value) for header_name, header_value in parsed_headers.items()}

    @property
    def teams_milestone_phrase_list(self) -> list[str]:
        return [phrase.strip().lower() for phrase in self.teams_milestone_phrases.split("|") if phrase.strip()]

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def uses_sql_server(self) -> bool:
        return self.database_url.startswith("mssql")

    @property
    def database_schema_or_none(self) -> str | None:
        return None if self.uses_sqlite or not self.database_schema else self.database_schema

    def application_admin_group_name_for(self, application_code: str) -> str:
        return self.application_admin_group_pattern.format(application_code=application_code)

    def application_reader_group_name_for(self, application_code: str) -> str:
        return self.application_reader_group_pattern.format(application_code=application_code)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def safe_settings_for_display(settings: Settings) -> dict[str, object]:
    """Effective settings with secret values redacted (used by the administration page)."""
    secret_field_markers = ("secret", "api_key", "password", "signing", "encryption_key")
    displayed_settings: dict[str, object] = {}
    for field_name in Settings.model_fields:
        field_value = getattr(settings, field_name)
        if any(marker in field_name for marker in secret_field_markers):
            displayed_settings[field_name] = "•••• set" if field_value else "not set"
        else:
            displayed_settings[field_name] = str(field_value) if isinstance(field_value, Path) else field_value
    return displayed_settings


__all__ = [
    "DEFAULT_LOCAL_TOKEN_SIGNING_SECRET",
    "LOCAL_AUTHENTICATION_ENVIRONMENTS",
    "AuthenticationMode",
    "AzureIdentityMode",
    "EmailMode",
    "EnvironmentName",
    "IntegrationMode",
    "LlmProviderName",
    "RESOURCES_DIRECTORY",
    "Settings",
    "get_settings",
    "safe_settings_for_display",
]

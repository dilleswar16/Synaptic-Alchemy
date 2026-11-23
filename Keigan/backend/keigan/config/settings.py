"""Typed application settings (the Python equivalent of Spring's application.properties).

Every value is read from environment variables or ``backend/.env``. Nothing else in the code base reads
``os.environ`` directly: inject ``get_settings()`` instead.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from keigan.entities.status_values import StakeholderRole

BACKEND_ROOT_DIRECTORY = Path(__file__).resolve().parents[2]
RESOURCES_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
# Published in the repository, so it is a known value: it may only be used on a developer machine or in the test suite.
DEFAULT_LOCAL_TOKEN_SIGNING_SECRET = "local-development-only-change-me-0123456789abcdef"
# A running Ask Keigan answer refreshes its ``last_progress_at`` every ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS while a model turn or tool call is in flight, so a live run is
# never silent for longer than one beat (plus one database write, at most the driver's lock wait). It is called interrupted only after this many beats were missed.
STALE_RUN_MINIMUM_HEARTBEATS = 3


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


class ModelPrice(BaseModel):
    """What one AI model costs per million tokens (in whatever currency the operator chose; Keigan only multiplies)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)


def parse_model_prices(prices_json: str) -> dict[str, ModelPrice]:
    """The ``LLM_MODEL_PRICES_JSON`` mapping (model name to prices); empty text means no prices are configured."""
    if not prices_json.strip():
        return {}
    try:
        prices = TypeAdapter(dict[str, ModelPrice]).validate_json(prices_json)
    except ValidationError as validation_error:
        raise ValueError(f"LLM_MODEL_PRICES_JSON is not valid: {validation_error}") from validation_error
    if any(not model_name.strip() for model_name in prices):
        raise ValueError("LLM_MODEL_PRICES_JSON needs a model name as every key.")
    return prices


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
    llm_managed_identity_scope: str = Field(default="https://cognitiveservices.azure.com/.default", min_length=1)  # token scope for azure_openai and openai_compatible
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
    log_prompts_for_debugging: bool = False  # prompts hold customer telemetry: only accepted when ENVIRONMENT=local

    # ── Investigations ─────────────────────────────────────────────────────────
    investigation_lookback_minutes: int = 60
    investigation_max_window_minutes: int = 240
    investigation_max_concurrent: int = Field(default=3, ge=1)  # across all worker pods; more investigations wait in the queue
    investigation_max_services: int = 6
    investigation_supported_minimum_confidence: float = Field(default=0.5, ge=0.0, le=1.0)  # lowest confidence a supported hypothesis may have (the prompt's "strongly suggests" band)
    investigation_ruled_out_maximum_confidence: float = Field(default=0.2, ge=0.0, le=1.0)  # highest confidence a ruled-out hypothesis may have (the "unlikely" band)
    investigation_trace_raw_output_stored_characters: int = Field(default=20_000, ge=1000, le=200_000)  # characters of one AI call's raw answer kept in the decision trace
    action_items_maximum_per_postmortem: int = Field(default=8, ge=1, le=20)  # most action items the AI may propose for one postmortem (also told to the model)
    action_items_maximum_due_days: int = Field(default=180, ge=7, le=730)  # latest due date, in days from today (and the clamp on the AI's suggested days)
    action_items_details_maximum_characters: int = Field(default=4000, ge=200, le=20_000)
    action_items_reason_minimum_characters: int = Field(default=10, ge=1, le=200)  # shortest reason for blocked and won't do
    suggested_fix_maximum_command_characters: int = Field(default=600, ge=80, le=4000)  # longest suggested command shown as copyable; longer is withheld
    runbook_health_unused_after_days: int = Field(default=60, ge=7, le=730)  # a runbook never used after this many days is flagged
    runbook_health_stale_after_days: int = Field(default=180, ge=30, le=1095)  # a runbook not updated for this many days is flagged
    runbook_health_minimum_rated_investigations: int = Field(default=3, ge=1, le=50)  # fewest rated investigations before a runbook can be called often wrong
    runbook_health_wrong_share_percent: float = Field(default=50.0, ge=10, le=100)  # share of rated investigations rated incorrect that flags a runbook
    weekly_review_maximum_listed_items: int = Field(default=10, ge=1, le=50)  # most overdue and unowned action items listed in the weekly review
    error_budget_policy_single_incident_threshold_percent: float = Field(default=20.0, ge=1, le=100)  # one incident using more than this share of an SLO's budget needs a postmortem with a top-priority item
    error_budget_policy_outage_class_threshold_percent: float = Field(default=20.0, ge=1, le=100)  # one class of outage using more than this share of an SLO's budget over the class window
    error_budget_policy_outage_class_window_days: int = Field(default=90, ge=7)  # the class window ("a quarter"); at most SLI_RAW_RETENTION_DAYS
    error_budget_policy_evaluation_interval_minutes: int = Field(default=60, ge=5, le=1440)  # how often impacts and breaches are re-evaluated
    error_budget_policy_final_after_hours: int = Field(default=24, ge=1, le=168)  # hours after resolution when an incident's budget figure becomes final
    error_budget_policy_minimum_data_coverage_percent: float = Field(default=50.0, ge=10, le=100)  # least share of the budget window that must have measurements
    error_budget_policy_minimum_window_events: int = Field(default=1000, ge=0, le=1_000_000_000)  # fewest events in the budget window for a share to be stated
    error_budget_policy_auto_draft_postmortem: bool = True  # start a postmortem draft when a breach is found on a resolved incident
    error_budget_policy_waiver_minimum_characters: int = Field(default=20, ge=5, le=500)  # shortest reason for waiving a requirement
    error_budget_policy_guidance_maximum_characters: int = Field(default=2000, ge=100, le=10_000)  # longest text of what a team does when a budget is used up
    error_budget_policy_notification_roles: str = "lead"  # team roles (comma separated) told about breaches in addition to subscribers
    error_budget_policy_breach_retention_days: int = Field(default=730, ge=90, le=3650)  # closed breaches older than this are deleted
    action_items_reminders_enabled: bool = True  # master switch for reminder and escalation emails
    action_items_reminder_hour_local: int = Field(default=9, ge=0, le=23)  # hour, in the application's time zone, at which the daily reminder job runs
    action_items_reminder_days_before_due: int = Field(default=2, ge=0, le=14)  # days before the due date of the due-soon reminder (0 = none)
    action_items_overdue_reminder_interval_days: int = Field(default=7, ge=1, le=30)  # days between reminders for one overdue item
    action_items_escalate_after_overdue_days: int = Field(default=14, ge=1, le=90)  # days overdue after which top and high items go to the escalation roles
    action_items_escalation_roles: str = "lead,manager"  # team roles (comma separated) that receive escalations and items nobody owns
    action_items_closed_retention_days: int = Field(default=730, ge=90, le=3650)  # closed action items older than this are deleted
    action_items_external_reference_pattern: str = r"^[A-Z]{2,10}[0-9]{4,12}$"  # accepted shape of a typed ServiceNow task number
    investigation_max_checks_per_service: int = Field(default=7, ge=1, le=30)  # evidence checks one service gets in an investigation; a cut is reported as a gap
    investigation_evidence_token_budget: int = 8_000
    investigation_knowledge_token_budget: int = 6_000
    auto_send_preliminary_report: bool = True

    # ── Application teams ──────────────────────────────────────────────────────
    team_members_maximum_per_application: int = Field(default=100, ge=1)
    team_invitation_resend_cooldown_minutes: int = Field(default=15, ge=1)  # one invitation email per person per this many minutes
    team_invitation_stale_after_days: int = Field(default=14, ge=1)  # an invitation this old with no sign-in is shown as stale
    # The longest operating notes (the team's guidance for the AI) an application may have, counted after trimming. The database column is NVARCHAR(max),
    # so every value up to the upper bound fits; the AI prompt also takes the whole text.
    application_operating_notes_maximum_characters: int = Field(default=4000, ge=100, le=20_000)

    # ── SLO and intelligence ───────────────────────────────────────────────────
    sli_collection_interval_minutes: int = 5
    slo_backfill_days: int = 30
    slo_supporting_signal_backfill_days: int = 7
    predictive_analysis_interval_minutes: int = 60
    intelligence_weekly_report_weekday: int = 0  # Monday
    intelligence_weekly_report_hour: int = 8

    # ── Reliability metrics page ───────────────────────────────────────────────
    # Fewest rated investigations before a "share marked correct" percentage is shown (below it the page says there are not enough ratings yet).
    metrics_minimum_rating_sample: int = Field(default=5, ge=1)
    # Longest period (days) one request may ask for.
    metrics_maximum_window_days: int = Field(default=365, ge=1)
    # Per-model prices for an estimated cost, as JSON: {"model-name": {"input_per_million": 1.25, "output_per_million": 10}}. Empty: the page shows tokens only.
    llm_model_prices_json: str = ""

    # ── Ask Keigan ─────────────────────────────────────────────────────────────
    # How much Keigan does for one question is limited by the number of tool calls (there is no time limit on an answer) and by the token budget.
    ask_keigan_max_tool_calls_global: int = Field(default=8, ge=1, le=50)
    ask_keigan_max_tool_calls_investigation: int = Field(default=6, ge=1, le=50)
    ask_keigan_max_parallel_tool_calls: int = Field(default=3, ge=1, le=5)  # requests executed from one model turn; the rest are skipped
    ask_keigan_tool_timeout_seconds: int = Field(default=60, ge=5, le=600)  # per tool call; stops one hung call, never a long answer
    ask_keigan_stale_run_seconds: int = Field(default=300, ge=60, le=3600)  # silence after which a running answer counts as interrupted
    ask_keigan_progress_heartbeat_seconds: int = Field(default=15, ge=5, le=300)  # how often a live answer refreshes its last_progress_at; the stale limit must be at least 3 beats
    ask_keigan_answer_token_budget: int = Field(default=80_000, ge=5000, le=1_000_000)  # input plus output tokens across all turns of one answer
    ask_keigan_tool_output_model_characters: int = Field(default=6000, ge=500, le=50_000)  # characters of one tool result sent to the model
    ask_keigan_tool_output_stored_characters: int = Field(default=60_000, ge=1000, le=1_000_000)  # characters of one tool output stored as "full output"
    ask_keigan_tool_output_preview_characters: int = Field(default=1500, ge=200, le=10_000)  # characters of output sent live to the browser
    ask_keigan_tool_list_item_limit: int = Field(default=20, ge=1, le=200)  # items a list tool returns
    ask_keigan_tool_series_point_limit: int = Field(default=100, ge=10, le=1000)  # points a series tool returns; the bucket width grows to keep them within it
    ask_keigan_tool_passage_characters: int = Field(default=2400, ge=200, le=20_000)  # characters of one passage (a runbook's steps) a tool returns
    ask_keigan_log_query_max_lookback_minutes: int = Field(default=43_200, ge=5, le=43_200)
    ask_keigan_knowledge_token_budget: int = Field(default=2500, ge=500, le=20_000)
    ask_keigan_heartbeat_seconds: int = Field(default=15, ge=5, le=60)  # keep-alive interval of the answer stream
    ask_keigan_protocol_repair_attempts: int = Field(default=1, ge=0, le=2)  # repair retries per turn for models without native tool calling
    ask_keigan_follow_up_question_limit: int = Field(default=3, ge=0, le=5)
    ask_keigan_event_queue_size: int = Field(default=1000, ge=100, le=100_000)  # events one answer may hold for a slow reader before the stream is dropped (the stored trace stays)
    ask_keigan_shutdown_grace_seconds: int = Field(default=10, ge=1, le=120)  # how long a stopping process waits for its cancelled answers to end before it marks their runs interrupted
    # How much of an investigation the digest in front of the model holds: newest timeline events, topology node names, and characters of each evidence summary.
    ask_keigan_digest_timeline_events: int = Field(default=15, ge=0, le=100)
    ask_keigan_digest_topology_nodes: int = Field(default=40, ge=0, le=500)
    ask_keigan_digest_evidence_summary_characters: int = Field(default=300, ge=50, le=2000)
    # Stored steps and runs of global conversations older than this many days are purged (the conversation stays). Empty: keep everything.
    ask_keigan_trace_retention_days: int | None = Field(default=None, ge=30, le=3650)
    ask_keigan_conformance_report_path: Path = Path("ask_keigan_conformance_report.json")  # where the conformance script writes its report and the administration page reads the last one
    # Overrides of resources/catalogs/llm_model_capabilities.yaml (same shape), as JSON. Empty object: the catalog as shipped.
    llm_model_capabilities_json: str = "{}"

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
    @field_validator("llm_model_prices_json", mode="after")
    @classmethod
    def model_prices_must_be_valid(cls, prices_json: str) -> str:
        parse_model_prices(prices_json)
        return prices_json

    @field_validator("error_budget_policy_notification_roles", mode="after")
    @classmethod
    def notification_roles_must_be_team_roles(cls, roles: str) -> str:
        unknown = [role for role in (part.strip() for part in roles.split(",")) if role and role not in {member.value for member in StakeholderRole}]
        if unknown:
            raise ValueError(f"ERROR_BUDGET_POLICY_NOTIFICATION_ROLES has unknown team roles: {', '.join(unknown)}")
        return roles

    @field_validator("action_items_escalation_roles", mode="after")
    @classmethod
    def escalation_roles_must_be_team_roles(cls, roles: str) -> str:
        unknown = [role for role in (part.strip() for part in roles.split(",")) if role and role not in {member.value for member in StakeholderRole}]
        if unknown:
            raise ValueError(f"ACTION_ITEMS_ESCALATION_ROLES has unknown team roles: {', '.join(unknown)}")
        return roles

    @field_validator("action_items_external_reference_pattern", mode="after")
    @classmethod
    def external_reference_pattern_must_be_a_regular_expression(cls, pattern: str) -> str:
        try:
            re.compile(pattern)
        except re.error as invalid:
            raise ValueError(f"ACTION_ITEMS_EXTERNAL_REFERENCE_PATTERN is not a valid regular expression: {invalid}") from invalid
        return pattern

    @field_validator("ask_keigan_trace_retention_days", mode="before")
    @classmethod
    def empty_trace_retention_means_keep_everything(cls, retention_days: object) -> object:
        return None if isinstance(retention_days, str) and not retention_days.strip() else retention_days

    @field_validator("llm_model_capabilities_json", mode="after")
    @classmethod
    def model_capability_overrides_must_be_valid(cls, overrides_json: str) -> str:
        from keigan.ai.model_capabilities import parse_capability_overrides  # imported here: that module reads this one at import time

        parse_capability_overrides(overrides_json)
        return overrides_json

    @field_validator("data_directory", mode="after")
    @classmethod
    def ensure_data_directory_exists(cls, data_directory: Path) -> Path:
        data_directory.mkdir(parents=True, exist_ok=True)
        (data_directory / "uploads").mkdir(parents=True, exist_ok=True)
        return data_directory

    @model_validator(mode="after")
    def validate_safe_combinations(self) -> "Settings":
        if self.error_budget_policy_outage_class_window_days > self.sli_raw_retention_days:
            raise ValueError("ERROR_BUDGET_POLICY_OUTAGE_CLASS_WINDOW_DAYS cannot exceed SLI_RAW_RETENTION_DAYS: the class rule reads the raw SLI measurements, which expire after that many days.")
        if self.environment == EnvironmentName.PROD:
            if not self.pii_masking_enabled:
                raise ValueError("PII_MASKING_ENABLED must be true when ENVIRONMENT=prod.")
            if self.llm_provider == LlmProviderName.MOCK:
                raise ValueError("LLM_PROVIDER=mock is not allowed when ENVIRONMENT=prod.")
        self._validate_authentication_and_secrets()
        if self.investigation_ruled_out_maximum_confidence >= self.investigation_supported_minimum_confidence:
            raise ValueError(
                f"INVESTIGATION_RULED_OUT_MAXIMUM_CONFIDENCE ({self.investigation_ruled_out_maximum_confidence}) must be below INVESTIGATION_SUPPORTED_MINIMUM_CONFIDENCE "
                f"({self.investigation_supported_minimum_confidence}): a hypothesis cannot be both supported and ruled out."
            )
        if self.ask_keigan_tool_output_preview_characters > self.ask_keigan_tool_output_stored_characters:
            raise ValueError("ASK_KEIGAN_TOOL_OUTPUT_PREVIEW_CHARACTERS must not be larger than ASK_KEIGAN_TOOL_OUTPUT_STORED_CHARACTERS.")
        if self.ask_keigan_tool_output_model_characters > self.ask_keigan_tool_output_stored_characters:
            raise ValueError("ASK_KEIGAN_TOOL_OUTPUT_MODEL_CHARACTERS must not be larger than ASK_KEIGAN_TOOL_OUTPUT_STORED_CHARACTERS.")
        if self.ask_keigan_stale_run_seconds < STALE_RUN_MINIMUM_HEARTBEATS * self.ask_keigan_progress_heartbeat_seconds:
            raise ValueError(
                f"ASK_KEIGAN_STALE_RUN_SECONDS ({self.ask_keigan_stale_run_seconds}) must be at least {STALE_RUN_MINIMUM_HEARTBEATS} times ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS "
                f"({self.ask_keigan_progress_heartbeat_seconds}): a live answer refreshes its progress once per heartbeat, and a run is only called interrupted after several missed beats."
            )
        if self.log_prompts_for_debugging and self.environment != EnvironmentName.LOCAL:
            raise ValueError(f"LOG_PROMPTS_FOR_DEBUGGING writes customer telemetry into the log, so it is only allowed when ENVIRONMENT=local, not {self.environment}.")
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
    def error_budget_policy_notification_role_list(self) -> list[str]:
        return [role.strip() for role in self.error_budget_policy_notification_roles.split(",") if role.strip()]

    @property
    def action_items_escalation_role_list(self) -> list[str]:
        return [role.strip() for role in self.action_items_escalation_roles.split(",") if role.strip()]

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
    def llm_model_prices(self) -> dict[str, ModelPrice]:
        return parse_model_prices(self.llm_model_prices_json)

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


_URL_USER_INFORMATION = re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)[^/\s@]+@", re.IGNORECASE)
_KEY_VALUE_CREDENTIAL = re.compile(r"(?P<name>\b(?:password|pwd|accountkey|sharedaccesskey|sharedaccesssignature)\s*=\s*)[^;\s]+", re.IGNORECASE)


def redact_credentials(text: str) -> str:
    """A connection string or URL with its password removed; the host and database stay, because an administrator needs them."""
    without_user_information = _URL_USER_INFORMATION.sub(lambda match: f"{match.group('scheme')}••••@", text)
    return _KEY_VALUE_CREDENTIAL.sub(lambda match: f"{match.group('name')}••••", without_user_information)


def safe_settings_for_display(settings: Settings) -> dict[str, object]:
    """Effective settings with secret values redacted (used by the administration page)."""
    secret_field_markers = ("secret", "api_key", "password", "signing", "encryption_key", "token", "credential", "headers")
    displayed_settings: dict[str, object] = {}
    for field_name in Settings.model_fields:
        field_value = getattr(settings, field_name)
        if any(marker in field_name for marker in secret_field_markers) and not isinstance(field_value, bool | int | float):  # a number or a flag cannot be a credential, so a token budget stays readable
            displayed_settings[field_name] = "•••• set" if field_value else "not set"
        elif isinstance(field_value, str):
            displayed_settings[field_name] = redact_credentials(field_value)
        else:
            displayed_settings[field_name] = str(field_value) if isinstance(field_value, Path) else field_value
    return displayed_settings


__all__ = [
    "DEFAULT_LOCAL_TOKEN_SIGNING_SECRET",
    "LOCAL_AUTHENTICATION_ENVIRONMENTS",
    "STALE_RUN_MINIMUM_HEARTBEATS",
    "AuthenticationMode",
    "AzureIdentityMode",
    "EmailMode",
    "EnvironmentName",
    "IntegrationMode",
    "LlmProviderName",
    "ModelPrice",
    "RESOURCES_DIRECTORY",
    "Settings",
    "get_settings",
    "redact_credentials",
    "safe_settings_for_display",
]

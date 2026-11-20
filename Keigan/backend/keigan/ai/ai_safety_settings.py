"""Settings for prompt safety and AI output safety, read from the same environment and ``backend/.env`` as the main settings.

Kept beside the code that uses them so the prompt-safety rules (link allow-list, flagged-document policy, per-user
token budget, organisation name) can be tuned without touching the platform-wide settings module.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from keigan.config.settings import BACKEND_ROOT_DIRECTORY, get_settings


class FlaggedDocumentPolicy(StrEnum):
    """What to do with an uploaded document whose text looks like a prompt-injection attempt."""

    WARN = "warn"  # keep it, but mark its prompt block with an injection warning
    EXCLUDE = "exclude"  # never put it into a prompt


class AiSafetySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT_DIRECTORY / ".env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # Hosts that AI-written text may link to (exact host match). ``*.example.com`` explicitly allows sub-domains.
    # The hosts of SERVICENOW_INSTANCE_URL, FRONTEND_BASE_URL and PUBLIC_BASE_URL are always allowed in addition.
    # No public code-hosting sites by default: their content is attacker-controlled.
    ai_output_allowed_link_hosts: str = "portal.azure.com,learn.microsoft.com"
    # Name of the organisation Keigan works for, rendered into prompts. Empty means the prompts do not name one.
    organization_name: str = ""
    ai_flagged_document_policy: FlaggedDocumentPolicy = FlaggedDocumentPolicy.WARN
    # Daily token budget of one user for AI calls that belong to no single application (chat across several applications).
    llm_daily_token_budget_per_user: int = 500_000
    # Maximum number of earlier chat turns passed to the model, and the characters kept of each turn.
    chat_history_turn_limit: int = 8
    chat_history_turn_characters: int = 800

    @field_validator("ai_output_allowed_link_hosts")
    @classmethod
    def _normalise_host_list(cls, host_list: str) -> str:
        return ",".join(host.strip().lower() for host in host_list.split(",") if host.strip())

    @property
    def allowed_link_hosts(self) -> frozenset[str]:
        """Configured hosts plus the hosts of Keigan's own integrations (ServiceNow, frontend, API)."""
        main_settings = get_settings()
        configured_hosts = {host for host in self.ai_output_allowed_link_hosts.split(",") if host}
        for own_url in (main_settings.servicenow_instance_url, main_settings.frontend_base_url, main_settings.public_base_url):
            own_host = (urlsplit(own_url).hostname or "").lower() if own_url else ""
            if own_host:
                configured_hosts.add(own_host)
        return frozenset(configured_hosts)


@lru_cache
def get_ai_safety_settings() -> AiSafetySettings:
    return AiSafetySettings()

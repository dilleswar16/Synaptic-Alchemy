"""Settings of the telemetry access rules and the outbound URL policy (V2, V16).

Read from environment variables or ``backend/.env`` exactly like :mod:`keigan.config.settings`; kept in their own class so the
access rules stay in one place. Every key is documented in ``backend/.env.example``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from keigan.config.settings import BACKEND_ROOT_DIRECTORY


def _split_list(comma_separated_values: str) -> tuple[str, ...]:
    return tuple(value.strip().lower() for value in comma_separated_values.split(",") if value.strip())


class TelemetryAccessSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT_DIRECTORY / ".env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # Internal hosts Keigan may call although they resolve to private addresses (for example an on-premises Splunk).
    # Comma separated; "splunk.corp.example.com" matches that host, ".corp.example.com" matches its sub-domains.
    outbound_allowed_hosts: str = ""
    # Host names that are always refused, even when listed above (cluster DNS, loopback, cloud metadata).
    outbound_denied_host_suffixes: str = "localhost,.localhost,.local,.internal,.svc,.cluster.local"
    # How long a Log Analytics workspace id looked up in Azure is trusted before it is looked up again.
    workspace_identity_cache_seconds: int = 900

    @property
    def outbound_allowed_host_list(self) -> tuple[str, ...]:
        return _split_list(self.outbound_allowed_hosts)

    @property
    def outbound_denied_host_suffix_list(self) -> tuple[str, ...]:
        return _split_list(self.outbound_denied_host_suffixes)


@lru_cache
def get_telemetry_access_settings() -> TelemetryAccessSettings:
    return TelemetryAccessSettings()

"""The URLs Keigan will call for a log tool connection, so the outbound URL policy can check exactly those (finding V16).

Elastic, Splunk and the other tools use ``endpoint_url``. Datadog derives its host from the ``site`` setting
(``https://api.<site>``, see ``DatadogClient``), so the site is a URL in disguise and is checked as one.
"""

from __future__ import annotations

from typing import Any

DEFAULT_DATADOG_SITE = "datadoghq.com"
ENDPOINT_URL_FIELD = "endpointUrl"
DATADOG_SITE_FIELD = "connectionConfiguration.site"


def log_tool_endpoint_urls(tool_type: str, endpoint_url: str | None, connection_configuration: dict[str, Any] | None) -> list[tuple[str, str]]:
    """``(form field, URL)`` for every address the connection makes Keigan call."""
    endpoints: list[tuple[str, str]] = []
    if endpoint_url:
        endpoints.append((ENDPOINT_URL_FIELD, endpoint_url))
    if tool_type == "datadog":
        site = str((connection_configuration or {}).get("site") or DEFAULT_DATADOG_SITE)
        endpoints.append((DATADOG_SITE_FIELD, f"https://api.{site}"))
    return endpoints


def log_tool_endpoint_signature(tool_type: str, endpoint_url: str | None, connection_configuration: dict[str, Any] | None, authentication_method: str | None) -> tuple:
    """Everything that decides where the stored credential is sent. When it changes the credential must be entered again."""
    return (
        tuple(url.lower() for _field, url in log_tool_endpoint_urls(tool_type, endpoint_url, connection_configuration)),
        (authentication_method or "").lower(),
    )

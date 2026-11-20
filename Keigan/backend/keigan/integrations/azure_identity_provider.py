"""Access tokens for Keigan's own Azure identity (managed / workload identity in AKS, client secret or CLI locally)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from azure.identity.aio import (
    AzureCliCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
    WorkloadIdentityCredential,
)

from keigan.config.settings import AzureIdentityMode, Settings
from keigan.exceptions.keigan_exceptions import IntegrationException

TOKEN_REFRESH_MARGIN_SECONDS = 300
RESOURCE_MANAGER_SCOPE = "https://management.azure.com/.default"
logger = logging.getLogger(__name__)
IDENTITY_RETRY_SECONDS = 300


@dataclass(frozen=True)
class KeiganIdentity:
    """The principal application teams grant Reader roles to (shown on the onboarding "Grant access" step)."""

    tenant_id: str | None
    client_id: str | None
    object_id: str | None
    display_name: str | None
    source: str  # settings | discovered | not_configured
    missing_values: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_values


def _read_token_claims(access_token: str) -> dict[str, Any]:
    """Claims of Keigan's own access token. Only read for identification (oid, tid, appid), never trusted for authorization."""
    payload_segment = access_token.split(".")[1]
    padded_segment = payload_segment + "=" * (-len(payload_segment) % 4)
    return dict(json.loads(base64.urlsafe_b64decode(padded_segment)))


def _configured_value(value: str | None) -> str | None:
    """Treats an unedited template value such as ``<managed-identity-object-id>`` as not configured."""
    cleaned_value = (value or "").strip()
    return None if not cleaned_value or cleaned_value.startswith("<") else cleaned_value


class AzureCredentialProvider:
    """Caches one credential per tenant and access tokens per (tenant, scope)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._credentials_by_tenant: dict[str, object] = {}
        self._tokens_by_key: dict[tuple[str, str], tuple[str, float]] = {}
        self._lock = asyncio.Lock()
        self._resolved_identity: KeiganIdentity | None = None
        self._identity_resolved_at = 0.0

    @property
    def is_configured(self) -> bool:
        return self.settings.azure_identity_mode != AzureIdentityMode.NONE

    def _create_credential(self, tenant_id: str) -> object:
        identity_mode = self.settings.azure_identity_mode
        if identity_mode == AzureIdentityMode.MANAGED_IDENTITY:
            return ManagedIdentityCredential(client_id=self.settings.azure_client_id or None)
        if identity_mode == AzureIdentityMode.WORKLOAD_IDENTITY:
            return WorkloadIdentityCredential(tenant_id=tenant_id or None, client_id=self.settings.azure_client_id or None)
        if identity_mode == AzureIdentityMode.CLIENT_SECRET:
            if not tenant_id:
                raise IntegrationException("AZURE_IDENTITY_MODE=client_secret needs AZURE_TENANT_ID.")
            return ClientSecretCredential(tenant_id, self.settings.azure_client_id, self.settings.azure_client_secret)
        if identity_mode == AzureIdentityMode.AZURE_CLI:
            return AzureCliCredential(tenant_id=tenant_id or None)
        raise IntegrationException("Keigan's Azure identity is not configured (AZURE_IDENTITY_MODE=none).")

    async def get_access_token(self, scope: str, tenant_id: str | None = None) -> str:
        effective_tenant_id = tenant_id or self.settings.azure_tenant_id
        cache_key = (effective_tenant_id, scope)
        cached_token = self._tokens_by_key.get(cache_key)
        if cached_token and cached_token[1] - time.time() > TOKEN_REFRESH_MARGIN_SECONDS:
            return cached_token[0]
        async with self._lock:
            credential = self._credentials_by_tenant.get(effective_tenant_id)
            if credential is None:
                credential = self._create_credential(effective_tenant_id)
                self._credentials_by_tenant[effective_tenant_id] = credential
            try:
                access_token = await credential.get_token(scope)  # type: ignore[attr-defined]
            except Exception as credential_error:  # noqa: BLE001
                raise IntegrationException(f"Could not obtain an Azure access token for {scope}: {credential_error}") from credential_error
            self._tokens_by_key[cache_key] = (access_token.token, float(access_token.expires_on))
            return access_token.token

    async def resolve_keigan_identity(self) -> KeiganIdentity:
        """Keigan's own principal: configured values first; gaps filled from its own Azure token (tid, appid, oid claims).

        No extra permission is needed. A complete result is cached for the life of the process; an incomplete one is retried
        after five minutes (for example while the workload identity is still being federated)."""
        if self._resolved_identity and (self._resolved_identity.is_complete or time.monotonic() - self._identity_resolved_at < IDENTITY_RETRY_SECONDS):
            return self._resolved_identity
        tenant_id = _configured_value(self.settings.azure_tenant_id)
        client_id = _configured_value(self.settings.keigan_managed_identity_client_id) or _configured_value(self.settings.azure_client_id)
        object_id = _configured_value(self.settings.keigan_managed_identity_object_id)
        source = "settings"
        if self.is_configured and not (tenant_id and client_id and object_id):
            try:
                token_claims = _read_token_claims(await self.get_access_token(RESOURCE_MANAGER_SCOPE))
                tenant_id = tenant_id or token_claims.get("tid")
                client_id = client_id or token_claims.get("appid") or token_claims.get("azp")
                object_id = object_id or token_claims.get("oid")
                source = "discovered"
            except Exception as discovery_error:  # noqa: BLE001 — shown to admins as "not configured"
                logger.warning("Could not discover Keigan's identity from its access token: %s", discovery_error)
        missing_values = tuple(name for name, value in (("tenantId", tenant_id), ("clientId", client_id), ("objectId", object_id)) if not value)
        if missing_values and not (tenant_id or client_id or object_id):
            source = "not_configured"
        self._resolved_identity = KeiganIdentity(
            tenant_id=tenant_id, client_id=client_id, object_id=object_id,
            display_name=self.settings.keigan_managed_identity_display_name or None, source=source, missing_values=missing_values,
        )
        self._identity_resolved_at = time.monotonic()
        return self._resolved_identity

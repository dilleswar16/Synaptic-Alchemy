"""Runtime connector registry — resolves credentials and instantiates connectors from DB rows."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from corvin.connectors.base import BaseConnector
from corvin.connectors.azure_monitor import AzureMonitorConnector
from corvin.connectors.elastic import ElasticConnector
from corvin.connectors.byoa import ByoaConnector

if TYPE_CHECKING:
    from corvin.storage.models import LogSourceRow

_log = logging.getLogger(__name__)

_SOURCE_TYPE_MAP: dict[str, type[BaseConnector]] = {
    "azure_monitor": AzureMonitorConnector,
    "elastic": ElasticConnector,
    "byoa": ByoaConnector,
}


class ConnectorRegistry:
    """Instantiates the correct connector for a LogSourceRow, resolving credentials at runtime."""

    def get_connector(self, source: "LogSourceRow") -> BaseConnector | None:
        cls = _SOURCE_TYPE_MAP.get(source.source_type)
        if cls is None:
            _log.warning("ConnectorRegistry: unknown source_type=%r", source.source_type)
            return None
        credential = self._resolve_credential(source)
        return cls(config=source.config_json, credential_value=credential)

    def _resolve_credential(self, source: "LogSourceRow") -> str | None:
        if not source.credential_ref:
            return None
        ctype = source.credential_type
        if ctype == "env_var":
            return os.environ.get(source.credential_ref)
        if ctype == "kv_reference":
            return self._fetch_from_keyvault(source.credential_ref)
        if ctype == "db_encrypted":
            return self._decrypt(source.credential_ref)
        return None

    @staticmethod
    def _fetch_from_keyvault(secret_spec: str) -> str | None:
        """
        secret_spec format: "vault_url|secret_name"
        e.g. "https://my-vault.vault.azure.net|my-elastic-key"
        """
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            if "|" not in secret_spec:
                _log.warning("ConnectorRegistry: KV secret_spec must be 'vault_url|secret_name'")
                return None
            vault_url, secret_name = secret_spec.split("|", 1)
            client = SecretClient(vault_url=vault_url.strip(), credential=DefaultAzureCredential())
            return client.get_secret(secret_name.strip()).value
        except Exception as exc:
            _log.warning("ConnectorRegistry: Key Vault fetch failed: %s", exc)
            return None

    @staticmethod
    def _decrypt(ciphertext: str) -> str | None:
        try:
            from corvin.connectors.crypto import decrypt
            return decrypt(ciphertext)
        except Exception as exc:
            _log.warning("ConnectorRegistry: credential decryption failed: %s", exc)
            return None

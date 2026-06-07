"""Secret reference resolution for DB-stored integration configs."""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def resolve_secret_reference(ref: str | None) -> str | None:
    """Resolve a secret reference to a concrete value.

    Supported formats:
      - env:VAR_NAME
      - kv:https://<vault>.vault.azure.net|secret-name
      - VAR_NAME (treated as env var name)

    Returns None when the value cannot be resolved.
    """
    if not ref:
        return None
    raw = str(ref).strip()
    if not raw:
        return None

    if raw.startswith("env:"):
        env_name = raw[4:].strip()
        return os.environ.get(env_name) if env_name else None

    if raw.startswith("kv:"):
        spec = raw[3:].strip()
        if "|" not in spec:
            _log.warning("Secret reference kv: must use format kv:vault_url|secret_name")
            return None
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            vault_url, secret_name = spec.split("|", 1)
            client = SecretClient(vault_url=vault_url.strip(), credential=DefaultAzureCredential())
            return client.get_secret(secret_name.strip()).value
        except Exception as exc:  # noqa: BLE001
            _log.warning("Secret reference kv: resolution failed: %s", exc)
            return None

    # Backward-compatible fallback: plain env var name.
    return os.environ.get(raw)

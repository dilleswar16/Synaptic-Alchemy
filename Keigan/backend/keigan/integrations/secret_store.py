"""Secret storage behind one interface: Azure Key Vault in Azure, a Fernet-encrypted table locally.

The database and the API only ever carry secret *names*. Values are written once and read only by integrations.
"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime

import httpx
from cryptography.fernet import Fernet, InvalidToken

from keigan.config.database_config import open_session
from keigan.config.settings import Settings
from keigan.entities.platform_entities import StoredSecret
from keigan.exceptions.keigan_exceptions import IntegrationException, NotFoundException
from keigan.integrations.azure_identity_provider import AzureCredentialProvider

KEY_VAULT_SCOPE = "https://vault.azure.net/.default"
KEY_VAULT_API_VERSION = "7.4"


def build_secret_name(purpose: str) -> str:
    """Key Vault compatible, unique, descriptive secret name, e.g. ``logtool-elastic-3f2a9c1b``."""
    sanitized_purpose = re.sub(r"[^a-zA-Z0-9-]", "-", purpose).strip("-").lower()[:80]
    return f"{sanitized_purpose}-{uuid.uuid4().hex[:8]}"


class SecretStore(ABC):
    @abstractmethod
    async def set_secret(self, secret_name: str, secret_value: str, description: str | None = None) -> None: ...

    @abstractmethod
    async def get_secret(self, secret_name: str) -> str: ...

    @abstractmethod
    async def delete_secret(self, secret_name: str) -> None: ...

    async def get_secret_or_none(self, secret_name: str | None) -> str | None:
        if not secret_name:
            return None
        try:
            return await self.get_secret(secret_name)
        except NotFoundException:
            return None


class LocalEncryptedSecretStore(SecretStore):
    def __init__(self, encryption_key_material: str):
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(encryption_key_material.encode("utf-8")).digest())
        self._fernet = Fernet(derived_key)

    async def set_secret(self, secret_name: str, secret_value: str, description: str | None = None) -> None:
        encrypted_value = self._fernet.encrypt(secret_value.encode("utf-8")).decode("ascii")
        async with open_session() as session:
            stored_secret = await session.get(StoredSecret, secret_name)
            if stored_secret is None:
                session.add(StoredSecret(secret_name=secret_name, encrypted_secret_value=encrypted_value, secret_description=description))
            else:
                stored_secret.encrypted_secret_value = encrypted_value
                stored_secret.last_rotated_at = datetime.now(UTC)

    async def get_secret(self, secret_name: str) -> str:
        async with open_session() as session:
            stored_secret = await session.get(StoredSecret, secret_name)
        if stored_secret is None or not stored_secret.encrypted_secret_value:
            raise NotFoundException(f"Secret {secret_name} is not set.")
        try:
            return self._fernet.decrypt(stored_secret.encrypted_secret_value.encode("ascii")).decode("utf-8")
        except InvalidToken as decryption_error:
            raise IntegrationException("A stored secret could not be decrypted (encryption key changed?).") from decryption_error

    async def delete_secret(self, secret_name: str) -> None:
        async with open_session() as session:
            stored_secret = await session.get(StoredSecret, secret_name)
            if stored_secret is not None:
                await session.delete(stored_secret)


class KeyVaultSecretStore(SecretStore):
    def __init__(self, vault_url: str, credential_provider: AzureCredentialProvider):
        self.vault_url = vault_url.rstrip("/")
        self.credential_provider = credential_provider

    async def _authorization_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.credential_provider.get_access_token(KEY_VAULT_SCOPE)}"}

    async def set_secret(self, secret_name: str, secret_value: str, description: str | None = None) -> None:
        async with httpx.AsyncClient(timeout=20) as http_client:
            response = await http_client.put(
                f"{self.vault_url}/secrets/{secret_name}?api-version={KEY_VAULT_API_VERSION}",
                headers=await self._authorization_headers(),
                json={"value": secret_value, "tags": {"managedBy": "keigan", "description": (description or "")[:250]}},
            )
        if response.status_code >= 400:
            raise IntegrationException(f"Key Vault refused to store the secret ({response.status_code}).")
        async with open_session() as session:
            if await session.get(StoredSecret, secret_name) is None:
                session.add(StoredSecret(secret_name=secret_name, encrypted_secret_value=None, secret_description=description))

    async def get_secret(self, secret_name: str) -> str:
        async with httpx.AsyncClient(timeout=20) as http_client:
            response = await http_client.get(
                f"{self.vault_url}/secrets/{secret_name}?api-version={KEY_VAULT_API_VERSION}", headers=await self._authorization_headers()
            )
        if response.status_code == 404:
            raise NotFoundException(f"Secret {secret_name} is not set.")
        if response.status_code >= 400:
            raise IntegrationException(f"Key Vault refused to read the secret ({response.status_code}).")
        return str(response.json()["value"])

    async def delete_secret(self, secret_name: str) -> None:
        async with httpx.AsyncClient(timeout=20) as http_client:
            await http_client.delete(
                f"{self.vault_url}/secrets/{secret_name}?api-version={KEY_VAULT_API_VERSION}", headers=await self._authorization_headers()
            )


def create_secret_store(settings: Settings, credential_provider: AzureCredentialProvider) -> SecretStore:
    if settings.secret_store_mode == "key_vault":
        if not settings.azure_key_vault_url:
            raise IntegrationException("SECRET_STORE_MODE=key_vault requires AZURE_KEY_VAULT_URL.")
        return KeyVaultSecretStore(settings.azure_key_vault_url, credential_provider)
    return LocalEncryptedSecretStore(settings.local_secret_encryption_key or settings.local_token_signing_secret)

"""Binary file storage for knowledge uploads: local disk in development, Azure Blob Storage in Azure."""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from keigan.config.settings import Settings
from keigan.exceptions.keigan_exceptions import IntegrationException, NotFoundException
from keigan.integrations.azure_identity_provider import AzureCredentialProvider

STORAGE_SCOPE = "https://storage.azure.com/.default"


def build_storage_path(application_id: str, original_file_name: str) -> str:
    """Random, non-guessable storage path that keeps the extension (never the user's file name)."""
    file_extension = Path(original_file_name).suffix.lower()[:10]
    return f"{application_id}/{uuid.uuid4().hex}{file_extension}"


class FileStorage(ABC):
    @abstractmethod
    async def save_file(self, storage_path: str, file_bytes: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def read_file(self, storage_path: str) -> bytes: ...

    @abstractmethod
    async def delete_file(self, storage_path: str) -> None: ...


class LocalFileStorage(FileStorage):
    def __init__(self, root_directory: Path):
        self.root_directory = root_directory.resolve()
        self.root_directory.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> Path:
        resolved_path = (self.root_directory / storage_path).resolve()
        if self.root_directory not in resolved_path.parents:
            raise IntegrationException("Invalid storage path.")
        return resolved_path

    async def save_file(self, storage_path: str, file_bytes: bytes, content_type: str) -> None:
        target_path = self._resolve_safe_path(storage_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target_path.write_bytes, file_bytes)

    async def read_file(self, storage_path: str) -> bytes:
        target_path = self._resolve_safe_path(storage_path)
        if not target_path.exists():
            raise NotFoundException("The stored file was not found.")
        return await asyncio.to_thread(target_path.read_bytes)

    async def delete_file(self, storage_path: str) -> None:
        target_path = self._resolve_safe_path(storage_path)
        if target_path.exists():
            await asyncio.to_thread(target_path.unlink)


class AzureBlobFileStorage(FileStorage):
    def __init__(self, account_url: str, container_name: str, credential_provider: AzureCredentialProvider):
        self.container_url = f"{account_url.rstrip('/')}/{container_name}"
        self.credential_provider = credential_provider

    async def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {await self.credential_provider.get_access_token(STORAGE_SCOPE)}",
            "x-ms-version": "2023-11-03",
        }
        headers.update(extra_headers or {})
        return headers

    async def save_file(self, storage_path: str, file_bytes: bytes, content_type: str) -> None:
        async with httpx.AsyncClient(timeout=60) as http_client:
            response = await http_client.put(
                f"{self.container_url}/{storage_path}",
                content=file_bytes,
                headers=await self._headers({"x-ms-blob-type": "BlockBlob", "Content-Type": content_type}),
            )
        if response.status_code >= 400:
            raise IntegrationException(f"Blob storage refused the upload ({response.status_code}).")

    async def read_file(self, storage_path: str) -> bytes:
        async with httpx.AsyncClient(timeout=60) as http_client:
            response = await http_client.get(f"{self.container_url}/{storage_path}", headers=await self._headers())
        if response.status_code == 404:
            raise NotFoundException("The stored file was not found.")
        if response.status_code >= 400:
            raise IntegrationException(f"Blob storage refused the download ({response.status_code}).")
        return response.content

    async def delete_file(self, storage_path: str) -> None:
        async with httpx.AsyncClient(timeout=30) as http_client:
            await http_client.delete(f"{self.container_url}/{storage_path}", headers=await self._headers())


def create_file_storage(settings: Settings, credential_provider: AzureCredentialProvider) -> FileStorage:
    if settings.file_storage_mode == "azure_blob":
        if not settings.azure_blob_account_url:
            raise IntegrationException("FILE_STORAGE_MODE=azure_blob requires AZURE_BLOB_ACCOUNT_URL.")
        return AzureBlobFileStorage(settings.azure_blob_account_url, settings.azure_blob_container, credential_provider)
    return LocalFileStorage(settings.data_directory / "uploads")

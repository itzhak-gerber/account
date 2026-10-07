"""File storage behind a small interface: a local folder, or Azure Blob Storage in the cloud."""

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import anyio
from azure.identity.aio import ManagedIdentityCredential
from azure.storage.blob.aio import BlobServiceClient

from app.core.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> StoredObject: ...
    async def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir).resolve()

    def _path(self, key: str) -> Path:
        path = (self._base / key).resolve()
        if not path.is_relative_to(self._base):
            raise ValueError("invalid storage key")
        return path

    async def put(self, key: str, data: bytes) -> StoredObject:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)  # atomic: never a half-written file

        await anyio.to_thread.run_sync(write)
        return StoredObject(key=key, size=len(data), sha256=hashlib.sha256(data).hexdigest())

    async def get(self, key: str) -> bytes:
        return await anyio.to_thread.run_sync(self._path(key).read_bytes)


class AzureBlobStorage:
    """Blobs in one private container. In Azure the app signs in with its managed identity;
    there is no storage key anywhere. A connection string is accepted only for local tests
    against the Azurite emulator."""

    def __init__(
        self,
        *,
        account_url: str | None,
        container: str,
        connection_string: str | None = None,
        client_id: str | None = None,
    ) -> None:
        self._container = container
        self._account_url = account_url
        self._connection_string = connection_string
        self._client_id = client_id
        self._service: BlobServiceClient | None = None

    def _client(self) -> BlobServiceClient:
        if self._service is None:
            if self._connection_string:
                self._service = BlobServiceClient.from_connection_string(self._connection_string)
            else:
                if not self._account_url:
                    raise RuntimeError("APP_AZURE_STORAGE_ACCOUNT_URL is not set")
                credential = ManagedIdentityCredential(client_id=self._client_id)
                self._service = BlobServiceClient(self._account_url, credential=credential)
        return self._service

    @staticmethod
    def _check(key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError("invalid storage key")
        return key

    async def put(self, key: str, data: bytes) -> StoredObject:
        blob = self._client().get_blob_client(self._container, self._check(key))
        # Overwrite allowed: if issuing failed after the upload, the retry writes the same key.
        # What stays fixed is decided by the database (an issued document keeps its file).
        await blob.upload_blob(data, overwrite=True)
        return StoredObject(key=key, size=len(data), sha256=hashlib.sha256(data).hexdigest())

    async def get(self, key: str) -> bytes:
        blob = self._client().get_blob_client(self._container, self._check(key))
        downloader = await blob.download_blob()
        return await downloader.readall()


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "azure":
        return AzureBlobStorage(
            account_url=settings.azure_storage_account_url,
            container=settings.azure_storage_container,
            connection_string=settings.azure_storage_connection_string,
            client_id=settings.azure_client_id,
        )
    return LocalStorage(settings.storage_dir)

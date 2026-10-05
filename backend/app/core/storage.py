"""File storage behind a small interface. Local disk now; Azure Blob Storage in M1b."""

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import anyio

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


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(get_settings().storage_dir)

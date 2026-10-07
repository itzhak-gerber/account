import os

import pytest

from app.core.storage import AzureBlobStorage, LocalStorage, Storage

AZURITE = os.environ.get("APP_TEST_AZURITE_CONNECTION_STRING")


async def roundtrip(storage: Storage) -> None:
    stored = await storage.put("b1/documents/d1/original.pdf", b"%PDF-1.7 test")
    again = await storage.put("b1/documents/d1/original.pdf", b"%PDF-1.7 test")  # a retry
    assert stored.size == 13
    assert stored.sha256 == again.sha256
    assert await storage.get("b1/documents/d1/original.pdf") == b"%PDF-1.7 test"
    with pytest.raises(ValueError):
        await storage.put("../escape.pdf", b"x")


async def test_local_storage(tmp_path: object) -> None:
    await roundtrip(LocalStorage(str(tmp_path)))


@pytest.mark.skipif(not AZURITE, reason="needs the Azurite emulator")
async def test_azure_blob_storage() -> None:
    from azure.storage.blob.aio import BlobServiceClient

    async with BlobServiceClient.from_connection_string(AZURITE or "") as service:
        container = service.get_container_client("files")
        if not await container.exists():
            await container.create_container()
    await roundtrip(
        AzureBlobStorage(account_url=None, container="files", connection_string=AZURITE)
    )

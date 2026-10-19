"""SPEC.md §7.2.1: the factory is the only place that reads BACKUP_BACKEND.
Azure is never exercised against a real account — BlobServiceClient is
mocked throughout (SPEC.md §9.1)."""

from unittest.mock import MagicMock, patch

from azure.core.exceptions import ResourceExistsError

from app.config import Settings
from app.storage import get_backup_storage
from app.storage.azure_blob import AzureBlobStorage
from app.storage.local import LocalStorage


def test_factory_returns_local_storage(tmp_path):
    settings = Settings(local_backup_dir=str(tmp_path))
    storage = get_backup_storage(settings)
    assert isinstance(storage, LocalStorage)


@patch("app.storage.azure_blob.BlobServiceClient")
def test_factory_returns_azure_storage_with_connection_string(mock_blob_service_client):
    mock_container = MagicMock()
    mock_blob_service_client.from_connection_string.return_value.get_container_client.return_value = (
        mock_container
    )
    settings = Settings(backup_backend="azure", azure_storage_connection_string="fake-connection-string")

    storage = get_backup_storage(settings)

    assert isinstance(storage, AzureBlobStorage)
    mock_blob_service_client.from_connection_string.assert_called_once_with("fake-connection-string")
    mock_container.create_container.assert_called_once()


@patch("app.storage.azure_blob.DefaultAzureCredential")
@patch("app.storage.azure_blob.BlobServiceClient")
def test_factory_returns_azure_storage_with_account_url(mock_blob_service_client, mock_credential):
    mock_container = MagicMock()
    mock_blob_service_client.return_value.get_container_client.return_value = mock_container
    settings = Settings(
        backup_backend="azure", azure_storage_account_url="https://example.blob.core.windows.net"
    )

    storage = get_backup_storage(settings)

    assert isinstance(storage, AzureBlobStorage)
    mock_blob_service_client.assert_called_once_with(
        account_url="https://example.blob.core.windows.net",
        credential=mock_credential.return_value,
    )


@patch("app.storage.azure_blob.BlobServiceClient")
def test_factory_tolerates_container_already_existing(mock_blob_service_client):
    mock_container = MagicMock()
    mock_container.create_container.side_effect = ResourceExistsError("already exists")
    mock_blob_service_client.from_connection_string.return_value.get_container_client.return_value = (
        mock_container
    )
    settings = Settings(backup_backend="azure", azure_storage_connection_string="fake-connection-string")

    storage = get_backup_storage(settings)  # must not raise

    assert isinstance(storage, AzureBlobStorage)


def test_local_storage_roundtrip(tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.upload("inventory-20260101T000000Z.json", b'{"hello": "world"}')

    backups = storage.list()
    assert len(backups) == 1
    assert backups[0].name == "inventory-20260101T000000Z.json"
    assert backups[0].size_bytes == len(b'{"hello": "world"}')

    assert storage.download("inventory-20260101T000000Z.json") == b'{"hello": "world"}'


def test_local_storage_download_missing_raises_file_not_found(tmp_path):
    storage = LocalStorage(str(tmp_path))
    try:
        storage.download("does-not-exist.json")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_local_storage_ignores_unrelated_files(tmp_path):
    storage = LocalStorage(str(tmp_path))
    (tmp_path / "not-a-backup.txt").write_text("irrelevant")
    storage.upload("inventory-20260101T000000Z.json", b"{}")

    assert [b.name for b in storage.list()] == ["inventory-20260101T000000Z.json"]

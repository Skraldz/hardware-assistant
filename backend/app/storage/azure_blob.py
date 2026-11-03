"""Azure Blob Storage backend (SPEC.md §7.2). Auth via either
AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL +
DefaultAzureCredential. The container is created if it doesn't exist yet.
"""

from typing import TYPE_CHECKING

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from app.storage.base import BackupInfo

if TYPE_CHECKING:
    from azure.storage.blob import ContainerClient

    from app.config import Settings


class AzureBlobStorage:
    """Backups in an Azure Blob Storage container.

    Offsite copy, so the inventory survives the loss of the machine holding
    it. Storage only -- no processing, no sharing, no inference. Credentials
    come from the environment, never from code or from a request.
    """

    def __init__(self, container_client: "ContainerClient") -> None:
        """Wrap an Azure container client.

        Args:
            container_client: A ready container client.
        """
        self._container = container_client

    @classmethod
    def from_settings(cls, settings: "Settings") -> "AzureBlobStorage":
        """Build the store from settings.

        Uses the connection string when present, otherwise the account URL with
        DefaultAzureCredential. Creates the container if it does not exist.

        Args:
            settings: Application settings.

        Returns:
            AzureBlobStorage: The configured store.
        """
        if settings.azure_storage_connection_string:
            service_client = BlobServiceClient.from_connection_string(
                settings.azure_storage_connection_string
            )
        else:
            service_client = BlobServiceClient(
                account_url=settings.azure_storage_account_url,
                credential=DefaultAzureCredential(),
            )
        container_client = service_client.get_container_client(settings.azure_backup_container)
        try:
            container_client.create_container()
        except ResourceExistsError:
            pass
        return cls(container_client)

    def upload(self, name: str, data: bytes) -> str:
        """Upload one backup blob.

        Args:
            name: Blob name.
            data: File contents.

        Returns:
            str: The blob URL.
        """
        blob_client = self._container.upload_blob(name=name, data=data, overwrite=True)
        return blob_client.url

    def list(self) -> list[BackupInfo]:
        """List blobs in the container, newest first.

        Returns:
            list[BackupInfo]: Name, size and last-modified for each blob.
        """
        return [
            BackupInfo(name=blob.name, created_at=blob.last_modified, size_bytes=blob.size or 0)
            for blob in self._container.list_blobs()
        ]

    def download(self, name: str) -> bytes:
        """Download one backup blob.

        Args:
            name: Blob name.

        Returns:
            bytes: The blob contents.

        Raises:
            FileNotFoundError: When no blob has that name.
        """
        # Normalised to FileNotFoundError so callers (services/backup.py)
        # handle a "missing backup" the same way regardless of backend.
        try:
            return self._container.download_blob(name).readall()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(name) from exc

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_backup_backend_defaults_to_local():
    settings = Settings()
    assert settings.backup_backend == "local"


def test_backup_backend_is_case_insensitive():
    settings = Settings(backup_backend="AZURE", azure_storage_connection_string="x")
    assert settings.backup_backend == "azure"


def test_invalid_backup_backend_raises():
    with pytest.raises(ValidationError):
        Settings(backup_backend="dropbox")


def test_azure_without_credentials_fails_fast():
    with pytest.raises(ValidationError, match="AZURE_STORAGE_CONNECTION_STRING"):
        Settings(backup_backend="azure")


def test_azure_with_connection_string_is_accepted():
    settings = Settings(backup_backend="azure", azure_storage_connection_string="x")
    assert settings.backup_backend == "azure"


def test_azure_with_account_url_is_accepted():
    settings = Settings(backup_backend="azure", azure_storage_account_url="https://x.blob.core.windows.net")
    assert settings.backup_backend == "azure"

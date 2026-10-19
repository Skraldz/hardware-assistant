from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://app:app@db:3306/hardware_assistant"

    # psu_wattage_sufficient rule (SPEC.md §6): required_w = (cpu_tdp + gpu_tdp +
    # psu_base_watt_w) * psu_safety_margin. Configurable per §6's requirement.
    psu_base_watt_w: int = 75
    psu_safety_margin: float = 1.3

    # --- LLM (Ollama) ---
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_request_timeout_s: float = 60.0

    # --- Web lookup (SearXNG) for /api/components/search + /extract ---
    enable_web_lookup: bool = True
    searxng_base_url: str = "http://searxng:8080"

    # --- Recommend pipeline ---
    recommend_top_n: int = 5
    recommend_default_max_builds: int = 3

    # --- Backup (SPEC.md §7.2.1) ---
    backup_backend: Literal["local", "azure"] = "local"
    local_backup_dir: str = "/app/backups"
    azure_storage_connection_string: str | None = None
    azure_storage_account_url: str | None = None
    azure_backup_container: str = "inventory-backups"

    @field_validator("backup_backend", mode="before")
    @classmethod
    def _normalize_backup_backend(cls, value: object) -> object:
        # Case-insensitive ("AZURE" == "azure") per SPEC.md §7.2.1.
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _require_azure_credentials_when_selected(self) -> "Settings":
        # Fail fast: never silently fall back to local storage when azure is
        # misconfigured, or the user would wrongly believe data is in the cloud.
        if self.backup_backend == "azure" and not (
            self.azure_storage_connection_string or self.azure_storage_account_url
        ):
            raise ValueError(
                "BACKUP_BACKEND=azure kræver AZURE_STORAGE_CONNECTION_STRING eller AZURE_STORAGE_ACCOUNT_URL"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

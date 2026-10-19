from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://app:app@db:3306/hardware_assistant"

    # psu_wattage_sufficient rule (SPEC.md §6): required_w = (cpu_tdp + gpu_tdp +
    # psu_base_watt_w) * psu_safety_margin. Configurable per §6's requirement.
    psu_base_watt_w: int = 75
    psu_safety_margin: float = 1.3


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://saras:saras@localhost:5432/saras"
    duckdb_path: str = "./data/analytics.duckdb"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # API security
    saras_api_key: str = "change-me"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # App
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()

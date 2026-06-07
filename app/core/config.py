from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки вынесены в отдельный класс, чтобы не держать параметры запуска в коде."""

    app_name: str = "IT Department Workflow System"
    app_env: str = "local"
    app_debug: bool = True
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Настройки кэшируются, чтобы приложение не перечитывало .env при каждом обращении."""
    return Settings()

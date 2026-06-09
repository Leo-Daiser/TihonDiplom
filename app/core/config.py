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
    zabbix_webhook_token: str = "local-zabbix-token"
    minio_endpoint: str = "minio:9000"
    minio_public_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "local-access-key"
    minio_secret_key: str = "local-secret-key"
    minio_bucket: str = "task-attachments"
    minio_secure: bool = False
    rocketchat_enabled: bool = False
    rocketchat_webhook_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Настройки кэшируются, чтобы приложение не перечитывало .env при каждом обращении."""
    return Settings()

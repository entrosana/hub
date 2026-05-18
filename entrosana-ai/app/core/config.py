"""Application config -- loaded from env + .env file."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str
    api_version: str = "0.0.1"
    cors_origins: list[str] = ["https://entrosana.com", "https://www.entrosana.com"]

    # Database
    database_url: str
    database_pool_size: int = 10

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # DLM / Claude
    anthropic_api_key: str = ""
    dlm_model_version: str = "claude-sonnet-4-6"
    dlm_prompt_version: str = "v0.1.0"
    dlm_temperature: float = 0.0
    dlm_audit_hmac_key: str

    # CashCtrl integration
    cashctrl_api_base: str = ""
    cashctrl_api_key: str = ""
    cashctrl_webhook_secret: str = ""

    # Auth
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Observability
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "entrosana-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()

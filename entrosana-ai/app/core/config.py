"""Application config -- loaded from env + .env file."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Specific shipped-placeholder markers — deliberately NOT the bare word "secret"
# (that would reject legitimate strong keys that merely contain it).
_PLACEHOLDERS = ("replace-me", "replace_me", "change-me", "changeme", "your-key-here")


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
    # Id of the current audit HMAC key, stored on each row so keys can rotate.
    # Retired keys stay verifiable via the keyring in app/audit/service.py.
    dlm_audit_hmac_key_id: str = "k1"

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
    otel_service_name: str = "entrosana-ai"

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        """Fail closed in production: the JWT signing key (`secret_key`) and the
        audit HMAC key must be strong and not a shipped placeholder (audit C3).
        Non-production envs are exempt so tests/dev can use fixed values.
        """
        if self.environment == "production":
            weak = []
            for name in ("secret_key", "dlm_audit_hmac_key"):
                val = getattr(self, name) or ""
                lowered = val.lower()
                if len(val) < 32 or any(p in lowered for p in _PLACEHOLDERS):
                    weak.append(name)
            if weak:
                raise ValueError(
                    "insecure secrets in production: "
                    + ", ".join(weak)
                    + " must be >=32 chars and not a placeholder"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()

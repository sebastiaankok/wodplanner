"""Application configuration."""

import secrets
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    environment: Literal["development", "production"] = "development"

    # WodApp credentials (no longer required for web - users log in themselves)
    wodapp_username: str | None = None
    wodapp_password: str | None = None

    # Logging
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Cache configuration
    api_cache_ttl_seconds: int = 600

    # Session configuration
    session_expire_days: int | None = None  # None = never expire
    cookie_secure: bool | None = None  # None = auto (True if production)
    # Set SECRET_KEY env var in production; random default invalidates sessions on restart
    secret_key: str = secrets.token_hex(32)

    # Google Calendar sync (all optional — feature is disabled when client_id is unset)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/google/callback"
    # Optional: base64url-encoded 32-byte Fernet key; derived from secret_key when absent
    google_token_enc_key: str | None = None

    @model_validator(mode="after")
    def apply_environment_defaults(self) -> "Settings":
        if self.cookie_secure is None:
            self.cookie_secure = self.environment == "production"
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

"""Application configuration."""

import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # WodApp credentials (no longer required for web - users log in themselves)
    wodapp_username: str | None = None
    wodapp_password: str | None = None

    # Cache configuration
    api_cache_ttl_seconds: int = 600

    # Session configuration
    session_expire_days: int = 7
    cookie_secure: bool = False  # Set True in production with HTTPS
    # Set SECRET_KEY env var in production; random default invalidates sessions on restart
    secret_key: str = secrets.token_hex(32)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

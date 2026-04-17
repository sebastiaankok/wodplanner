"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # WodApp credentials (no longer required for web - users log in themselves)
    wodapp_username: str | None = None
    wodapp_password: str | None = None

    # Session configuration
    session_expire_days: int = 7
    cookie_secure: bool = False  # Set True in production with HTTPS

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

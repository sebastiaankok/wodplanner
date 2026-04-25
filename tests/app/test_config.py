"""Tests for app/config.py"""

from wodplanner.app.config import Settings, settings


class TestSettings:
    def test_default_environment(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        s = Settings()
        assert s.environment == "development"

    def test_environment_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        s = Settings()
        assert s.environment == "production"

    def test_environment_development(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        s = Settings()
        assert s.environment == "development"

    def test_default_log_level(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        s = Settings()
        assert s.log_level == "INFO"

    def test_log_level_debug(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.log_level == "DEBUG"

    def test_default_api_cache_ttl(self, monkeypatch):
        monkeypatch.delenv("API_CACHE_TTL_SECONDS", raising=False)
        s = Settings()
        assert s.api_cache_ttl_seconds == 600

    def test_api_cache_ttl_custom(self, monkeypatch):
        monkeypatch.setenv("API_CACHE_TTL_SECONDS", "300")
        s = Settings()
        assert s.api_cache_ttl_seconds == 300

    def test_default_session_expire_days_none(self, monkeypatch):
        monkeypatch.delenv("SESSION_EXPIRE_DAYS", raising=False)
        s = Settings()
        assert s.session_expire_days is None

    def test_session_expire_days_set(self, monkeypatch):
        monkeypatch.setenv("SESSION_EXPIRE_DAYS", "30")
        s = Settings()
        assert s.session_expire_days == 30

    def test_wodapp_credentials_optional(self, monkeypatch):
        monkeypatch.delenv("WODAPP_USERNAME", raising=False)
        monkeypatch.delenv("WODAPP_PASSWORD", raising=False)
        s = Settings()
        assert s.wodapp_username is None
        assert s.wodapp_password is None

    def test_wodapp_credentials_set(self, monkeypatch):
        monkeypatch.setenv("WODAPP_USERNAME", "user")
        monkeypatch.setenv("WODAPP_PASSWORD", "pass")
        s = Settings()
        assert s.wodapp_username == "user"
        assert s.wodapp_password == "pass"

    def test_cookie_secure_default_dev(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
        s = Settings()
        assert s.cookie_secure is False

    def test_cookie_secure_default_prod(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
        s = Settings()
        assert s.cookie_secure is True

    def test_cookie_secure_explicit_true(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("COOKIE_SECURE", "true")
        s = Settings()
        assert s.cookie_secure is True

    def test_cookie_secure_explicit_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("COOKIE_SECURE", "false")
        s = Settings()
        assert s.cookie_secure is False

    def test_secret_key_default_hex(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        s = Settings()
        assert len(s.secret_key) == 64  # 32 bytes = 64 hex chars

    def test_secret_key_custom(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "custom_secret_key")
        s = Settings()
        assert s.secret_key == "custom_secret_key"


class TestSettingsSingleton:
    def test_settings_is_singleton(self):
        assert isinstance(settings, Settings)

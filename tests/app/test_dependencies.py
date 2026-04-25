"""Tests for app/dependencies.py"""

from pathlib import Path
from unittest.mock import patch

from wodplanner.app.dependencies import (
    _get_db_path,
    get_api_cache_service,
)


class TestGetDbPath:
    def test_default_db_path(self, monkeypatch):
        monkeypatch.delenv("DB_PATH", raising=False)
        path = _get_db_path()
        assert path == Path("/data/wodplanner.db")

    def test_custom_db_path_from_env(self, monkeypatch):
        monkeypatch.setenv("DB_PATH", "/custom/path/app.db")
        path = _get_db_path()
        assert path == Path("/custom/path/app.db")


class TestGetApiCacheService:
    def test_returns_api_cache_service_instance(self):
        get_api_cache_service.cache_clear()
        service = get_api_cache_service()
        assert service is not None
        from wodplanner.services.api_cache import ApiCacheService
        assert isinstance(service, ApiCacheService)

    def test_caches_same_instance(self):
        get_api_cache_service.cache_clear()
        service1 = get_api_cache_service()
        service2 = get_api_cache_service()
        assert service1 is service2

    def test_cache_clear_returns_new_instance(self):
        get_api_cache_service.cache_clear()
        service1 = get_api_cache_service()
        get_api_cache_service.cache_clear()
        service2 = get_api_cache_service()
        assert service1 is not service2

    def test_ttl_from_settings(self, monkeypatch):
        with patch("wodplanner.app.dependencies.settings") as mock_settings:
            mock_settings.api_cache_ttl_seconds = 300
            get_api_cache_service.cache_clear()
            service = get_api_cache_service()
            assert service._ttl == 300